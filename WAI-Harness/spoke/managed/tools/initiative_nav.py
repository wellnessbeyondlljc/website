#!/usr/bin/env python3
"""initiative_nav.py — runnable nav verbs for the initiative save/start/resume/sleep/wake feature.

Wires the gap on top of the existing foundation (initiative_store.py CRUD, the
initiative schema, flat savepoints). Verbs: list / show / tree / new / pin /
switch / sleep / wake / save / adopt / wake-check.

Folder model you can SEE (under WAI-Harness/spoke/local/initiatives/):
  index.json                                         read-model
  current.json                                       the active focus pin
  bytype/initiative/<state>/<id>.json                the initiative object (store)
  savepoints/<id>/sp-*.json                          child savepoints (symlinks to the
                                                     authoritative flat savepoints/, so the
                                                     /wai resume menu still sees them)

Lifecycle: proposed | approved | active | measuring | dormant | complete | abandoned.
sleep: active->dormant (captures dormant_from + wake_on). wake / wake-check: dormant->dormant_from.

NOTE (ownership): the /wai-initiative slash command + /wai continuation-menu surfacing
are managed/.claude (Basher's). This tool is the engine those wrappers call; run it
directly today:  python3 initiative_nav.py <verb> ...
"""
import os, sys, json, glob, time, datetime, importlib.util, subprocess

ROOT = os.environ.get("WAI_ROOT", ".")
_STORE_PATH = os.path.join(ROOT, "WAI-Harness/spoke/managed/tools/initiative_store.py")


def _load_store():
    spec = importlib.util.spec_from_file_location("initiative_store", _STORE_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


store = _load_store()


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def base():
    return store.resolve_base(ROOT)


def sp_flat_dir():
    return os.path.join(ROOT, "WAI-Harness/spoke/local/savepoints")


def sp_nested_dir(iid):
    return os.path.join(str(base()), "savepoints", iid)


def current_path():
    return os.path.join(str(base()), "current.json")


# ---- focus pin -------------------------------------------------------------
def get_focus():
    p = current_path()
    if os.path.exists(p):
        try:
            return json.load(open(p)).get("initiative_id")
        except Exception:
            return None
    return None


def set_focus(iid, session=""):
    os.makedirs(str(base()), exist_ok=True)
    json.dump({"initiative_id": iid, "pinned_at": now_iso(), "session": session},
              open(current_path(), "w"), indent=2)


# ---- savepoint linkage -----------------------------------------------------
def link_savepoints(iid):
    """Symlink flat savepoints whose initiative_id==iid into savepoints/<id>/.
    Authoritative file stays flat (so the /wai resume menu still sees it)."""
    nd = sp_nested_dir(iid)
    os.makedirs(nd, exist_ok=True)
    linked = 0
    for f in glob.glob(os.path.join(sp_flat_dir(), "*.json")):
        try:
            if json.load(open(f)).get("initiative_id") != iid:
                continue
        except Exception:
            continue
        dst = os.path.join(nd, os.path.basename(f))
        if not os.path.lexists(dst):
            os.symlink(os.path.relpath(f, nd), dst)
            linked += 1
    return linked


def list_child_savepoints(iid):
    nd = sp_nested_dir(iid)
    out = []
    if os.path.isdir(nd):
        for f in sorted(glob.glob(os.path.join(nd, "*.json"))):
            try:
                d = json.load(open(f))
                out.append((d.get("id", os.path.basename(f)[:-5]),
                            d.get("status", "?"), d.get("where_we_are", "")[:70]))
            except Exception:
                out.append((os.path.basename(f)[:-5], "?", ""))
    return out


# ---- git helpers (for wake_on.commit_count) --------------------------------
def commit_count():
    try:
        return int(subprocess.run(["git", "-C", ROOT, "rev-list", "--count", "HEAD"],
                                  capture_output=True, text=True, timeout=10).stdout.strip() or 0)
    except Exception:
        return 0


# ---- verbs -----------------------------------------------------------------
def cmd_list(args):
    inits = store.load_all(ROOT)
    focus = get_focus()
    if not inits:
        print("  (no initiatives yet — create one: initiative_nav.py new <id> --title ...)")
        return
    print(f"\n  INITIATIVES ({len(inits)})   focus → {focus or '(none)'}\n")
    print(f"  {'':1} {'id':<34} {'state':<10} {'savepoints':>10}")
    print("  " + "-" * 60)
    for i in sorted(inits, key=lambda x: (x.get("lifecycle_state", ""), x.get("id", ""))):
        iid = i.get("id", "?")
        mark = "▶" if iid == focus else " "
        n = len(list_child_savepoints(iid))
        print(f"  {mark} {iid:<34} {i.get('lifecycle_state','?'):<10} {n:>10}")


def cmd_tree(args):
    inits = store.load_all(ROOT)
    focus = get_focus()
    ids = [args.id] if getattr(args, "id", None) else [i.get("id") for i in inits]
    for iid in ids:
        i = store.get(iid, ROOT)
        if not i:
            print(f"  {iid}: not found"); continue
        mark = " ▶" if iid == focus else ""
        wk = i.get("wake_on")
        wk_s = f"  wake_on={wk}" if wk else ""
        print(f"\n  ● {iid}  [{i.get('lifecycle_state','?')}]{mark}{wk_s}")
        cp = (i.get("current_position") or {}).get("summary")
        if cp:
            print(f"    position: {cp}")
        sps = list_child_savepoints(iid)
        if not sps:
            print("    └─ (no savepoints)")
        for n, (sid, st, where) in enumerate(sps):
            elbow = "└─" if n == len(sps) - 1 else "├─"
            print(f"    {elbow} ⏺ {sid}  [{st}]")
            if where:
                print(f"         {where}")


def cmd_show(args):
    i = store.get(args.id, ROOT)
    if not i:
        print(f"  {args.id}: not found"); return
    print(json.dumps(store._clean(i), indent=2))


def cmd_new(args):
    if store.get(args.id, ROOT):
        print(f"  {args.id} already exists"); return
    init = {
        "id": args.id,
        "label": args.title or args.id,
        "description": args.desc or "",
        "lifecycle_state": args.state,
        "impact_rank": args.rank,
        "owns": [],
        "revisit_cadence_days": 7,
        "current_position": {"summary": args.title or "", "updated_at": now_iso()},
        "created_at": now_iso(),
    }
    store.save(init, ROOT)
    print(f"  created {args.id} [{args.state}]  (propose-on-detect default = proposed)")


def _move(iid, new_state):
    i = store.get(iid, ROOT)
    if not i:
        print(f"  {iid}: not found"); return None
    store.save({**i, "lifecycle_state": new_state}, ROOT)
    return store.get(iid, ROOT)


def cmd_pin(args):
    if not store.get(args.id, ROOT):
        print(f"  {args.id}: not found"); return
    set_focus(args.id, os.environ.get("WAI_SESSION", ""))
    print(f"  focus pinned → {args.id}")


cmd_switch = cmd_pin


def cmd_sleep(args):
    i = store.get(args.id, ROOT)
    if not i:
        print(f"  {args.id}: not found"); return
    wake_on = {"reason": args.reason or ""}
    if args.until:
        u = args.until
        if u.startswith("+") and u.endswith("commits"):
            wake_on["commit_count"] = commit_count() + int(u[1:-7])
        elif u.startswith("event:"):
            wake_on["event"] = u[6:]
        else:
            wake_on["at"] = u
    i = {**i, "dormant_from": i.get("lifecycle_state", "active"),
         "dormant_since": now_iso(), "wake_on": wake_on}
    store.save(i, ROOT)
    _move(args.id, "dormant")
    print(f"  💤 {args.id} → dormant  wake_on={wake_on}")


def _do_wake(i):
    target = i.get("dormant_from") or "active"
    woke = {**i, "lifecycle_state": target, "wake_reason": (i.get("wake_on") or {}),
            "woke_at": now_iso()}
    woke.pop("wake_on", None)
    woke.pop("dormant_since", None)
    store.save(woke, ROOT)
    return target


def cmd_wake(args):
    i = store.get(args.id, ROOT)
    if not i:
        print(f"  {args.id}: not found"); return
    if i.get("lifecycle_state") != "dormant":
        print(f"  {args.id} is not dormant"); return
    t = _do_wake(i)
    print(f"  ☀ {args.id} woke → {t}")


def cmd_wake_check(args):
    """Steward logic — wake dormant initiatives whose wake_on has fired. Run
    manually now; Basher wires this into the nightly Ozi cycle."""
    now = now_iso()
    cc = commit_count()
    woke = []
    for i in store.load_all(ROOT):
        if i.get("lifecycle_state") != "dormant":
            continue
        w = i.get("wake_on") or {}
        fire = False
        if w.get("at") and now >= w["at"]:
            fire = True
        if w.get("commit_count") and cc >= w["commit_count"]:
            fire = True
        # event triggers need an external signal; left to explicit `wake`.
        if fire:
            t = _do_wake(i)
            woke.append((i.get("id"), t))
    if woke:
        for iid, t in woke:
            print(f"  ☀ woke {iid} → {t}")
    else:
        print(f"  wake-check: nothing due (now={now[:19]}, commits={cc})")
    return woke


def cmd_save(args):
    """Create a savepoint owned by an initiative (flat + nested symlink)."""
    if not store.get(args.id, ROOT):
        print(f"  {args.id}: not found"); return
    sid = f"sp-{os.environ.get('WAI_SESSION','manual')}-{args.slug or 'note'}"
    sp = {"id": sid, "schema_version": 2, "status": "pending",
          "initiative_id": args.id, "created_at": now_iso(),
          "where_we_are": args.note or "", "created_by": "initiative_nav.py"}
    os.makedirs(sp_flat_dir(), exist_ok=True)
    json.dump(sp, open(os.path.join(sp_flat_dir(), sid + ".json"), "w"), indent=2)
    n = link_savepoints(args.id)
    # refresh initiative current_position
    i = store.get(args.id, ROOT)
    i["current_position"] = {"summary": args.note or "", "updated_at": now_iso(),
                             "last_savepoint": sid}
    i["last_revisited_at"] = now_iso()
    store.save(i, ROOT)
    print(f"  ⏺ saved {sid} under {args.id}  (+{n} linked)")


def cmd_adopt(args):
    n = link_savepoints(args.id)
    print(f"  adopted {n} flat savepoint(s) (initiative_id={args.id}) into savepoints/{args.id}/")


def main():
    import argparse
    p = argparse.ArgumentParser(prog="initiative_nav.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    t = sub.add_parser("tree"); t.add_argument("id", nargs="?")
    s = sub.add_parser("show"); s.add_argument("id")
    n = sub.add_parser("new"); n.add_argument("id"); n.add_argument("--title"); n.add_argument("--desc")
    n.add_argument("--state", default="proposed"); n.add_argument("--rank", type=int, default=50)
    for verb in ("pin", "switch", "wake", "adopt"):
        sp = sub.add_parser(verb); sp.add_argument("id")
    sl = sub.add_parser("sleep"); sl.add_argument("id"); sl.add_argument("--until"); sl.add_argument("--reason")
    sv = sub.add_parser("save"); sv.add_argument("id"); sv.add_argument("--slug"); sv.add_argument("--note")
    sub.add_parser("wake-check")
    args = p.parse_args()
    {
        "list": cmd_list, "tree": cmd_tree, "show": cmd_show, "new": cmd_new,
        "pin": cmd_pin, "switch": cmd_switch, "sleep": cmd_sleep, "wake": cmd_wake,
        "save": cmd_save, "adopt": cmd_adopt, "wake-check": cmd_wake_check,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
