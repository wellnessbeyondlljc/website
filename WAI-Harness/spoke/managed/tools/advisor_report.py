#!/usr/bin/env python3
"""Advisor Visibility Report — aggregates advisor run history, department membership,
and lug attribution into a structured JSON snapshot."""

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def generate_report(project_root: str) -> dict:
    root = Path(project_root)
    advisors_dir = root / "WAI-Spoke" / "advisors"

    registry = json.loads((advisors_dir / "registry.json").read_text())
    departments = json.loads((advisors_dir / "departments.json").read_text())

    source_registry_path = advisors_dir / "source-registry.json"
    sources = json.loads(source_registry_path.read_text()) if source_registry_path.exists() else []

    # Build advisor → department reverse map
    advisor_dept: dict[str, str | None] = {a["advisor_id"]: None for a in registry}
    for dept in departments:
        for aid in dept.get("advisor_ids", []):
            advisor_dept[aid] = dept["department_id"]

    # Count runs per advisor
    runs_by_advisor: dict[str, int] = {a["advisor_id"]: 0 for a in registry}
    for runs_file in glob.glob(str(advisors_dir / "*" / "runs.jsonl")):
        advisor_id = Path(runs_file).parent.name
        count = 0
        with open(runs_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    count += 1
        if advisor_id in runs_by_advisor:
            runs_by_advisor[advisor_id] += count
        else:
            runs_by_advisor[advisor_id] = count

    # Count attributed lugs and sum ROI per advisor
    attributed_count: dict[str, int] = {a["advisor_id"]: 0 for a in registry}
    roi_sum: dict[str, float] = {a["advisor_id"]: 0.0 for a in registry}
    total_attributed = 0

    for lug_file in glob.glob(str(root / "WAI-Spoke" / "lugs" / "bytype" / "**" / "*.json"), recursive=True):
        try:
            lug = json.loads(Path(lug_file).read_text())
        except (json.JSONDecodeError, OSError):
            continue
        creator = lug.get("created_by_advisor")
        if not creator:
            continue
        total_attributed += 1
        if creator in attributed_count:
            attributed_count[creator] += 1
            roi_sum[creator] += float(lug.get("roi", 0) or 0)

    total_runs = sum(runs_by_advisor.values())
    active_advisors = sum(1 for a in registry if a.get("status") == "active")
    attribution_pct = round(total_attributed / len(registry) * 100, 1) if registry else 0.0

    # Department aggregates
    dept_runs: dict[str, int] = {}
    dept_lugs: dict[str, int] = {}
    for dept in departments:
        did = dept["department_id"]
        dept_runs[did] = sum(runs_by_advisor.get(aid, 0) for aid in dept.get("advisor_ids", []))
        dept_lugs[did] = sum(attributed_count.get(aid, 0) for aid in dept.get("advisor_ids", []))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_advisors": len(registry),
            "active_advisors": active_advisors,
            "total_departments": len(departments),
            "total_runs": total_runs,
            "attributed_lugs": total_attributed,
            "attribution_pct": attribution_pct,
        },
        "departments": [
            {
                "department_id": dept["department_id"],
                "title": dept["title"],
                "advisor_count": len(dept.get("advisor_ids", [])),
                "total_runs": dept_runs[dept["department_id"]],
                "attributed_lugs": dept_lugs[dept["department_id"]],
            }
            for dept in departments
        ],
        "advisors": [
            {
                "advisor_id": a["advisor_id"],
                "title": a["title"],
                "status": a.get("status", "unknown"),
                "department_id": advisor_dept.get(a["advisor_id"]),
                "run_count": runs_by_advisor.get(a["advisor_id"], 0),
                "attributed_lug_count": attributed_count.get(a["advisor_id"], 0),
                "roi_contribution": round(roi_sum.get(a["advisor_id"], 0.0), 2),
            }
            for a in registry
        ],
        "sources": [
            {
                "source_id": s["source_id"],
                "type": s.get("type", "unknown"),
                "advisors_using_count": len(s.get("advisors_using", [])),
            }
            for s in sources
        ],
    }


def print_summary(report: dict) -> None:
    s = report["summary"]
    print(f"\nAdvisor Visibility Report — {report['generated_at'][:19]}Z")
    print(f"Advisors: {s['total_advisors']} total, {s['active_advisors']} active | "
          f"Runs: {s['total_runs']} | Attributed lugs: {s['attributed_lugs']} ({s['attribution_pct']}%)")

    print("\nDEPARTMENTS")
    print(f"  {'ID':<20} {'Title':<20} {'Advisors':>8} {'Runs':>6} {'Lugs':>6}")
    print(f"  {'-'*20} {'-'*20} {'-'*8} {'-'*6} {'-'*6}")
    for dept in report["departments"]:
        print(f"  {dept['department_id']:<20} {dept['title']:<20} "
              f"{dept['advisor_count']:>8} {dept['total_runs']:>6} {dept['attributed_lugs']:>6}")

    print("\nTOP ADVISORS")
    advisors = sorted(report["advisors"], key=lambda a: a["roi_contribution"], reverse=True)
    print(f"  {'ID':<20} {'Dept':<15} {'Runs':>6} {'ROI':>7}")
    print(f"  {'-'*20} {'-'*15} {'-'*6} {'-'*7}")
    for a in advisors[:10]:
        dept = a["department_id"] or "-"
        print(f"  {a['advisor_id']:<20} {dept:<15} {a['run_count']:>6} {a['roi_contribution']:>7.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Advisor Visibility Report")
    parser.add_argument("--json", action="store_true", default=True,
                        help="Write visibility-report.json (default)")
    parser.add_argument("--print-summary", action="store_true",
                        help="Print human-readable summary table to stdout")
    parser.add_argument("--project-root", default=".",
                        help="Project root directory (default: .)")
    args = parser.parse_args()

    report = generate_report(args.project_root)

    if args.print_summary:
        print_summary(report)
        return

    out_path = Path(args.project_root) / "WAI-Spoke" / "advisors" / "visibility-report.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(str(out_path))


if __name__ == "__main__":
    main()
