#!/usr/bin/env python3
"""Partial-Staging Recovery Pre-Flight (extracted from wai-closeout.md Step 10g).

Checks for an in-progress closeout buffer from a prior interrupted attempt in
this session. If a valid partial staging buffer is found, harvest its draft
state instead of recomposing. Then (re)mark the staging buffer as 'partial' so
the closeout has an idempotent recovery point until it flips to 'closeout'
after commit.

Faithful reproduction of the inline python block. CLI:
    python3 recover_partial_staging.py --base BASE

Prints JSON to stdout:
    {"recovered": bool, "items": [str, ...]}

  - recovered: True when a prior partial staging buffer was found and harvested.
  - items: human-readable harvest messages (empty when nothing recovered).

Quiet (empty JSON {"recovered": false, "items": []}) when nothing to recover.
"""
import argparse
import datetime
import json
import os
from datetime import timezone


def recover_partial_staging(base: str) -> dict:
    """Harvest a prior partial staging buffer, then (re)mark staging as partial.

    Mirrors wai-closeout.md Step 10g exactly.
    """
    recovered = False
    items = []

    staging_path = os.path.join(base, 'runtime', 'closeout-staging.json')
    if os.path.exists(staging_path):
        try:
            s = json.load(open(staging_path))
            if s.get('type') == 'partial':
                recovered = True
                items.append(
                    "[closeout] Partial staging buffer found — harvesting draft state"
                )
                items.append(
                    f"  Prior draft: version={s.get('version', '?')}, "
                    f"session={s.get('session_id', '?')}"
                )
                # DRAFT_COMMIT_MESSAGE and STAGED_VERSION from s can be reused below
        except Exception:
            pass

    # Mark as partial now — updated to 'closeout' after commit (idempotent recovery point)
    try:
        session_id = json.load(
            open(os.path.join(base, 'runtime', 'session-guard.json'))
        ).get('session_id', 'unknown')
    except Exception:
        session_id = 'unknown'
    partial = {
        'type': 'partial',
        'session_id': session_id,
        'started_at': datetime.datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(os.path.join(base, 'runtime'), exist_ok=True)
    with open(staging_path, 'w') as f:
        json.dump(partial, f, indent=2)

    return {'recovered': recovered, 'items': items}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Partial-Staging Recovery Pre-Flight (wai-closeout Step 10g)."
    )
    ap.add_argument('--base', required=True, help='Spoke BASE directory (resolved v4/v3 base).')
    args = ap.parse_args()

    result = recover_partial_staging(args.base)
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
