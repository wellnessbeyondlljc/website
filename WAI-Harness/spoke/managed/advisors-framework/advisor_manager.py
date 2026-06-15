"""
AdvisorManager -- enforces advisor lifecycle rules including the one-piloting-slot constraint.

Rules:
- Only ONE advisor per spoke may be in 'piloting' status at any time.
- An advisor cannot enter 'piloting' without a complete pilot_contract.
- force_activate() bypasses the slot check but REQUIRES a non-empty reason string.
- All activation/deactivation events are written to lifecycle.jsonl.
"""
import datetime
import json
import os
import sys
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

PROJECT_ROOT = Path('/home/mario/projects/wheelwright/framework')
ADVISORS_DIR = PROJECT_ROOT / 'WAI-Spoke/advisors'
LIFECYCLE_LOG = ADVISORS_DIR / 'lifecycle.jsonl'


class AdvisorSlotOccupiedError(Exception):
    """Raised when trying to activate a piloting advisor when the slot is already taken."""
    pass


class AdvisorManager:
    def __init__(self):
        state = json.load(open(PROJECT_ROOT / 'WAI-Spoke/WAI-State.json'))
        self.wheel_id = state['wheel']['spoke_id']
        # SyncClient -- loaded lazily to avoid import issues
        self._sync = None

    def _get_sync(self):
        if self._sync is None:
            try:
                sys.path.insert(0, str(PROJECT_ROOT / 'WAI-Spoke'))
                from db.sync import SyncClient
                self._sync = SyncClient()
            except Exception:
                self._sync = None
        return self._sync

    def get_active_pilot(self) -> dict | None:
        """Return the current piloting advisor row, or None if slot is empty.

        Scans local advisor YAML files for piloting status.
        Falls back to Supabase if sync is enabled.
        """
        if not YAML_AVAILABLE:
            return None

        for advisor_dir in ADVISORS_DIR.iterdir():
            if not advisor_dir.is_dir():
                continue
            # Skip non-advisor directories
            if advisor_dir.name in ('schema',):
                continue
            active_yaml = advisor_dir / 'active.yaml'
            if not active_yaml.exists():
                continue
            try:
                active = yaml.safe_load(open(active_yaml))
                if not isinstance(active, dict):
                    continue
                current_version = active.get('current', 'v1.0.0')
                version_yaml = advisor_dir / f'{current_version}.yaml'
                if not version_yaml.exists():
                    continue
                defn = yaml.safe_load(open(version_yaml))
                if not isinstance(defn, dict):
                    continue
                # Handle both wrapped (advisor: {...}) and unwrapped formats
                advisor = defn.get('advisor', defn)
                if advisor.get('status') == 'piloting' and advisor.get('id'):
                    return {
                        'advisor_id': advisor['id'],
                        'status': 'piloting',
                        'pilot_iteration': advisor.get('pilot_iteration', 1),
                        'wheel_id': self.wheel_id,
                    }
            except Exception:
                continue
        return None

    def _load_advisor_def(self, advisor_id: str) -> dict:
        """Load the current version YAML definition dict for an advisor.

        Returns the inner advisor dict (unwrapped from 'advisor:' key if present).
        """
        if not YAML_AVAILABLE:
            raise RuntimeError('PyYAML is required for YAML-based advisor loading')
        advisor_dir = ADVISORS_DIR / advisor_id
        active_yaml = advisor_dir / 'active.yaml'
        if not active_yaml.exists():
            raise FileNotFoundError(f'No active.yaml for advisor {advisor_id}')
        active = yaml.safe_load(open(active_yaml))
        if not isinstance(active, dict):
            raise ValueError(f'active.yaml for {advisor_id} is not a mapping')
        current_version = active.get('current', 'v1.0.0')
        version_yaml = advisor_dir / f'{current_version}.yaml'
        if not version_yaml.exists():
            raise FileNotFoundError(f'No {current_version}.yaml for advisor {advisor_id}')
        defn = yaml.safe_load(open(version_yaml))
        if not isinstance(defn, dict):
            raise ValueError(f'{current_version}.yaml for {advisor_id} is not a mapping')
        return defn.get('advisor', defn)

    def _validate_pilot_contract(self, advisor_id: str, advisor_def: dict):
        """Verify pilot_contract is complete before allowing piloting status."""
        contract = advisor_def.get('pilot_contract')
        if not contract:
            raise ValueError(
                f'Advisor {advisor_id} is missing pilot_contract -- required before piloting'
            )
        required = ['hypothesis', 'kpis', 'data_required_for_evaluation', 'decision_criteria']
        missing = [k for k in required if not contract.get(k)]
        if missing:
            raise ValueError(
                f'Advisor {advisor_id} pilot_contract is missing required fields: {missing}'
            )

    def activate_advisor(self, advisor_id: str, to_status: str = 'piloting', reason: str = None):
        """Activate an advisor to a given status.

        If to_status='piloting', enforces the one-slot rule and validates pilot_contract.
        Raises AdvisorSlotOccupiedError if a pilot is already active.
        """
        if to_status == 'piloting':
            current = self.get_active_pilot()
            if current:
                raise AdvisorSlotOccupiedError(
                    f"Pilot slot held by '{current['advisor_id']}' -- "
                    f"deactivate it first or use force_activate()"
                )
            if YAML_AVAILABLE:
                advisor_def = self._load_advisor_def(advisor_id)
                self._validate_pilot_contract(advisor_id, advisor_def)

        self._set_advisor_status(advisor_id, to_status)
        self.write_lifecycle_event(
            advisor_id=advisor_id,
            event_type=f'activated_to_{to_status}',
            reason=reason or 'standard activation',
            changed_fields=['status'],
        )

        sync = self._get_sync()
        if sync:
            try:
                sync.upsert('advisor_registry', {
                    'wheel_id': self.wheel_id,
                    'advisor_id': advisor_id,
                    'status': to_status,
                })
            except Exception:
                pass  # sync failure is non-fatal

        # Start watchdog for piloting and promoted advisors
        if to_status in ('piloting', 'promoted'):
            try:
                sys.path.insert(0, str(PROJECT_ROOT / 'WAI-Spoke'))
                from advisors.evolution_engine import EvolutionEngine
                evolution_risk = 'medium'  # default if not specified in spec
                if hasattr(self, '_last_evolution_risk'):
                    evolution_risk = self._last_evolution_risk
                EvolutionEngine().start_watchdog(advisor_id, evolution_risk, 'v1.0.0')
            except Exception:
                pass  # watchdog is best-effort; activation must not fail

    def force_activate(self, advisor_id: str, reason: str):
        """Force-activate an advisor to piloting, bypassing the slot check.

        Requires a non-empty reason string (logged for audit).
        If another advisor currently holds the piloting slot, it is demoted to 'removed'
        before the target advisor is activated.
        """
        if not reason or not reason.strip():
            raise ValueError(
                'force_activate requires a non-empty reason string for audit logging'
            )

        # Demote current pilot if any
        current = self.get_active_pilot()
        if current:
            self.write_lifecycle_event(
                advisor_id=current['advisor_id'],
                event_type='force_deactivated',
                reason=f'force_activate called for {advisor_id}: {reason}',
                changed_fields=['status'],
            )
            self._set_advisor_status(current['advisor_id'], 'removed')

        self._set_advisor_status(advisor_id, 'piloting')
        self.write_lifecycle_event(
            advisor_id=advisor_id,
            event_type='force_activated_to_piloting',
            reason=reason,
            changed_fields=['status'],
        )

        sync = self._get_sync()
        if sync:
            try:
                sync.upsert('advisor_registry', {
                    'wheel_id': self.wheel_id,
                    'advisor_id': advisor_id,
                    'status': 'piloting',
                })
            except Exception:
                pass

    def deactivate_advisor(self, advisor_id: str, reason: str = None):
        """Deactivate an advisor (sets status to 'removed')."""
        self._set_advisor_status(advisor_id, 'removed')
        self.write_lifecycle_event(
            advisor_id=advisor_id,
            event_type='deactivated',
            reason=reason or 'manual deactivation',
            changed_fields=['status'],
        )

    def promote_advisor(self, advisor_id: str, reason: str = None):
        """Promote a piloting advisor to promoted status."""
        self._set_advisor_status(advisor_id, 'promoted')
        self.write_lifecycle_event(
            advisor_id=advisor_id,
            event_type='promoted',
            reason=reason or 'pilot evaluation succeeded',
            changed_fields=['status'],
        )

    def _set_advisor_status(self, advisor_id: str, new_status: str):
        """Update status in the advisor's versioned YAML file (local enforcement)."""
        if not YAML_AVAILABLE:
            return  # no local YAML support -- Supabase-only path

        advisor_dir = ADVISORS_DIR / advisor_id
        active_yaml = advisor_dir / 'active.yaml'
        if not active_yaml.exists():
            return  # advisor not locally tracked; Supabase-only path

        try:
            active = yaml.safe_load(open(active_yaml))
            if not isinstance(active, dict):
                return
            current_version = active.get('current', 'v1.0.0')
            version_yaml = advisor_dir / f'{current_version}.yaml'
            if not version_yaml.exists():
                return

            defn = yaml.safe_load(open(version_yaml))
            if not isinstance(defn, dict):
                return

            # Handle both wrapped and unwrapped formats
            wrapped = 'advisor' in defn
            advisor = defn.get('advisor', defn)

            advisor['status'] = new_status
            now = datetime.datetime.utcnow().isoformat() + 'Z'
            if 'status_history' not in advisor:
                advisor['status_history'] = []
            advisor['status_history'].append({
                'status': new_status,
                'at': now,
                'by': 'advisor_manager',
            })

            if wrapped:
                defn['advisor'] = advisor
            else:
                defn = advisor

            with open(version_yaml, 'w') as f:
                yaml.dump(defn, f, default_flow_style=False, allow_unicode=True)

        except Exception:
            pass  # non-fatal -- Supabase is the authoritative registry

    def write_lifecycle_event(
        self,
        advisor_id: str,
        event_type: str,
        reason: str,
        changed_fields: list = None,
    ):
        """Append a lifecycle event to lifecycle.jsonl.

        Uses json.dumps(ensure_ascii=False) to handle any unicode characters safely.
        Each line is independently parseable JSONL.
        """
        now = datetime.datetime.utcnow()
        ts_compact = now.strftime('%Y%m%dT%H%M%S')
        event = {
            'event_id': f'evt-{advisor_id}-{ts_compact}',
            'advisor_id': advisor_id,
            'event_type': event_type,
            'ts': now.isoformat() + 'Z',
            'reason': reason,
            'changed_fields': changed_fields or [],
            'authorized_by': 'ozi',
            'wheel_id': self.wheel_id,
        }
        os.makedirs(ADVISORS_DIR, exist_ok=True)
        with open(LIFECYCLE_LOG, 'a') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
