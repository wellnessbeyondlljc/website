#!/usr/bin/env python3
"""classify_delta_ceremony.py — deterministic extraction of the wai-closeout
"### 2b. Delta Ceremony Detection" inline block (P2 of
initiative-optimize-ceremonies-v1).

Classifies a re-closeout into a delta class (FULL / MICRO / PATCH / STANDARD)
and emits the skip flags + CONVERSATION_ONLY that the rest of the closeout
ceremony consumes. Faithful reproduction of the inline Python the ceremony
used to run — NO new logic.

Source of truth for behaviour:
  WAI-Harness/spoke/managed/.claude/commands/wai-closeout.md
  section "### 2b. Delta Ceremony Detection".

CLI:
  python3 classify_delta_ceremony.py --base BASE [--session-id SID] [--json]

  --base        the resolved spoke BASE dir (the value the ceremony substitutes
                for {BASE}). Runtime + state files are read under it; it is also
                the literal path prefix used to detect "state-only" diffs, exactly
                as the inline block did after {BASE} substitution.
  --session-id  override the current session id (default: read from
                {BASE}/runtime/session-guard.json -> session_id).
  --json        print the result as a JSON object (default).

Output (JSON object) keys — same classification + flags the inline block set:
  DELTA_CLASS, SKIP_VERSION_BUMP, SKIP_TEST_GATE, SKIP_CHANGELOG,
  SKIP_TEACHINGS, SKIP_SKILL_SYNC, SKIP_TELEMETRY, SKIP_BRIEFS,
  CONVERSATION_ONLY
The boolean values are JSON booleans (the inline block printed them as the
lowercase strings "true"/"false" for `export`; --json gives real booleans, which
is the faithful machine-readable form of the same values).
"""
import argparse
import json
import os
import subprocess
import sys


def classify(base, session_id=None, root="."):
    """Return the delta-classification dict. Faithful port of the inline block.
    `root` is the git repo dir the ceremony runs from (default cwd = spoke root).

    `base` is the substituted {BASE}. It is used both to locate runtime/state
    files AND as the literal string prefix for the state-only diff test, exactly
    as the inline block did (it tested `f.startswith('{BASE}/')`).
    """
    fingerprint_path = os.path.join(base, "runtime", "closeout-fingerprint.json")
    session_guard_path = os.path.join(base, "runtime", "session-guard.json")

    # Read current session ID
    current_session = session_id
    if current_session is None:
        try:
            current_session = json.load(open(session_guard_path)).get("session_id")
        except Exception:
            current_session = None

    # Defaults — assume FULL (no fingerprint or cross-session)
    DELTA_CLASS = "FULL"
    SKIP_VERSION_BUMP = False
    SKIP_TEST_GATE = False
    SKIP_CHANGELOG = False
    SKIP_TEACHINGS = False
    SKIP_SKILL_SYNC = False
    SKIP_TELEMETRY = False
    SKIP_BRIEFS = False
    CONVERSATION_ONLY = False

    # Literal path prefix the inline block used after {BASE} substitution.
    base_prefix = base.rstrip("/") + "/"

    if os.path.exists(fingerprint_path) and current_session:
        fp = json.load(open(fingerprint_path))
        same_session = fp.get("session_id") == current_session
        if same_session:
            SKIP_VERSION_BUMP = True  # always skip on re-closeout within same session
            # Classify delta since last closeout
            last_sha = fp.get("last_closeout_sha", "")
            if last_sha:
                result = subprocess.run(
                    ["git", "diff", "--name-only", last_sha, "HEAD"],
                    capture_output=True, text=True, cwd=root,
                )
                changed = [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
                # Classify
                state_only = all(
                    f.startswith(base_prefix) and any(f.endswith(x) for x in [".json", ".jsonl"])
                    for f in changed
                )
                has_py_sh = any(f.endswith((".py", ".sh")) or "tools/" in f for f in changed)
                has_docs = any(f.endswith((".md", ".yaml", ".yml")) for f in changed)
                if not changed or state_only:
                    DELTA_CLASS = "MICRO"
                    SKIP_TEST_GATE = True
                    SKIP_CHANGELOG = True
                    SKIP_TEACHINGS = True
                    SKIP_SKILL_SYNC = True
                    SKIP_TELEMETRY = True
                    SKIP_BRIEFS = True
                elif has_py_sh:
                    DELTA_CLASS = "STANDARD"
                    SKIP_CHANGELOG = False
                elif has_docs:
                    DELTA_CLASS = "PATCH"
                    SKIP_TEACHINGS = True

    # CONVERSATION_ONLY: no code/doc/template changes this session
    if DELTA_CLASS != "MICRO":
        session_start_sha = None
        try:
            if os.path.exists(session_guard_path):
                session_start_sha = json.load(open(session_guard_path)).get("session_start_sha")
        except Exception:
            session_start_sha = None
        if session_start_sha:
            r = subprocess.run(
                ["git", "diff", "--name-only", session_start_sha, "HEAD"],
                capture_output=True, text=True, cwd=root,
            )
            session_changed = [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]
        else:
            r = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"], capture_output=True, text=True, cwd=root,
            )
            session_changed = [f.strip() for f in r.stdout.strip().splitlines() if f.strip()]
        code_or_doc = [
            f for f in session_changed
            if f.endswith((".py", ".sh", ".js", ".ts", ".jsx", ".tsx",
                           ".md", ".yaml", ".yml"))
            or "tools/" in f or "templates/" in f
        ]
        if not code_or_doc:
            CONVERSATION_ONLY = True

    SKIP_TEST_GATE = SKIP_TEST_GATE or CONVERSATION_ONLY

    return {
        "DELTA_CLASS": DELTA_CLASS,
        "SKIP_VERSION_BUMP": SKIP_VERSION_BUMP,
        "SKIP_TEST_GATE": SKIP_TEST_GATE,
        "SKIP_CHANGELOG": SKIP_CHANGELOG,
        "SKIP_TEACHINGS": SKIP_TEACHINGS,
        "SKIP_SKILL_SYNC": SKIP_SKILL_SYNC,
        "SKIP_TELEMETRY": SKIP_TELEMETRY,
        "SKIP_BRIEFS": SKIP_BRIEFS,
        "CONVERSATION_ONLY": CONVERSATION_ONLY,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Classify a (re-)closeout delta ceremony.")
    ap.add_argument("--base", required=True, help="resolved spoke BASE dir ({BASE} substitution)")
    ap.add_argument("--session-id", default=None, help="override current session id")
    ap.add_argument("--root", default=".", help="git repo dir (default cwd = spoke root)")
    ap.add_argument("--json", action="store_true", default=True,
                    help="emit JSON (default; kept for explicitness)")
    args = ap.parse_args(argv)

    result = classify(args.base, session_id=args.session_id, root=args.root)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
