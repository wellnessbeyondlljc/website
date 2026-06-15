#!/usr/bin/env python3
"""check_public_sync.py — Detect drift between tools/ and shared/codebase/tools/.

The files listed in SHARED_FILES are intended to be identical in both locations.
Run this during closeout whenever tools/ is modified, or add to CI.

Usage:
    python3 tools/check_public_sync.py
    python3 tools/check_public_sync.py --fix   # copy tools/ → shared/codebase/tools/
"""

import sys
import hashlib
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "tools"
PUBLIC = ROOT / "shared" / "codebase" / "tools"

# Files that must be kept in sync between tools/ and shared/codebase/tools/.
# Does not include files that are private-only (advisor_report.py, spoke_*.py, etc.)
# or migration scripts (archived).
SHARED_FILES = [
    "advisor_context_refresh.py",
    "advisor_schedule_eval.py",
    "cc_advisor.py",
    "closeout.sh",
    "enrich_lugs.py",
    "gemini_advisor.py",
    "historian_scan.py",
    "human_hours.py",
    "lathe_score.py",
    "luci_check.py",
    "lug_utils.py",
    "pre_commit_health.py",
    "schedule_advisor.py",
    "score_backlog.py",
    "security_scan.py",
    "tag_vibe_affinity.py",
    "tool_advisor.py",
    "wai-chain.sh",
    "wai_validate.py",
    "write_assay.py",
    "write_cartographer_obs.py",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Check tools/ vs shared/codebase/tools/ for drift")
    parser.add_argument("--fix", action="store_true", help="Copy diverged files from tools/ to shared/codebase/tools/")
    args = parser.parse_args()

    drifted = []
    missing_private = []
    missing_public = []

    for name in SHARED_FILES:
        priv = PRIVATE / name
        pub = PUBLIC / name

        if not priv.exists():
            missing_private.append(name)
            continue
        if not pub.exists():
            missing_public.append(name)
            continue

        if sha256(priv) != sha256(pub):
            drifted.append(name)

    clean = True

    if missing_private:
        clean = False
        print("MISSING from tools/ (unexpected):")
        for f in missing_private:
            print(f"  {f}")

    if missing_public:
        clean = False
        print("MISSING from shared/codebase/tools/ (needs add):")
        for f in missing_public:
            print(f"  {f}")
        if args.fix:
            for f in missing_public:
                import shutil
                shutil.copy2(PRIVATE / f, PUBLIC / f)
                print(f"  [FIXED] copied {f}")

    if drifted:
        clean = False
        print("DRIFTED (tools/ is newer — shared/ needs update):")
        for f in drifted:
            print(f"  {f}")
        if args.fix:
            import shutil
            for f in drifted:
                shutil.copy2(PRIVATE / f, PUBLIC / f)
                print(f"  [FIXED] synced {f}")

    if clean:
        print("OK — tools/ and shared/codebase/tools/ are in sync.")
        sys.exit(0)
    else:
        if not args.fix:
            print("\nRun with --fix to sync tools/ → shared/codebase/tools/")
        sys.exit(1 if not args.fix else 0)


if __name__ == "__main__":
    main()
