#!/usr/bin/env python3
"""guidance.py — the guidance language (spec-guidance-language-v1, AC45).

Four object types steer the autonomous wheel; the dispatcher/expediter/pre-tool-guard
read them on every decision:

  goal        {goal_id, statement, metric?, priority, active_until?}      -> SOFT ranking
  guardrail   {guardrail_id, kind, value, scope?, hard, mandated?}        -> HARD block
  focus_lock  {focus_id, target, mode: exclusive|priority, active_until?} -> dispatch scope
  sign_off    {action_id, bucket, ...}  + acks {action_id, ack, reason, signer} -> staged-until-ack

Hard rules (spec constraints):
  - Guardrails are HARD + machine-enforced: a violation is BLOCKED + logged, never warned.
  - A spoke cannot WEAKEN a hub-mandated guardrail; it may only add stricter local ones.
  - Sign-off-required actions stay STAGED until a matching approve ack exists.
  - Focus-lock PAUSES out-of-focus work (visible), never deletes it.
  - Every set/change/expiry/sign-off is written to the guidance-log — no silent steering.

Pure + path-injected: load_guidance / stack_guardrails / is_active / rank_by_goals /
filter_by_focus / enforce_guardrail / sign_off_status / log_guidance. The library passes
the spec's 8 tests directly; live wiring (dispatcher budget pause already exists via the
circuit-breaker; pre-tool-guard no_touch_path/banned_action enforcement is a Basher .claude
change-lug; expediter consumes rank+focus).
"""
import fnmatch
import json
import os
from pathlib import Path

GUIDANCE_FILE = "guidance.json"          # {goals, guardrails, focus_locks, sign_offs, acks}
LOG_FILE = "guidance-log.jsonl"
# how a spoke guardrail of each kind would WEAKEN a mandated hub one (rejected):
#   budget/rate: a LARGER value is weaker (more allowance)
#   no_touch_path/banned_action/scope: REMOVING or differing is weaker
_NUMERIC_KINDS = {"budget", "rate"}


# ----------------------------- load -----------------------------

def load_guidance(spoke_dir, hub_dir=None):
    """Read spoke (and optional hub) guidance and return the stacked set.
    Each dir holds a guidance.json with {goals, guardrails, focus_locks, sign_offs, acks}.
    Missing files yield empty lists. Hub guardrails are mandated and stack first."""
    spoke = _read(Path(spoke_dir) / GUIDANCE_FILE)
    hub = _read(Path(hub_dir) / GUIDANCE_FILE) if hub_dir else {}
    hub_rails = [{**g, "mandated": True} for g in hub.get("guardrails", [])]
    guardrails, rejected = stack_guardrails(hub_rails, spoke.get("guardrails", []))
    return {
        "goals": hub.get("goals", []) + spoke.get("goals", []),
        "guardrails": guardrails,
        "rejected_guardrails": rejected,
        "focus_locks": hub.get("focus_locks", []) + spoke.get("focus_locks", []),
        "sign_offs": spoke.get("sign_offs", []) + hub.get("sign_offs", []),
        "acks": spoke.get("acks", []) + hub.get("acks", []),
    }


def _read(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError):
        return {}


# ----------------------------- stacking -----------------------------

def stack_guardrails(hub_rails, spoke_rails):
    """Merge hub (mandated) + spoke guardrails. A spoke guardrail that targets the same
    guardrail_id (or kind+scope) as a mandated hub rail and would WEAKEN it is REJECTED;
    the hub value stands. A spoke may add new (stricter/independent) guardrails.
    Returns (effective_guardrails, rejected[])."""
    effective = list(hub_rails)
    rejected = []
    by_id = {g.get("guardrail_id"): g for g in hub_rails}
    by_ks = {(g.get("kind"), g.get("scope")): g for g in hub_rails}
    for sr in spoke_rails:
        hub_match = by_id.get(sr.get("guardrail_id")) or by_ks.get((sr.get("kind"), sr.get("scope")))
        if hub_match and hub_match.get("mandated") and _weakens(hub_match, sr):
            rejected.append({"guardrail": sr, "reason": "cannot weaken mandated hub guardrail",
                             "mandated_value": hub_match.get("value")})
            continue
        effective.append(sr)
    return effective, rejected


def _weakens(hub_rail, spoke_rail):
    """True if spoke_rail is a weaker version of a mandated hub_rail."""
    if hub_rail.get("kind") in _NUMERIC_KINDS:
        try:
            return float(spoke_rail.get("value")) > float(hub_rail.get("value"))
        except (TypeError, ValueError):
            return spoke_rail.get("value") != hub_rail.get("value")
    # path/action/scope: any differing value targeting the same rail is a weaken attempt
    return spoke_rail.get("value") != hub_rail.get("value")


# ----------------------------- lifecycle -----------------------------

def is_active(obj, now_ts):
    """A guidance object is active unless its active_until is in the past (string compare
    on ISO-8601 timestamps, which sort lexicographically)."""
    until = obj.get("active_until")
    return True if not until else str(now_ts) < str(until)


def expire_pass(objs, now_ts):
    """Split objects into (active, expired) by active_until."""
    active, expired = [], []
    for o in objs:
        (active if is_active(o, now_ts) else expired).append(o)
    return active, expired


# ----------------------------- goals (soft ranking) -----------------------------

def rank_by_goals(items, goals, now_ts, key="target"):
    """Stable-sort items by the priority of the goal matching item[key] (lower priority
    number = higher). Items matching no active goal sort last, original order preserved.
    A goal matches an item when goal['target'] == item[key]."""
    active = [g for g in goals if is_active(g, now_ts)]
    pri = {g.get("target"): g.get("priority", 10_000) for g in active}
    return sorted(enumerate(items),
                  key=lambda iv: (pri.get(iv[1].get(key), 10_000), iv[0]))
    # note: returns list of (orig_index, item); callers usually want just the items:


def ranked_items(items, goals, now_ts, key="target"):
    return [it for _i, it in rank_by_goals(items, goals, now_ts, key=key)]


# ----------------------------- focus-lock (dispatch scope) -----------------------------

def filter_by_focus(items, focus_locks, now_ts):
    """Apply active focus-locks to the autonomous queue.
    Returns {dispatch: [...], paused: [{item, reason}], expired: [focus_id,...]}.
    exclusive mode: only items matching ANY exclusive focus target dispatch; the rest are
    paused 'by focus-lock'. priority mode alone does not pause (ranking handles it).
    A focus matches an item when its target equals item['epic'] / item['initiative'] or
    glob-matches item['path']."""
    active, expired = expire_pass(focus_locks, now_ts)
    exclusive = [f for f in active if f.get("mode", "exclusive") == "exclusive"]
    out = {"dispatch": [], "paused": [], "expired": [f.get("focus_id") for f in expired]}
    if not exclusive:
        out["dispatch"] = list(items)
        return out
    for it in items:
        if any(_focus_matches(f, it) for f in exclusive):
            out["dispatch"].append(it)
        else:
            out["paused"].append({"item": it, "reason": "paused by focus-lock"})
    return out


def _focus_matches(focus, item):
    tgt = focus.get("target")
    if tgt in (item.get("epic"), item.get("initiative"), item.get("id")):
        return True
    path = item.get("path")
    return bool(path and fnmatch.fnmatch(path, tgt))


# ----------------------------- guardrails (hard blocks) -----------------------------

def enforce_guardrail(action, guardrails, now_ts=None):
    """Check an action against all active HARD guardrails. Returns
    {allowed: bool, violation: {guardrail_id, kind, reason}|None}. First violation wins.

    action keys consulted by kind:
      no_touch_path -> action['path']    blocked if it matches guardrail value (glob)
      banned_action -> action['action']  blocked if it equals guardrail value
      budget        -> action['spend_after'] (running total)  blocked if > value
      scope         -> action['scope']   blocked if guardrail value set and != it
      rate          -> action['rate']     blocked if > value
    """
    for g in guardrails:
        if now_ts is not None and not is_active(g, now_ts):
            continue
        if not g.get("hard", True):
            continue
        kind, val = g.get("kind"), g.get("value")
        v = None
        if kind == "no_touch_path" and action.get("path") is not None:
            if fnmatch.fnmatch(action["path"], str(val)):
                v = f"path {action['path']} matches no_touch {val}"
        elif kind == "banned_action" and action.get("action") is not None:
            if action["action"] == val:
                v = f"action '{action['action']}' is banned"
        elif kind == "budget" and action.get("spend_after") is not None:
            if float(action["spend_after"]) > float(val):
                v = f"spend {action['spend_after']} exceeds budget {val}"
        elif kind == "scope" and val is not None and action.get("scope") is not None:
            if action["scope"] != val:
                v = f"scope '{action['scope']}' outside allowed '{val}'"
        elif kind == "rate" and action.get("rate") is not None:
            if float(action["rate"]) > float(val):
                v = f"rate {action['rate']} exceeds {val}"
        if v:
            return {"allowed": False,
                    "violation": {"guardrail_id": g.get("guardrail_id"), "kind": kind, "reason": v}}
    return {"allowed": True, "violation": None}


# ----------------------------- sign-off (staged until ack) -----------------------------

SIGN_OFF_BUCKETS = {"Flag", "Drop", "decommission"}


def needs_sign_off(action):
    """An action requires sign-off if its bucket is Flag/Drop/decommission."""
    return action.get("bucket") in SIGN_OFF_BUCKETS


def sign_off_status(action_id, acks):
    """staged | approved | rejected | deferred — from the latest matching ack."""
    matching = [a for a in acks if a.get("action_id") == action_id]
    if not matching:
        return "staged"
    last = matching[-1].get("ack")
    return {"approve": "approved", "reject": "rejected", "defer": "deferred"}.get(last, "staged")


def can_proceed(action, acks):
    """True only if the action needs no sign-off, or it has an approve ack."""
    if not needs_sign_off(action):
        return True
    return sign_off_status(action.get("action_id"), acks) == "approved"


# ----------------------------- guidance-log -----------------------------

def log_guidance(log_path, record):
    """Append one record to the guidance-log (jsonl). record MUST carry event + (signer
    or actor) + reason so Historian can answer 'who steered, when, why'. Returns record."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def read_guidance_log(log_path):
    log_path = Path(log_path)
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
