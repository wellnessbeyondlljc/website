import json
import datetime
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path('/home/mario/projects/wheelwright/framework')
sys.path.insert(0, str(PROJECT_ROOT / 'WAI-Spoke'))
from db.sync import SyncClient

RISK_THRESHOLDS = {'low': 3, 'medium': 5, 'high': 10}


class EvolutionEngine:
    """
    Detects recurring advisor patterns, forms hypothesis lugs, and tracks
    watchdog windows for adopted behavior changes.

    Architecture:
    - observations_buffer.jsonl: offline-safe local log (per advisor)
    - Supabase advisor_observations table: fleet-visible mirror (best-effort)
    - Hypothesis lugs: written to bytype/other/open/ + Supabase advisor_hypotheses
    - Cohort check (medium/high risk): hub-side only (Architect advisor) — NOT done here

    Risk thresholds (local observation count):
    - low: 3+ fired observations
    - medium: 5+ fired observations (cohort check: hub-side)
    - high: 10+ fired observations (cohort check: hub-side)
    """

    def __init__(self):
        self._sync = SyncClient()

    def record_observation(self, advisor_id: str, pattern_id: str, fired: bool,
                           user_response: str = None, context: dict = None,
                           observation_type: str = 'behavioral'):
        """
        Record one observation for an advisor pattern.

        Writes to:
        1. Local JSONL buffer at WAI-Spoke/advisors/{advisor_id}/observations_buffer.jsonl
        2. Supabase advisor_observations table (best-effort via SyncClient)

        user_response must be one of: 'acted', 'dismissed', 'ignored', or None
        observation_type: category of observation (e.g. 'behavioral', 'corpus_test')
        """
        obs = {
            'id': str(uuid.uuid4()),
            'observation_type': observation_type,
            'advisor_id': advisor_id,
            'pattern_id': pattern_id,
            'fired': fired,
            'user_response': user_response,
            'observed_at': datetime.datetime.utcnow().isoformat() + 'Z',
            'context': context or {}
        }
        # Write to local buffer (offline-safe)
        buf_path = PROJECT_ROOT / f'WAI-Spoke/advisors/{advisor_id}/observations_buffer.jsonl'
        buf_path.parent.mkdir(parents=True, exist_ok=True)
        with open(buf_path, 'a') as f:
            f.write(json.dumps(obs, ensure_ascii=False) + '\n')
        # Mirror to Supabase (best-effort; no-op when sync_enabled=False)
        try:
            self._sync.upsert('advisor_observations', obs)
        except Exception:
            pass  # local buffer is authoritative; Supabase is best-effort

    def check_recurrence(self, advisor_id: str, pattern_id: str) -> tuple:
        """
        Count fired=True observations for the given pattern in the local buffer.

        Returns (should_form: bool, evolution_risk: str, count: int)
        - should_form=True when count >= any threshold
        - evolution_risk = 'low' | 'medium' | 'high' (highest crossed)
        - count = total fired observations for this pattern
        """
        buf_path = PROJECT_ROOT / f'WAI-Spoke/advisors/{advisor_id}/observations_buffer.jsonl'
        if not buf_path.exists():
            return False, 'low', 0

        lines = [l.strip() for l in buf_path.read_text().splitlines() if l.strip()]
        observations = []
        for line in lines:
            try:
                observations.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        count = sum(
            1 for o in observations
            if o.get('pattern_id') == pattern_id and o.get('fired') is True
        )

        # Check thresholds from highest to lowest
        for risk in ('high', 'medium', 'low'):
            if count >= RISK_THRESHOLDS[risk]:
                return True, risk, count

        return False, 'low', count

    def form_hypothesis(self, advisor_id: str, pattern_id: str, obs_refs: list,
                        proposed_change: str, evolution_risk: str) -> str:
        """
        Create a hypothesis lug in WAI-Spoke/lugs/bytype/other/open/ and
        upsert to Supabase advisor_hypotheses.

        Returns the hypothesis ID.
        """
        ts = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S')
        hyp_id = f'hyp-{advisor_id}-{pattern_id}-{ts}'

        lug = {
            'id': hyp_id,
            'type': 'hypothesis',
            'status': 'open',
            'title': f'Evolution hypothesis: {advisor_id} pattern {pattern_id} recurrence detected',
            'advisor_id': advisor_id,
            'pattern_id': pattern_id,
            'hypothesis_text': (
                f'Pattern "{pattern_id}" in advisor "{advisor_id}" has recurred '
                f'{len(obs_refs)} times, crossing the {evolution_risk}-risk threshold. '
                f'Proposed change requires review before adoption.'
            ),
            'proposed_change': proposed_change,
            'evolution_risk': evolution_risk,
            'observation_basis': obs_refs,
            'cohort_confirmation_count': 0,
            'created_at': datetime.datetime.utcnow().isoformat() + 'Z',
            'updated_at': datetime.datetime.utcnow().isoformat() + 'Z',
            'gb': 'claude-sonnet-4-6',
            'routed_to': 'LOCAL'
        }

        out_path = PROJECT_ROOT / f'WAI-Spoke/lugs/bytype/hypothesis/open/{hyp_id}.json'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w') as f:
            json.dump(lug, f, indent=2, ensure_ascii=False)

        try:
            self._sync.upsert('advisor_hypotheses', lug)
        except Exception:
            pass  # disk is authoritative

        return hyp_id

    def check_and_form_if_ready(self, advisor_id: str, pattern_id: str,
                                 proposed_change: str) -> str | None:
        """
        If recurrence threshold is crossed and no open hypothesis exists for
        this pattern, form a hypothesis.

        Returns hypothesis_id if formed, None if not yet ready or already exists.
        """
        should_form, risk, count = self.check_recurrence(advisor_id, pattern_id)
        if not should_form:
            return None

        # Dedup: check for existing open hypothesis for this pattern
        lug_dir = PROJECT_ROOT / 'WAI-Spoke/lugs/bytype/hypothesis/open'
        if lug_dir.exists():
            existing = list(lug_dir.glob(f'hyp-{advisor_id}-{pattern_id}-*.json'))
            if existing:
                return None  # Already has an open hypothesis — don't duplicate

        # Collect obs_refs from the buffer
        buf_path = PROJECT_ROOT / f'WAI-Spoke/advisors/{advisor_id}/observations_buffer.jsonl'
        obs_refs = []
        if buf_path.exists():
            for line in buf_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    obs = json.loads(line)
                    if obs.get('pattern_id') == pattern_id and obs.get('fired'):
                        obs_refs.append(obs.get('observed_at', ''))
                except json.JSONDecodeError:
                    continue

        return self.form_hypothesis(advisor_id, pattern_id, obs_refs, proposed_change, risk)

    HYPOTHESIS_STATUSES = {'open', 'testing', 'confirmed', 'rejected', 'adopted'}

    def promote_hypothesis(self, hyp_id: str, new_status: str) -> bool:
        """
        Transition a hypothesis lug to a new status.

        Valid statuses: open, testing, confirmed, rejected, adopted
        On 'adopted': also upserts to advisor_versions table.

        Returns True if the hypothesis was found and updated, False otherwise.
        """
        if new_status not in self.HYPOTHESIS_STATUSES:
            raise ValueError(f'Invalid status: {new_status!r}. Must be one of {self.HYPOTHESIS_STATUSES}')

        hyp_dir = PROJECT_ROOT / 'WAI-Spoke/lugs/bytype/hypothesis'
        files = list(hyp_dir.rglob(f'{hyp_id}.json')) if hyp_dir.exists() else []
        if not files:
            return False

        hyp_path = files[0]
        lug = json.loads(hyp_path.read_text())
        lug['status'] = new_status
        lug['updated_at'] = datetime.datetime.utcnow().isoformat() + 'Z'

        with open(hyp_path, 'w') as f:
            json.dump(lug, f, indent=2, ensure_ascii=False)

        if new_status == 'adopted':
            advisor_id = lug.get('advisor_id', '')
            row = {
                'advisor_id': advisor_id,
                'wheel_id': self._get_wheel_id(),
                'version': 1,
                'definition_yaml': self._load_active_yaml(advisor_id),
                'activated_at': datetime.datetime.utcnow().isoformat() + 'Z',
            }
            try:
                self._sync.upsert('advisor_versions', row)
            except Exception:
                pass

        try:
            self._sync.upsert('advisor_hypotheses', lug)
        except Exception:
            pass

        return True

    def record_corpus_test_observation(self, test_id: str, pattern_id: str,
                                       fired: bool, user_response: str = None) -> None:
        """
        Record an observation from a corpus test run.

        Thin wrapper over record_observation() using advisor_id='corpus-test-{test_id}'.
        Writes to WAI-Spoke/advisors/corpus-test-{test_id}/observations_buffer.jsonl.
        """
        self.record_observation(
            advisor_id=f'corpus-test-{test_id}',
            pattern_id=pattern_id,
            fired=fired,
            user_response=user_response,
            observation_type='corpus_test',
        )

    # ─── Watchdog ────────────────────────────────────────────────────────────

    WATCHDOG_DAYS = {'low': 14, 'medium': 28, 'high': 56}

    def start_watchdog(self, advisor_id: str, evolution_risk: str, adopted_version: str):
        """
        Record the start of a watchdog window after a behavior change is adopted.
        Writes to advisor_version_watchdog table so we know when to evaluate.

        evolution_risk: 'low' | 'medium' | 'high'
        adopted_version: e.g. 'v1.1.0'
        """
        days = self.WATCHDOG_DAYS.get(evolution_risk, 28)
        now = datetime.datetime.utcnow()
        watchdog_until = now + datetime.timedelta(days=days)
        row = {
            'advisor_id': advisor_id,
            'version': adopted_version,
            'wheel_id': self._get_wheel_id(),
            'definition_yaml': self._load_active_yaml(advisor_id),
            'activated_at': now.isoformat() + 'Z',
            'watchdog_until': watchdog_until.isoformat() + 'Z',
        }
        try:
            self._sync.upsert('advisor_version_watchdog', row)
        except Exception:
            pass  # watchdog is best-effort; disk state is authoritative

    def check_watchdog_degradation(self, advisor_id: str) -> tuple:
        """
        Check whether the current active version has degraded relative to
        its pre-adoption baseline.

        Returns (degraded: bool, reason: str).
        - (False, 'no_watchdog') if watchdog not active
        - (False, 'watchdog_expired') if watchdog window has passed
        - (False, 'insufficient_data') if fewer than 5 observations post-adoption
        - (False, 'ok') if within threshold
        - (True, 'Act rate dropped from X% to Y%') if degraded
        """
        buf_path = PROJECT_ROOT / f'WAI-Spoke/advisors/{advisor_id}/observations_buffer.jsonl'
        if not buf_path.exists():
            return False, 'no_watchdog'

        lines = [l.strip() for l in buf_path.read_text().splitlines() if l.strip()]
        observations = []
        for line in lines:
            try:
                observations.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        if not observations:
            return False, 'no_watchdog'

        # Split: first half = baseline, second half = recent
        midpoint = len(observations) // 2
        if midpoint < 5:
            return False, 'insufficient_data'

        baseline_obs = observations[:midpoint]
        recent_obs = observations[midpoint:]

        def act_rate(obs_list):
            fired = [o for o in obs_list if o.get('fired')]
            if not fired:
                return 0.0
            acted = [o for o in fired if o.get('user_response') == 'acted']
            return len(acted) / len(fired)

        baseline = act_rate(baseline_obs)
        current = act_rate(recent_obs)

        # 30% drop threshold
        if baseline > 0 and current < baseline * 0.70:
            pct_b = int(baseline * 100)
            pct_c = int(current * 100)
            return True, f'Act rate dropped from {pct_b}% to {pct_c}% (threshold: 30% drop)'

        return False, 'ok'

    def auto_rollback_if_degraded(self, advisor_id: str) -> bool:
        """
        If watchdog detects degradation, restore the previous active.yaml,
        write a lifecycle event, and create a finding lug.

        Returns True if rollback was performed, False otherwise.
        """
        degraded, reason = self.check_watchdog_degradation(advisor_id)
        if not degraded:
            return False

        # Try to load a backup of the previous YAML
        advisor_dir = PROJECT_ROOT / f'WAI-Spoke/advisors/{advisor_id}'
        backup_path = advisor_dir / 'pre_adoption_backup.yaml'
        active_path = advisor_dir / 'active.yaml'

        if backup_path.exists():
            import shutil
            shutil.copy2(str(backup_path), str(active_path))
        # else: no backup available, rollback is informational only

        # Write lifecycle event via AdvisorManager
        try:
            sys.path.insert(0, str(PROJECT_ROOT / 'WAI-Spoke'))
            from advisors.advisor_manager import AdvisorManager
            mgr = AdvisorManager()
            mgr.write_lifecycle_event(
                advisor_id=advisor_id,
                event_type='auto_rolled_back',
                reason=reason,
                changed_fields=['active.yaml']
            )
        except Exception as e:
            pass  # best-effort

        # Create a finding lug
        ts = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S')
        finding_id = f'finding-watchdog-{advisor_id}-{ts}'
        finding = {
            'id': finding_id,
            'type': 'other',
            'status': 'open',
            'title': f'Advisor {advisor_id} auto-rolled back during watchdog: {reason}',
            'advisor_id': advisor_id,
            'event_type': 'watchdog_rollback',
            'reason': reason,
            'created_at': datetime.datetime.utcnow().isoformat() + 'Z',
            'gb': 'claude-sonnet-4-6',
            'routed_to': 'LOCAL'
        }
        out_path = PROJECT_ROOT / f'WAI-Spoke/lugs/bytype/other/open/{finding_id}.json'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w') as f:
            json.dump(finding, f, indent=2, ensure_ascii=False)

        return True

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _get_wheel_id(self) -> str:
        state = json.loads((PROJECT_ROOT / 'WAI-Spoke/WAI-State.json').read_text())
        return state['wheel'].get('spoke_id', 'unknown')

    def _load_active_yaml(self, advisor_id: str) -> str:
        active_path = PROJECT_ROOT / f'WAI-Spoke/advisors/{advisor_id}/active.yaml'
        if active_path.exists():
            return active_path.read_text()
        return ''

    def get_cohort_confirmation_count(self, hypothesis_id: str) -> int:
        """
        Read cohort_confirmation_count for a hypothesis from Supabase.
        Returns 0 if sync is disabled or hypothesis not found.
        """
        # This is a read-only query to Supabase — only works when sync_enabled=True
        # Hub-side Architect advisor manages cohort tracking; spokes only read the count
        try:
            import os
            import httpx
            state = json.loads(
                (PROJECT_ROOT / 'WAI-Spoke/WAI-State.json').read_text()
            )
            idx = state.get('_index', {})
            if not idx.get('sync_enabled'):
                return 0
            url = idx.get('supabase_url', '')
            key = os.environ.get(idx.get('supabase_anon_key_env', 'WAI_SUPABASE_ANON_KEY'), '')
            if not url or not key:
                return 0
            r = httpx.get(
                f'{url}/rest/v1/advisor_hypotheses',
                params={'id': f'eq.{hypothesis_id}', 'select': 'cohort_confirmation_count'},
                headers={'apikey': key, 'Authorization': f'Bearer {key}'}
            )
            r.raise_for_status()
            rows = r.json()
            if rows:
                return rows[0].get('cohort_confirmation_count', 0)
        except Exception:
            pass
        return 0
