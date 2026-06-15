#!/usr/bin/env python3
"""hygiene.py — self-healing stale-path remediation (AC22) + the Hygiene/Hank act-arm (AC34).

gap_exposure_validator + verification_spine.GAP_TYPES already DETECT cruft/misplacement and
deprecation-live. This is the arm that ACTS on them — safely:

  redirect_path(path, home_map)         (AC22) — during v3->v4 coexistence, a write aimed at a
       deprecated v3 WAI-Spoke/<cat> path is self-healed to its v4 WAI-Harness home, so work
       never silently lands in a dead tree. Returns (healed_path, was_redirected).
  detect_misplaced(disk_paths, homes)   (AC34) — files not under their home-map home.
  plan_remediation(misplaced, ...)      (AC34) — a DRY-RUN plan: misplaced->home (relocate),
       cruft->trash_bin (NEVER rm, preserving relative path). Human sign-off gated for Drop.

Pure + path-injected. Relocation is additive/plan-first; nothing is moved by these functions —
the caller (Hank advisor) executes the plan after the Flag/Drop sign-off (guidance.py).
Reuses harness_activate.HOME_MAP for the v3->v4 category mapping (single source).
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
try:
    from harness_activate import HOME_MAP as _V3_TO_V4  # {v3 cat -> v4 rel}
except Exception:  # noqa: BLE001
    _V3_TO_V4 = {
        "WAI-State.json": "spoke/local/WAI-State.json", "sessions": "spoke/local/sessions",
        "lugs": "spoke/local/lugs", "savepoints": "spoke/local/savepoints",
        "initiatives": "spoke/local/initiatives", "signals": "spoke/local/signals",
        "bolts": "spoke/local/bolts", "teachings": "spoke/local/teachings",
        "kpi": "spoke/local/kpi", "advisors": "spoke/advisors",
    }

TRASH_ROOT = "/home/mario/projects/trash_bin"   # never rm under ~/projects


def redirect_path(path, home_map=None, v3_root="WAI-Spoke", v4_root="WAI-Harness"):
    """AC22 self-heal: if `path` targets a deprecated v3 WAI-Spoke/<cat>... write, return the
    v4 WAI-Harness home for it. Returns (healed_path, was_redirected). Idempotent: a path
    already under v4 (or not a mapped category) is returned unchanged."""
    home_map = home_map or _V3_TO_V4
    p = str(path).replace("\\", "/")
    prefix = v3_root + "/"
    if not p.startswith(prefix):
        return p, False
    rest = p[len(prefix):]            # e.g. "lugs/incoming/x.json" or "WAI-State.json"
    cat = rest.split("/", 1)[0]
    if cat not in home_map:
        return p, False               # unmapped v3 category — stays in v3 (no-orphan: never dropped)
    v4_rel = home_map[cat]
    tail = rest[len(cat):].lstrip("/")
    healed = f"{v4_root}/{v4_rel}" + (f"/{tail}" if tail else "")
    return healed, True


def detect_misplaced(disk_paths, expected_homes):
    """AC34 detect: a file is misplaced if its top-level category has a known home and the
    file does not live under that home. expected_homes: {category -> home_prefix}.
    Returns [{path, category, expected_home}]."""
    out = []
    for p in disk_paths:
        p = str(p).replace("\\", "/")
        cat = p.split("/", 1)[0]
        home = expected_homes.get(cat)
        if home and not p.startswith(home):
            out.append({"path": p, "category": cat, "expected_home": home})
    return out


def _trash_dest(path, trash_root=TRASH_ROOT, project_root="/home/mario/projects"):
    """Trash destination preserving the relative path under project_root (never rm)."""
    p = Path(path)
    try:
        rel = p.relative_to(project_root)
    except ValueError:
        rel = Path(p.name)
    return str(Path(trash_root) / rel)


def plan_remediation(misplaced, cruft=None, trash_root=TRASH_ROOT):
    """AC34 act (DRY-RUN plan): relocate misplaced files to their home; route cruft to
    trash_bin (NEVER rm), preserving relative path. Returns a plan; nothing is moved here.
    cruft entries that are a Drop carry human_gate=True (sign-off required)."""
    plan = {"relocate": [], "trash": [], "human_gate": False}
    for m in misplaced:
        rel = m["path"].split("/", 1)[1] if "/" in m["path"] else m["path"]
        plan["relocate"].append({"from": m["path"],
                                 "to": m["expected_home"].rstrip("/") + "/" + rel,
                                 "reason": f"misplaced: {m['category']} belongs under {m['expected_home']}"})
    for c in (cruft or []):
        plan["trash"].append({"from": c, "to": _trash_dest(c), "reason": "cruft", "human_gate": True})
    plan["human_gate"] = bool(plan["trash"])   # Drop/trash requires sign-off (guidance.py)
    return plan
