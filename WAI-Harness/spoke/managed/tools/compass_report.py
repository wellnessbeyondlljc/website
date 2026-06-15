#!/usr/bin/env python3
"""Compass — Dynamic fleet dashboard and morning brief.

Reads Lathe weights, Gardener health, session tracks, and spoke changelogs
to produce an HTML dashboard with decisions, productivity metrics, and
attention alignment.

Usage:
    python3 tools/compass_report.py [--hub-path PATH] [--open]

Generates WAI-Hub/advisors/compass/reports/dashboard-YYYY-MM-DD.html
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

_p = argparse.ArgumentParser(description="Compass — Dynamic fleet dashboard and morning brief.")
_p.add_argument("--hub-path", default=os.environ.get("WAI_HUB_PATH", ""), metavar="PATH", help="Path to hub root")
_p.add_argument("--open", action="store_true", help="Open dashboard in browser after generating")
_a = _p.parse_args()
HUB_PATH = Path(_a.hub_path)
OPEN_BROWSER = _a.open

COMPASS_DIR = HUB_PATH / "WAI-Hub/advisors/compass"
REPORTS_DIR = COMPASS_DIR / "reports"
DECISIONS_LOG = COMPASS_DIR / "decisions.jsonl"


def ensure_dirs():
    COMPASS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)


def load_registry():
    """Load spoke registry from hub."""
    reg = HUB_PATH / "WAI-Hub/registry/hub-registry.json"
    if reg.exists():
        return json.loads(reg.read_text())
    # Scan incoming
    incoming = HUB_PATH / "WAI-Hub/registry/incoming"
    spokes = {}
    if incoming.exists():
        for f in incoming.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                spokes[data.get("spoke_id", f.stem)] = data
            except (json.JSONDecodeError, OSError):
                pass
    return spokes


def load_lathe():
    """Load Lathe portfolio config."""
    path = HUB_PATH / "WAI-Hub/advisors/lathe/spoke_lathe.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"spokes": {}}


def load_changelogs():
    """Load spoke changelogs for recent completions."""
    entries = []
    # Check each spoke dir for changelog
    for spoke_dir in (HUB_PATH / "..").glob("*/WAI-Spoke/runtime/spoke-changelog.jsonl"):
        try:
            for line in spoke_dir.read_text().splitlines():
                if line.strip():
                    entries.append(json.loads(line.strip()))
        except:
            pass
    # Also check hub changelogs
    hub_log = HUB_PATH / "WAI-Hub/changelog.jsonl"
    if hub_log.exists():
        try:
            for line in hub_log.read_text().splitlines():
                if line.strip():
                    entries.append(json.loads(line.strip()))
        except:
            pass
    return sorted(entries, key=lambda x: x.get("ts", ""), reverse=True)


def load_signals():
    """Load recent hub signals for decision queue."""
    signals = []
    incoming = HUB_PATH / "WAI-Hub/signals/incoming"
    if incoming.exists():
        for f in sorted(incoming.glob("*.json"))[-20:]:  # last 20
            try:
                signals.append(json.loads(f.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
    return signals


def generate_html(registry, lathe, changelogs, signals):
    """Generate the HTML dashboard."""
    now = datetime.now(tz=None)
    date_str = now.strftime("%Y-%m-%d")
    spoke_count = len(registry)
    recent_completions = changelogs[:10]
    pending_signals = len(signals)

    # Spoke rows
    spoke_rows = ""
    for spoke_id, data in sorted(registry.items()):
        name = data.get("name", spoke_id)
        version = data.get("version", "?")
        sessions = data.get("session_count", 0)
        last = data.get("last_closeout", "never")[:10]
        shift = lathe.get("spokes", {}).get(spoke_id, {}).get("shift_direction", "maintain")
        shift_colors = {
            "growth": "#4ade80", "revenue": "#fbbf24", "research": "#818cf8",
            "maintain": "#94a3b8", "sunset": "#f87171"
        }
        color = shift_colors.get(shift, "#94a3b8")
        spoke_rows += f"""
        <tr>
            <td>{name}</td>
            <td>v{version}</td>
            <td>{sessions}</td>
            <td>{last}</td>
            <td><span style="background:{color};padding:2px 8px;border-radius:4px;color:#000;font-size:0.85em">{shift}</span></td>
        </tr>"""

    # Completion rows
    completion_rows = ""
    for entry in recent_completions[:5]:
        ts = entry.get("ts", "")[:10]
        title = entry.get("title", "")[:50]
        result = entry.get("result", "?")
        result_color = "#4ade80" if result == "completed" else "#f87171"
        completion_rows += f"""
        <tr>
            <td>{ts}</td>
            <td>{title}</td>
            <td><span style="color:{result_color}">{result}</span></td>
        </tr>"""

    # Signal decision rows
    signal_rows = ""
    for sig in signals[:5]:
        title = sig.get("t", sig.get("title", ""))[:50]
        impact = sig.get("impact", "?")
        signal_rows += f"""
        <tr>
            <td>{title}</td>
            <td>{impact}</td>
            <td>
                <button onclick="decide('{sig.get('i', '')}', 'approve')" style="background:#4ade80;border:none;padding:4px 8px;border-radius:3px;cursor:pointer">Approve</button>
                <button onclick="decide('{sig.get('i', '')}', 'defer')" style="background:#fbbf24;border:none;padding:4px 8px;border-radius:3px;cursor:pointer">Defer</button>
            </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Compass — Fleet Dashboard {date_str}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }}
        .header {{ text-align: center; padding: 20px 0; border-bottom: 1px solid #334155; margin-bottom: 20px; }}
        .header h1 {{ font-size: 2em; color: #f8fafc; }}
        .header .subtitle {{ color: #94a3b8; margin-top: 5px; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 16px; border: 1px solid #334155; }}
        .card h2 {{ font-size: 1.1em; color: #cbd5e1; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #334155; }}
        .metric {{ font-size: 2.5em; font-weight: bold; color: #f8fafc; }}
        .metric-label {{ color: #94a3b8; font-size: 0.85em; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; color: #94a3b8; font-size: 0.85em; padding: 6px 8px; border-bottom: 1px solid #334155; }}
        td {{ padding: 6px 8px; border-bottom: 1px solid #1e293b; }}
        .full-width {{ grid-column: 1 / -1; }}
        .stats {{ display: flex; gap: 30px; justify-content: center; margin: 15px 0; }}
        .stat {{ text-align: center; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Compass</h1>
        <div class="subtitle">Fleet Dashboard — {date_str} — {spoke_count} spokes</div>
    </div>

    <div class="stats">
        <div class="stat">
            <div class="metric">{spoke_count}</div>
            <div class="metric-label">Spokes</div>
        </div>
        <div class="stat">
            <div class="metric">{len(recent_completions)}</div>
            <div class="metric-label">Recent Completions</div>
        </div>
        <div class="stat">
            <div class="metric">{pending_signals}</div>
            <div class="metric-label">Pending Signals</div>
        </div>
    </div>

    <div class="grid">
        <div class="card full-width">
            <h2>Fleet Status</h2>
            <table>
                <tr><th>Spoke</th><th>Version</th><th>Sessions</th><th>Last Active</th><th>Shift</th></tr>
                {spoke_rows if spoke_rows else '<tr><td colspan="5" style="color:#64748b">No spokes registered yet. Run closeout with Step 9d to populate.</td></tr>'}
            </table>
        </div>

        <div class="card">
            <h2>Recent Completions</h2>
            <table>
                <tr><th>Date</th><th>Title</th><th>Result</th></tr>
                {completion_rows if completion_rows else '<tr><td colspan="3" style="color:#64748b">No completions yet. Spoke changelogs feed this.</td></tr>'}
            </table>
        </div>

        <div class="card">
            <h2>Decision Queue</h2>
            <table>
                <tr><th>Signal</th><th>Impact</th><th>Action</th></tr>
                {signal_rows if signal_rows else '<tr><td colspan="3" style="color:#64748b">No pending decisions.</td></tr>'}
            </table>
        </div>
    </div>

    <div style="text-align:center;color:#64748b;margin-top:20px;font-size:0.85em">
        Generated by Compass — Wheelwright Fleet Dashboard<br>
        {now.strftime("%Y-%m-%d %H:%M UTC")}
    </div>

    <script>
    function decide(id, action) {{
        // In a real implementation, this would write to decisions.jsonl
        alert('Decision: ' + action + ' on ' + id + '\\nIn production, this writes to decisions.jsonl');
    }}
    </script>
</body>
</html>"""
    return html, date_str


def main():
    ensure_dirs()

    registry = load_registry()
    lathe = load_lathe()
    changelogs = load_changelogs()
    signals = load_signals()

    html, date_str = generate_html(registry, lathe, changelogs, signals)

    output_path = REPORTS_DIR / f"dashboard-{date_str}.html"
    output_path.write_text(html)
    print(f"Dashboard generated: {output_path}")
    print(f"  Spokes: {len(registry)}")
    print(f"  Completions: {len(changelogs)}")
    print(f"  Pending signals: {len(signals)}")

    # Write scan state
    scan_state = {
        "advisor_id": "compass",
        "advisor_name": "Compass — Fleet Dashboard & Decision Engine",
        "version": "1.0.0",
        "mission_statement": "Surface what matters across all spokes — decisions, alignment, productivity — so the user sees the whole wheel at once",
        "last_scan_at": datetime.now(tz=None).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reports_generated": 1,
        "data_sources": [
            {"source": "WAI-Hub/registry/", "fields_used": ["spoke_id", "name", "version", "session_count"], "adequacy": "good"},
            {"source": "WAI-Hub/advisors/lathe/spoke_lathe.json", "fields_used": ["shift_direction", "budget"], "adequacy": "partial"},
            {"source": "*/WAI-Spoke/runtime/spoke-changelog.jsonl", "fields_used": ["ts", "title", "result"], "adequacy": "partial"},
            {"source": "WAI-Hub/signals/incoming/", "fields_used": ["title", "impact"], "adequacy": "good"},
            {"source": "taste.user.yaml", "fields_used": ["tone", "communication"], "adequacy": "missing"}
        ],
        "self_sharpening_log": []
    }
    (COMPASS_DIR / "scan_state.json").write_text(json.dumps(scan_state, indent=2) + "\n")

    if OPEN_BROWSER:
        import webbrowser
        webbrowser.open(f"file://{output_path.resolve()}")
        print("  Opened in browser")


if __name__ == "__main__":
    main()
