#!/usr/bin/env python3
"""worktree_guard.py — detected-concurrency git worktree isolation (epic AC20, Stream L).

Single-session case is ZERO COST: a session opens in the shared tree. Only when a
SECOND live session exists for the spoke does this create an isolated git worktree
for it, so one session's git add/commit cannot sweep another's in-flight files
(the S45 silent-revert). Session->worktree mapping is recorded; orphaned worktrees
from crashed sessions are reaped on spin-up. get_worktree() is reused by the
execution sandbox for isolated test runs.

Contract: live sessions come from the guard file {"live_sessions": [ids]} (the real
session-guard.json is wired in by Basher at session-start) or an injected live_ids list.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

DEFAULT_MAPPING = "WAI-Spoke/runtime/worktree-map.json"
DEFAULT_GUARD = "WAI-Spoke/runtime/session-guard.json"

# ── Session lanes (concurrent-session isolation) ────────────────────────────
# A "lane" is one Claude Code session, keyed by the CC session_id (stable across
# every hook event and equal to the transcript filename). The registry maps each
# CC session to its own wai_session/track + private runtime dir (cursor, guard,
# buffer), so two concurrent sessions never share per-turn state. Single-session
# is zero-cost: one lane, legacy session name, work in the shared tree.
LANES_REGISTRY = "runtime/sessions-live.json"  # relative to the data base
LANES_DIR = "runtime/lanes"                    # per-lane private runtime, rel to base
LANE_TTL_SECONDS = 12 * 3600                   # a lane unseen this long is reaped
LANE_TRANSCRIPT_GRACE = 600                    # transcript-gone tolerated this long


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt=None):
    return (dt or _utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s):
    try:
        d = datetime.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def _existing_ancestor(p):
    """Nearest existing directory at or above p (the lane base may not exist yet)."""
    p = os.path.abspath(p)
    while p and not os.path.isdir(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return p


def _canonical_base(base):
    """Resolve a lane data base to the MAIN worktree so the lane registry is SHARED
    across all of a spoke's worktrees (cross-worktree liveness — concurrent-session
    isolation AC3). A session launched inside <main>/.worktrees/<n> passes
    base=<that worktree>/WAI-Harness/spoke/local; its registry MUST live in
    <main>/WAI-Harness/spoke/local, or the two sessions get divergent (gitignored,
    CWD-relative) registries and can't see each other. Falls back to base unchanged
    when git can't resolve a SEPARATE main worktree (single tree, non-git, or any
    error) — so the main-tree case is byte-identical to before."""
    ab = os.path.abspath(base)
    try:
        anchor = _existing_ancestor(ab)
        wt_root = _git_out(anchor, "rev-parse", "--show-toplevel")
        if not wt_root:
            return ab
        main_root = repo_root(anchor)
        if not main_root or os.path.abspath(main_root) == os.path.abspath(wt_root):
            return ab  # already the main worktree (or single tree): unchanged
        rel = os.path.relpath(ab, wt_root)
        if rel.startswith(".."):
            return ab  # base is not under the worktree root: don't rewrite
        return os.path.join(main_root, rel)
    except Exception:
        return ab


def _worktree_of_base(base):
    """If `base` lives inside <root>/.worktrees/<name>/..., return <name> (the session
    worktree this lane runs in) so convergence can link a lane to its branch. Else None
    (a lane in the main tree)."""
    ab = os.path.abspath(base)
    parts = ab.split(os.sep)
    try:
        i = parts.index(WORKTREES_DIR)
        return parts[i + 1] if i + 1 < len(parts) else None
    except ValueError:
        return None


def _registry_path(base):
    return os.path.join(_canonical_base(base), LANES_REGISTRY)


def _load_registry(base):
    p = _registry_path(base)
    if os.path.exists(p):
        try:
            d = json.load(open(p))
            if isinstance(d, dict) and isinstance(d.get("lanes"), dict):
                return d
        except Exception:
            pass
    return {"lanes": {}}


def _save_registry(base, reg):
    p = _registry_path(base)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reg, f, indent=2)
    os.replace(tmp, p)  # atomic on POSIX


def _lane_alive(meta, now):
    """A lane is dead once unseen past TTL, or once its transcript has been gone
    longer than the spin-up grace (covers crashed sessions without waiting the
    full TTL). Unknown last_seen is treated as alive (conservative)."""
    last = _parse_iso(meta.get("last_seen", ""))
    if last is not None and (now - last).total_seconds() > LANE_TTL_SECONDS:
        return False
    tp = meta.get("transcript", "")
    if tp and not os.path.exists(tp):
        if last is None or (now - last).total_seconds() > LANE_TRANSCRIPT_GRACE:
            return False
    return True


def _reap_registry(reg, now):
    """Drop dead lanes in place; return the list of reaped cc_sids."""
    dead = [sid for sid, m in reg["lanes"].items() if not _lane_alive(m, now)]
    for sid in dead:
        del reg["lanes"][sid]
    return dead


def _allocate_wai_session(base, lanes, cc_sid, now):
    """Human-friendly session name. Sole/first lane in a minute keeps the legacy
    `session-YYYYMMDD-HHMM` name; a same-minute collision with another lane or a
    pre-existing dir gets a short cc_sid suffix so concurrent lanes never share a
    track directory."""
    stamp = now.strftime("session-%Y%m%d-%H%M")
    used = {m.get("wai_session") for m in lanes.values()}
    sess_root = os.path.join(base, "sessions")
    if stamp in used or os.path.isdir(os.path.join(sess_root, stamp)):
        return f"{stamp}-{cc_sid[:8]}"
    return stamp


def lane_register(base, cc_sid, transcript="", create=True):
    """Idempotent per-CC-session lane resolution. Same cc_sid always returns the
    same wai_session (re-entry/IDE-reconnect is a no-op); a new cc_sid gets its own
    lane. Reaps dead lanes first so liveness/`others` is always current.

    Returns a dict (absolute paths) or None when create=False and the lane is
    unknown."""
    if not cc_sid:
        return None
    reg = _load_registry(base)
    now = _utcnow()
    _reap_registry(reg, now)
    lanes = reg["lanes"]
    meta = lanes.get(cc_sid)
    created = False
    if meta is None:
        if not create:
            _save_registry(base, reg)
            return None
        wai = _allocate_wai_session(base, lanes, cc_sid, now)
        meta = {"wai_session": wai, "started_at": _iso(now),
                "last_seen": _iso(now), "transcript": transcript}
        wt = _worktree_of_base(base)
        if wt:
            meta["worktree"] = wt   # link the lane to its source worktree (CSRP P6 convergence)
        lanes[cc_sid] = meta
        created = True
    else:
        meta["last_seen"] = _iso(now)
        if transcript:
            meta["transcript"] = transcript
        if "worktree" not in meta:
            wt = _worktree_of_base(base)
            if wt:
                meta["worktree"] = wt
    wai = meta["wai_session"]
    # Ensure the lane's directories exist (track dir + private runtime dir).
    sess_dir = os.path.join(base, "sessions", wai)
    lane_dir = os.path.join(base, LANES_DIR, cc_sid)
    os.makedirs(sess_dir, exist_ok=True)
    os.makedirs(lane_dir, exist_ok=True)
    track = os.path.join(sess_dir, "track.jsonl")
    if not os.path.exists(track):
        open(track, "a").close()
    _save_registry(base, reg)
    others = sorted(s for s in lanes if s != cc_sid)
    return {
        "cc_sid": cc_sid,
        "wai_session": wai,
        "track_path": track,
        "lane_dir": lane_dir,
        "others": others,
        "others_count": len(others),
        "created": created,
    }


def live_lanes(base):
    """Live lanes after reaping, as {cc_sid: meta}. Persists the reap."""
    reg = _load_registry(base)
    if _reap_registry(reg, _utcnow()):
        _save_registry(base, reg)
    return dict(reg["lanes"])


def lane_unregister(base, cc_sid):
    reg = _load_registry(base)
    if cc_sid in reg["lanes"]:
        del reg["lanes"][cc_sid]
        _save_registry(base, reg)
        return True
    return False


# ── Session worktrees (source-file isolation for concurrent sessions) ───────
# Lanes isolate TRACKING; a worktree isolates the SOURCE TREE. A concurrent
# session launched inside its own worktree is a separate checkout on its own
# branch — its file edits cannot collide with (or be swept by) another session's
# commit, and it merges back through normal git. Branch-based (not detached) so
# the work is committable and mergeable.
WORKTREES_DIR = ".worktrees"          # under the repo root; gitignored by the parent
WORKTREE_BRANCH_PREFIX = "session/"   # one branch per session worktree


def _git_out(repo, *args):
    r = _git(repo, *args)
    return r.stdout.strip() if r.returncode == 0 else ""


def repo_root(path="."):
    """The main worktree's top-level (so worktrees nest under the real repo root,
    never under a sibling worktree)."""
    top = _git_out(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if top:
        # git-common-dir is <root>/.git; its parent is the main worktree root
        d = os.path.dirname(top) if os.path.basename(top) == ".git" else None
        if d and os.path.isdir(d):
            return d
    return _git_out(path, "rev-parse", "--show-toplevel") or os.path.abspath(path)


def _sanitize_name(name):
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in name]
    return "".join(keep).strip("-") or "wt"


def _auto_name(repo):
    wtdir = os.path.join(repo, WORKTREES_DIR)
    existing = set(os.listdir(wtdir)) if os.path.isdir(wtdir) else set()
    i = 1
    while f"wt-{i}" in existing:
        i += 1
    return f"wt-{i}"


def _branch_exists(repo, branch):
    return _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0


def _ensure_worktrees_ignored(repo):
    """Guarantee .worktrees/ is git-ignored on ANY spoke, without depending on its
    .gitignore or committing anything: append the rule to the repo's git common-dir
    info/exclude (shared across worktrees, local, never distributed) if absent. Makes
    worktree isolation clean fleet-wide out of the box."""
    common = _git_out(repo, "rev-parse", "--git-common-dir")
    if not common:
        return
    if not os.path.isabs(common):
        common = os.path.join(repo_root(repo), common)
    exclude = os.path.join(common, "info", "exclude")
    try:
        existing = ""
        if os.path.exists(exclude):
            existing = open(exclude).read()
        if ".worktrees/" not in existing:
            os.makedirs(os.path.dirname(exclude), exist_ok=True)
            with open(exclude, "a") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write("# WAI session worktrees (concurrent-session source isolation)\n.worktrees/\n")
    except OSError:
        pass


def session_worktree_new(repo=".", name=None, harness_dev=False, start_point="HEAD"):
    """Create an isolated worktree on its own branch off start_point. Idempotent on
    name. harness_dev=True pins the worktree to self-master so a SessionStart there
    won't revert in-worktree managed/ edits (for editing the harness itself)."""
    root = repo_root(repo)
    name = _sanitize_name(name) if name else _auto_name(root)
    wt = os.path.join(root, WORKTREES_DIR, name)
    branch = f"{WORKTREE_BRANCH_PREFIX}{name}"
    if os.path.isdir(wt):
        return {"worktree": wt, "branch": branch, "created": False,
                "launch": f"cd {wt} && claude",
                "note": "worktree already exists; reusing."}
    _ensure_worktrees_ignored(root)  # self-healing: .worktrees/ ignored on any spoke
    os.makedirs(os.path.join(root, WORKTREES_DIR), exist_ok=True)
    if _branch_exists(root, branch):
        r = _git(root, "worktree", "add", wt, branch)
    else:
        r = _git(root, "worktree", "add", "-b", branch, wt, start_point)
    if r.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {r.stderr.strip()}")
    if harness_dev:
        wh = os.path.join(wt, "WAI-Harness")
        if os.path.isdir(wh):
            try:
                with open(os.path.join(wh, ".harness-master"), "w") as f:
                    f.write(os.path.abspath(wh) + "\n")
            except OSError:
                pass
    return {"worktree": wt, "branch": branch, "created": True,
            "launch": f"cd {wt} && claude",
            "note": ("self-mastered for harness-dev (managed/ edits won't be reverted)."
                     if harness_dev else
                     "launch a Claude Code session there; its edits stay on this branch.")}


def _worktree_meta(root, wt):
    rel = os.path.relpath(wt, root)
    branch = _git_out(wt, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = bool(_git_out(wt, "status", "--porcelain"))
    ahead = behind = 0
    counts = _git_out(wt, "rev-list", "--left-right", "--count", f"main...{branch}")
    if counts and "\t" in counts:
        b, a = counts.split("\t")[:2]
        behind, ahead = int(b or 0), int(a or 0)
    merged = branch in _git_out(root, "branch", "--merged", "main")
    return {"name": os.path.basename(wt), "path": wt, "rel": rel, "branch": branch,
            "dirty": dirty, "ahead": ahead, "behind": behind, "merged_to_main": merged}


def session_worktrees(repo="."):
    """List the session worktrees under .worktrees/ with branch/dirty/ahead-behind."""
    root = repo_root(repo)
    wtroot = os.path.join(root, WORKTREES_DIR)
    out = []
    if os.path.isdir(wtroot):
        for name in sorted(os.listdir(wtroot)):
            wt = os.path.join(wtroot, name)
            if os.path.isdir(wt) and _git(wt, "rev-parse", "--is-inside-work-tree").returncode == 0:
                out.append(_worktree_meta(root, wt))
    return out


def session_worktree_finish(repo=".", name=None, merge=False, force=False):
    """Retire a session worktree. Refuses to discard uncommitted work unless force.
    merge=True fast-forwards/merges its branch into main first (only when the main
    worktree is clean and on main)."""
    root = repo_root(repo)
    name = _sanitize_name(name)
    wt = os.path.join(root, WORKTREES_DIR, name)
    branch = f"{WORKTREE_BRANCH_PREFIX}{name}"
    if not os.path.isdir(wt):
        return {"ok": False, "error": f"no worktree {name}"}
    meta = _worktree_meta(root, wt)
    if meta["dirty"] and not force:
        return {"ok": False, "error": "worktree has uncommitted changes; commit them, "
                "or pass force to discard.", "meta": meta}
    merged = False
    if merge and not meta["dirty"]:
        cur = _git_out(root, "rev-parse", "--abbrev-ref", "HEAD")
        # Only uncommitted TRACKED changes block a merge; untracked files (e.g. the
        # gitignored .worktrees/ dir itself) are irrelevant to a merge's safety.
        if cur != "main" or _git_out(root, "status", "--porcelain", "--untracked-files=no"):
            return {"ok": False, "error": "to merge, the main worktree must be clean and "
                    "on main.", "meta": meta}
        r = _git(root, "merge", "--no-ff", "-m", f"merge {branch}", branch)
        if r.returncode != 0:
            return {"ok": False, "error": f"merge failed: {r.stderr.strip()}", "meta": meta}
        merged = True
    rr = _git(root, "worktree", "remove", *(["--force"] if force else []), wt)
    if rr.returncode != 0:
        return {"ok": False, "error": f"worktree remove failed: {rr.stderr.strip()}", "meta": meta}
    _git(root, "branch", "-D" if force else "-d", branch)
    return {"ok": True, "removed": wt, "branch": branch, "merged": merged}


def session_worktree_reap(repo="."):
    """Remove worktrees that are clean AND fully merged into main (safe cleanup).
    Leaves dirty/unmerged worktrees in place and reports them."""
    root = repo_root(repo)
    reaped, kept = [], []
    for meta in session_worktrees(root):
        if not meta["dirty"] and meta["merged_to_main"]:
            session_worktree_finish(root, meta["name"])
            reaped.append(meta["name"])
        else:
            kept.append({"name": meta["name"], "dirty": meta["dirty"],
                         "ahead": meta["ahead"], "reason": "dirty" if meta["dirty"] else "unmerged"})
    return {"reaped": reaped, "kept": kept}


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def live_sessions(guard_path=DEFAULT_GUARD, base=None):
    """Live session ids. Prefer the lane registry (the authority); fall back to a
    guard file's explicit live_sessions list for legacy/injected callers."""
    if base:
        return sorted(live_lanes(base).keys())
    if not os.path.exists(guard_path):
        return []
    try:
        d = json.load(open(guard_path))
    except Exception:
        return []
    return list(d.get("live_sessions", []))


def _load_map(mapping_path):
    return json.load(open(mapping_path)) if os.path.exists(mapping_path) else {}


def _save_map(mapping_path, m):
    os.makedirs(os.path.dirname(os.path.abspath(mapping_path)), exist_ok=True)
    json.dump(m, open(mapping_path, "w"), indent=2)


def ensure_worktree(session_id, repo_path, guard_path=DEFAULT_GUARD,
                    mapping_path=DEFAULT_MAPPING, live_ids=None):
    """If another live session exists, isolate this one in its own worktree. Else None (shared tree)."""
    live = live_ids if live_ids is not None else live_sessions(guard_path)
    others = [s for s in live if s != session_id]
    if not others:
        return None  # single-session: zero cost, work in the shared tree
    m = _load_map(mapping_path)
    if session_id in m and os.path.isdir(m[session_id]):
        return m[session_id]
    wt = os.path.join(repo_path, ".worktrees", f"session-{session_id}")
    if not os.path.isdir(wt):
        r = _git(repo_path, "worktree", "add", "--detach", wt)
        if r.returncode != 0:
            raise RuntimeError(f"git worktree add failed: {r.stderr}")
    m[session_id] = wt
    _save_map(mapping_path, m)
    return wt


def reap_orphans(repo_path, mapping_path=DEFAULT_MAPPING, live_ids=None, guard_path=DEFAULT_GUARD):
    """Remove worktrees + mappings for sessions no longer live (crashed-session cleanup)."""
    live = set(live_ids if live_ids is not None else live_sessions(guard_path))
    m = _load_map(mapping_path)
    reaped = []
    for sid, wt in list(m.items()):
        if sid not in live:
            _git(repo_path, "worktree", "remove", "--force", wt)
            del m[sid]
            reaped.append(sid)
    _git(repo_path, "worktree", "prune")
    _save_map(mapping_path, m)
    return reaped


def get_worktree(session_id, mapping_path=DEFAULT_MAPPING, repo_path="."):
    """The path this session should operate in (its worktree, or the shared tree)."""
    return _load_map(mapping_path).get(session_id, repo_path)


def ownership_status(session_id, repo_path=".", guard_path=DEFAULT_GUARD,
                     mapping_path=DEFAULT_MAPPING, live_ids=None):
    """Answer the question every concurrent session must be able to ask: 'who owns this
    working tree right now, and am I safe to commit?' (epic AC3 / prevent-state-decay).

    The S45 episode: 3 framework sessions ran in ONE shared tree with no ownership
    surface, risking blind-commit-sweeps. This makes ownership observable.

    Returns {session_id, others_live[], isolated, owns_tree, safe_to_commit, advice}:
      - 0 other live sessions      -> you own the shared tree; safe to commit.
      - others live + you isolated -> you own YOUR worktree; safe to commit (in it).
      - others live + NOT isolated -> NO exclusive owner; NOT safe to blind-commit.
    """
    live = live_ids if live_ids is not None else live_sessions(guard_path)
    others = [s for s in live if s != session_id]
    wt = get_worktree(session_id, mapping_path, repo_path)
    isolated = bool(wt) and os.path.abspath(wt) != os.path.abspath(repo_path)
    if not others:
        return {"session_id": session_id, "others_live": [], "isolated": isolated,
                "owns_tree": True, "safe_to_commit": True,
                "advice": "single live session: you own the shared tree; safe to commit."}
    if isolated:
        return {"session_id": session_id, "others_live": others, "isolated": True,
                "owns_tree": True, "safe_to_commit": True,
                "advice": f"isolated in {wt}; {len(others)} other live session(s) — safe to commit in your worktree."}
    return {"session_id": session_id, "others_live": others, "isolated": False,
            "owns_tree": False, "safe_to_commit": False,
            "advice": (f"SHARED TREE with {len(others)} other live session(s) {others} and NO isolation. "
                       "Do NOT 'git add -A'/blind-commit — scope every add to your own files and "
                       "verify the staged set, or run ensure_worktree to isolate first.")}


def _cmd_lane_register(argv):
    ap = argparse.ArgumentParser(prog="lane-register")
    ap.add_argument("--session", required=True, help="Claude Code session id (lane key)")
    ap.add_argument("--base", required=True, help="data base, e.g. WAI-Harness/spoke/local")
    ap.add_argument("--transcript", default="")
    ap.add_argument("--no-create", action="store_true", help="resolve only; do not create a lane")
    a = ap.parse_args(argv)
    res = lane_register(a.base, a.session, a.transcript, create=not a.no_create)
    print(json.dumps(res or {}))
    return 0


def _cmd_lane_reap(argv):
    ap = argparse.ArgumentParser(prog="lane-reap")
    ap.add_argument("--base", required=True)
    a = ap.parse_args(argv)
    reg = _load_registry(a.base)
    reaped = _reap_registry(reg, _utcnow())
    _save_registry(a.base, reg)
    print(json.dumps({"reaped": reaped, "live": sorted(reg["lanes"].keys())}))
    return 0


def _cmd_lane_unregister(argv):
    ap = argparse.ArgumentParser(prog="lane-unregister")
    ap.add_argument("--base", required=True)
    ap.add_argument("--session", required=True, help="cc_sid lane key to remove")
    a = ap.parse_args(argv)
    before = a.session in _load_registry(a.base)["lanes"]
    lane_unregister(a.base, a.session)
    print(json.dumps({"unregistered": a.session, "was_present": before}))
    return 0


def _cmd_lanes(argv):
    ap = argparse.ArgumentParser(prog="lanes")
    ap.add_argument("--base", required=True)
    a = ap.parse_args(argv)
    lanes = live_lanes(a.base)
    print(json.dumps({"count": len(lanes), "lanes": lanes}))
    return 0


def _cmd_ownership(argv):
    ap = argparse.ArgumentParser(prog="ownership")
    ap.add_argument("--session", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--repo-path", default=".")
    a = ap.parse_args(argv)
    live = live_sessions(base=a.base)
    print(json.dumps(ownership_status(a.session, a.repo_path, live_ids=live)))
    return 0


def _cmd_wt_new(argv):
    ap = argparse.ArgumentParser(prog="wt-new")
    ap.add_argument("name", nargs="?", default=None, help="worktree name (auto wt-N if omitted)")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--harness-dev", action="store_true",
                    help="pin the worktree to self-master (for editing managed/ harness code)")
    ap.add_argument("--from", dest="start_point", default="HEAD")
    a = ap.parse_args(argv)
    print(json.dumps(session_worktree_new(a.repo, a.name, a.harness_dev, a.start_point), indent=2))
    return 0


def _cmd_wt_list(argv):
    ap = argparse.ArgumentParser(prog="wt-list")
    ap.add_argument("--repo", default=".")
    a = ap.parse_args(argv)
    print(json.dumps(session_worktrees(a.repo), indent=2))
    return 0


def _cmd_wt_finish(argv):
    ap = argparse.ArgumentParser(prog="wt-finish")
    ap.add_argument("name")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--merge", action="store_true", help="merge the branch into main first")
    ap.add_argument("--force", action="store_true", help="discard uncommitted work / force-remove")
    a = ap.parse_args(argv)
    res = session_worktree_finish(a.repo, a.name, a.merge, a.force)
    print(json.dumps(res, indent=2))
    return 0 if res.get("ok") else 1


def _cmd_wt_reap(argv):
    ap = argparse.ArgumentParser(prog="wt-reap")
    ap.add_argument("--repo", default=".")
    a = ap.parse_args(argv)
    print(json.dumps(session_worktree_reap(a.repo), indent=2))
    return 0


_SUBCOMMANDS = {
    "lane-register": _cmd_lane_register,
    "lane-resolve": _cmd_lane_register,  # alias: same idempotent register/lookup
    "lane-reap": _cmd_lane_reap,
    "lane-unregister": _cmd_lane_unregister,
    "lanes": _cmd_lanes,
    "ownership": _cmd_ownership,
    "wt-new": _cmd_wt_new,
    "wt-list": _cmd_wt_list,
    "wt-finish": _cmd_wt_finish,
    "wt-reap": _cmd_wt_reap,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in _SUBCOMMANDS:
        return _SUBCOMMANDS[argv[0]](argv[1:])

    # Legacy flag form (git-worktree isolation / ownership for explicit callers).
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--repo-path", default=".")
    ap.add_argument("--base", default=None, help="data base; derive live lanes from the registry")
    ap.add_argument("--mapping-path", default=DEFAULT_MAPPING)
    ap.add_argument("--guard-path", default=DEFAULT_GUARD)
    ap.add_argument("--reap", action="store_true")
    ap.add_argument("--status", action="store_true", help="print ownership/commit-safety status as JSON")
    args = ap.parse_args(argv)
    live = live_sessions(args.guard_path, base=args.base) if args.base else None
    if args.reap:
        print(f"[worktree] reaped: {reap_orphans(args.repo_path, args.mapping_path, guard_path=args.guard_path)}")
    if args.status:
        print(json.dumps(ownership_status(args.session_id, args.repo_path,
                                          args.guard_path, args.mapping_path, live_ids=live)))
        return 0
    wt = ensure_worktree(args.session_id, args.repo_path, args.guard_path, args.mapping_path, live_ids=live)
    print(f"[worktree] {'isolated -> ' + wt if wt else 'single-session -> shared tree (zero cost)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
