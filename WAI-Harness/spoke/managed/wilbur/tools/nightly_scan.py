#!/usr/bin/env python3
"""
Wilbur Nightly Scan — Incremental PathGraph Update + Spoke Bubble-Up

Recurring job that:
1. Reads only new sessions since last_scan_at from each spoke
2. Extracts aspirations and decisions from those sessions
3. Appends them to PathGraph.json (append-only)
4. Identifies important items (bubbles) to surface to Mario
5. Routes them through notification escalation
6. Updates ScanState.json with progress

Gated by: archaeology_complete check per spoke
Append-only: Never overwrites existing PathGraph entries
"""

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import glob
import re

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/tmp/wilbur_nightly_scan.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)


class NightlyScan:
    def __init__(self, framework_root: str):
        self.framework_root = Path(framework_root)
        self.wilbur_root = self.framework_root / 'wilbur'
        self.hub_root = Path(self.framework_root.parent) / 'hub'

        self.scanstate_path = self.wilbur_root / 'ScanState.json'
        self.hub_registry_path = self.hub_root / 'hub-registry.json'

        self.scanstate = self._load_scanstate()
        self.hub_registry = self._load_hub_registry()

    def _load_scanstate(self) -> Dict[str, Any]:
        if not self.scanstate_path.exists():
            log.warning(f'ScanState.json not found at {self.scanstate_path}')
            return {'spokes': {}}

        with open(self.scanstate_path) as f:
            return json.load(f)

    def _load_hub_registry(self) -> Dict[str, Any]:
        if not self.hub_registry_path.exists():
            log.error(f'hub-registry.json not found at {self.hub_registry_path}')
            return {'wheels': []}

        with open(self.hub_registry_path) as f:
            return json.load(f)

    def _get_spokes(self) -> List[Dict[str, str]]:
        """Extract active spokes from hub-registry."""
        spokes = []
        for wheel in self.hub_registry.get('wheels', []):
            if wheel.get('status') in ['active', 'idle']:
                spokes.append({
                    'spoke_id': wheel.get('spoke_id') or wheel.get('wheel_id'),
                    'path': wheel.get('path'),
                    'name': wheel.get('name', wheel.get('foundation_name', 'unknown'))
                })
        return spokes

    def _check_archaeology_gate(self, spoke_path: str) -> bool:
        """Check if archaeology_complete: true in {spoke}/WAI-Spoke/PathGraph.json."""
        pathgraph_path = Path(spoke_path) / 'WAI-Spoke' / 'PathGraph.json'

        if not pathgraph_path.exists():
            log.warning(f'  {spoke_path}: PathGraph.json not found (archaeology pending)')
            return False

        try:
            with open(pathgraph_path) as f:
                pathgraph = json.load(f)
            archaeology_complete = pathgraph.get('metadata', {}).get('archaeology_complete', False)
            if not archaeology_complete:
                log.info(f'  {spoke_path}: archaeology_complete=false, skipping incremental scan')
            return archaeology_complete
        except (json.JSONDecodeError, IOError) as e:
            log.error(f'  {spoke_path}: Failed to read PathGraph.json: {e}')
            return False

    def _find_new_sessions(self, spoke_path: str, last_scan_at: Optional[str]) -> List[Dict[str, Any]]:
        """Find session directories newer than last_scan_at."""
        sessions_dir = Path(spoke_path) / 'WAI-Spoke' / 'sessions'

        if not sessions_dir.exists():
            return []

        new_sessions = []
        last_scan_time = None

        if last_scan_at:
            try:
                last_scan_time = datetime.fromisoformat(last_scan_at.replace('Z', '+00:00'))
            except ValueError:
                log.warning(f'  Could not parse last_scan_at: {last_scan_at}')

        for session_dir in sorted(sessions_dir.glob('session-*')):
            if not session_dir.is_dir():
                continue

            # Try to extract timestamp from session ID (session-YYYYMMDD-HHMM)
            match = re.match(r'session-(\d{8})-(\d{4})', session_dir.name)
            if not match:
                continue

            try:
                date_str, time_str = match.groups()
                session_time = datetime.strptime(f'{date_str} {time_str}', '%Y%m%d %H%M')

                if last_scan_time is None or session_time > last_scan_time:
                    new_sessions.append({
                        'path': session_dir,
                        'id': session_dir.name,
                        'timestamp': session_time.isoformat()
                    })
            except ValueError:
                continue

        return new_sessions

    def _extract_aspirations(self, session_path: Path) -> List[Dict[str, Any]]:
        """Extract aspirations from session track.jsonl."""
        track_file = session_path / 'track.jsonl'
        aspirations = []

        if not track_file.exists():
            return aspirations

        try:
            with open(track_file) as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                        # Extract from focus, action, insights, open items
                        aspiration = self._parse_aspiration_from_event(event, session_path.name)
                        if aspiration:
                            aspirations.append(aspiration)
                    except json.JSONDecodeError:
                        continue
        except IOError:
            pass

        return aspirations

    def _parse_aspiration_from_event(self, event: Dict[str, Any], session_id: str) -> Optional[Dict[str, Any]]:
        """Parse aspiration text from a track event."""
        focus = event.get('focus', '')
        action = event.get('action', '')
        open_items = event.get('open', [])

        # Look for goal language
        goal_keywords = ['should', 'need to', 'will', 'plan to', 'goal', 'want', 'aim', 'focus on']

        # Combine text to search
        full_text = f'{focus} {action}'.lower()

        has_goal_language = any(kw in full_text for kw in goal_keywords)

        if has_goal_language or (action and len(action.strip()) > 10):
            text = action if action else focus
            if not text or len(text.strip()) < 10:
                return None

            # Determine confidence level
            confidence = 'explicit' if any(kw in full_text for kw in ['will', 'should']) else 'inferred'

            return {
                'id': f'aspiration-nightly-{session_id[-8:]}',
                'source_session': session_id,
                'extracted_at': datetime.utcnow().isoformat() + 'Z',
                'text': text[:200],  # Truncate to 200 chars
                'confidence': confidence,
                'status': 'open',
                'drift_level': None,
                'fulfilled_session': None,
                'tags': ['nightly-scan']
            }

        return None

    def _append_to_pathgraph(self, spoke_path: str, aspirations: List[Dict[str, Any]]) -> int:
        """Append new aspirations to PathGraph.json (append-only)."""
        if not aspirations:
            return 0

        pathgraph_path = Path(spoke_path) / 'WAI-Spoke' / 'PathGraph.json'

        if not pathgraph_path.exists():
            log.warning(f'  PathGraph.json missing, skipping append')
            return 0

        try:
            with open(pathgraph_path) as f:
                pathgraph = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            log.error(f'  Failed to read PathGraph.json: {e}')
            return 0

        # Initialize aspirations array if missing
        if 'aspirations' not in pathgraph:
            pathgraph['aspirations'] = []

        # Append new aspirations (never overwrite)
        count_before = len(pathgraph['aspirations'])
        pathgraph['aspirations'].extend(aspirations)
        count_added = len(pathgraph['aspirations']) - count_before

        try:
            with open(pathgraph_path, 'w') as f:
                json.dump(pathgraph, f, indent=2)
            log.info(f'  Appended {count_added} aspirations to PathGraph.json')
            return count_added
        except IOError as e:
            log.error(f'  Failed to write PathGraph.json: {e}')
            return 0

    def _identify_bubbles(self, spoke_path: str, spoke_id: str) -> List[Dict[str, Any]]:
        """Identify important items (bubbles) to surface."""
        bubbles = []

        # Check for blocked lugs
        lugs_dir = Path(spoke_path) / 'WAI-Spoke' / 'lugs' / 'bytype'
        if lugs_dir.exists():
            for lug_file in lugs_dir.glob('**/in_progress/*.json'):
                try:
                    with open(lug_file) as f:
                        lug = json.load(f)

                    blocked_by = lug.get('blocked_by', [])
                    if blocked_by:
                        impact = lug.get('impact', 5)
                        bubbles.append({
                            'spoke': spoke_id,
                            'level': 'SURFACE' if impact >= 7 else 'INFO',
                            'item': f"{lug.get('title', 'unnamed lug')} blocked by {len(blocked_by)} item(s)",
                            'cost_of_delay': impact,
                            'days_stalled': 0,
                            'type': 'blocked_lug'
                        })
                except (json.JSONDecodeError, IOError):
                    continue

        return bubbles

    def _score_bubbles(self, bubbles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Score bubbles by urgency."""
        for bubble in bubbles:
            score = (
                bubble.get('cost_of_delay', 5) *
                (1.1 if bubble.get('level') == 'SURFACE' else 1.0)
            )
            bubble['urgency_score'] = score

        return sorted(bubbles, key=lambda b: b.get('urgency_score', 0), reverse=True)

    def _produce_bubble_report(self, bubbles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Produce structured bubble-up report."""
        return {
            'scan_date': datetime.utcnow().strftime('%Y-%m-%d'),
            'spokes_scanned': len(set(b['spoke'] for b in bubbles)),
            'items': bubbles[:10]  # Top 10 items
        }

    def _update_scanstate(self, spoke_id: str, last_session_time: Optional[str], bubble_count: int):
        """Update ScanState.json with new last_scan_at."""
        if spoke_id not in self.scanstate['spokes']:
            self.scanstate['spokes'][spoke_id] = {
                'spoke_id': spoke_id,
                'last_scan_at': None,
                'archaeology_complete': False,
                'sessions_scanned_count': 0,
                'last_bubble_count': 0
            }

        spoke_state = self.scanstate['spokes'][spoke_id]
        if last_session_time:
            spoke_state['last_scan_at'] = last_session_time
        spoke_state['last_bubble_count'] = bubble_count
        spoke_state['sessions_scanned_count'] += 1

    def run(self):
        """Execute the full nightly scan."""
        log.info('Starting nightly scan...')

        spokes = self._get_spokes()
        all_bubbles = []

        for spoke_info in spokes:
            spoke_id = spoke_info['spoke_id']
            spoke_path = spoke_info['path']

            log.info(f'Processing spoke: {spoke_id}')

            # Check archaeology gate
            if not self._check_archaeology_gate(spoke_path):
                self._update_scanstate(spoke_id, None, 0)
                continue

            # Get last scan time
            spoke_state = self.scanstate['spokes'].get(spoke_id, {})
            last_scan_at = spoke_state.get('last_scan_at')

            # Find new sessions
            new_sessions = self._find_new_sessions(spoke_path, last_scan_at)
            log.info(f'  Found {len(new_sessions)} new sessions')

            if not new_sessions:
                continue

            # Extract aspirations and append
            all_aspirations = []
            last_session_time = None

            for session_info in new_sessions:
                aspirations = self._extract_aspirations(session_info['path'])
                all_aspirations.extend(aspirations)
                last_session_time = session_info['timestamp']

            if all_aspirations:
                self._append_to_pathgraph(spoke_path, all_aspirations)

            # Identify bubbles
            bubbles = self._identify_bubbles(spoke_path, spoke_id)
            all_bubbles.extend(bubbles)

            # Update state
            self._update_scanstate(spoke_id, last_session_time, len(bubbles))

        # Update global last_full_run_at
        self.scanstate['last_full_run_at'] = datetime.utcnow().isoformat() + 'Z'

        # Score and produce bubble report
        all_bubbles = self._score_bubbles(all_bubbles)
        report = self._produce_bubble_report(all_bubbles)

        # Save updated ScanState
        try:
            with open(self.scanstate_path, 'w') as f:
                json.dump(self.scanstate, f, indent=2)
            log.info(f'Updated ScanState.json')
        except IOError as e:
            log.error(f'Failed to save ScanState.json: {e}')

        # Save bubble report
        report_path = self.wilbur_root / 'reports' / f'bubble-report-{datetime.utcnow().strftime("%Y%m%d")}.json'
        report_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2)
            log.info(f'Saved bubble report to {report_path}')
        except IOError as e:
            log.error(f'Failed to save bubble report: {e}')

        # Print report for notification escalation
        print(json.dumps(report))

        log.info('Nightly scan complete')


def main():
    framework_root = Path(__file__).parent.parent.parent
    scanner = NightlyScan(str(framework_root))
    scanner.run()


if __name__ == '__main__':
    main()
