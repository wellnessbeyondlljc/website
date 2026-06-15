#!/usr/bin/env python3
"""
Lug Debt Scanner — commitment accounting + debt classification.
Usage: python3 scripts/lug_debt_scanner.py [--json]

Debt categories:
  abandoned            — started (in_progress or started_at set) but never closed; no activity for >72h
  deployed_unverified  — has deployed_at or outcome set but outcome_verification block absent/incomplete
  spec_drift           — outcome diverges from original intent (intent_honored=False in outcome_verification)
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LUGS_ROOT = Path("WAI-Spoke/lugs/bytype")
STALE_THRESHOLD_HOURS = 72
IMPL_TYPES = {"implementation", "feature", "task", "bug", "epic"}


def _parse_dt(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _age_hours(dt) -> float:
    if dt is None:
        return 0.0
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def scan_lugs():
    now = datetime.now(timezone.utc).isoformat()
    results = {
        "scanned_at": now,
        "abandoned": [],
        "deployed_unverified": [],
        "spec_drift": [],
        "stale_in_progress": [],   # kept for backwards compat
        "summary": {}
    }

    total = 0
    for lug_path in LUGS_ROOT.rglob("*.json"):
        try:
            lug = json.load(open(lug_path))
        except Exception:
            continue

        total += 1
        status = lug.get("status", "")
        lug_id = lug.get("id", lug_path.stem)
        lug_type = lug.get("type", "")
        title = lug.get("title", "")[:60]

        if lug_type not in IMPL_TYPES:
            continue

        # ── Abandoned ────────────────────────────────────────────────────────
        # started but never completed; last activity >72h ago
        if status in ("in_progress", "open"):
            started_at = lug.get("started_at") or lug.get("created_at")
            last_at = lug.get("last_updated") or lug.get("updated_at") or started_at
            age = _age_hours(_parse_dt(last_at))
            if status == "in_progress" and age > STALE_THRESHOLD_HOURS:
                entry = {"id": lug_id, "status": status, "age_hours": round(age), "title": title}
                results["abandoned"].append(entry)
                results["stale_in_progress"].append(entry)  # backwards compat

        # ── Deployed but unverified ───────────────────────────────────────────
        # has outcome or deployed_at but no outcome_verification block
        if status == "completed":
            has_outcome = bool(lug.get("outcome") or lug.get("deployed_at"))
            ov = lug.get("outcome_verification")
            if has_outcome and not ov:
                results["deployed_unverified"].append({
                    "id": lug_id,
                    "type": lug_type,
                    "title": title
                })
            elif has_outcome and isinstance(ov, dict):
                # Partial outcome_verification (deployed field absent)
                if not ov.get("deployed") and ov.get("deployed") is not True:
                    results["deployed_unverified"].append({
                        "id": lug_id,
                        "type": lug_type,
                        "title": title,
                        "note": "outcome_verification.deployed not confirmed"
                    })

        # ── Spec drift ───────────────────────────────────────────────────────
        # outcome_verification explicitly marks intent_honored=False
        ov = lug.get("outcome_verification")
        if isinstance(ov, dict) and ov.get("intent_honored") is False:
            results["spec_drift"].append({
                "id": lug_id,
                "type": lug_type,
                "status": status,
                "title": title,
                "notes": ov.get("notes", "")
            })

    results["summary"] = {
        "total_scanned": total,
        "abandoned_count": len(results["abandoned"]),
        "deployed_unverified_count": len(results["deployed_unverified"]),
        "spec_drift_count": len(results["spec_drift"]),
        "stale_in_progress_count": len(results["stale_in_progress"]),
        "debt_total": len(results["abandoned"]) + len(results["deployed_unverified"]) + len(results["spec_drift"])
    }
    return results


if __name__ == "__main__":
    results = scan_lugs()
    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))
    else:
        s = results["summary"]
        print(f"Lug Debt Scanner — {results['scanned_at'][:10]}")
        print(f"Scanned: {s['total_scanned']} impl-class lugs")
        print(f"Debt total: {s['debt_total']}")
        print(f"  Abandoned (in_progress >{STALE_THRESHOLD_HOURS}h): {s['abandoned_count']}")
        for item in results["abandoned"][:5]:
            print(f"    - {item['id']} ({item['age_hours']}h) {item['title']}")
        print(f"  Deployed unverified: {s['deployed_unverified_count']}")
        for item in results["deployed_unverified"][:3]:
            print(f"    - {item['id']} {item['title']}")
        print(f"  Spec drift (intent_honored=False): {s['spec_drift_count']}")
        for item in results["spec_drift"][:3]:
            print(f"    - {item['id']} {item['title']}")
