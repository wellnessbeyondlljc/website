"""
Behavioral tests for EvolutionEngine.

All file I/O is redirected to tmp_path via monkeypatching PROJECT_ROOT.
Supabase calls are no-ops (sync_enabled=False in test WAI-State.json).
"""

import json
import uuid
from pathlib import Path

import pytest
import sys

FRAMEWORK_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(FRAMEWORK_ROOT / 'WAI-Spoke'))

import advisors.evolution_engine as ee_mod
from advisors.evolution_engine import EvolutionEngine


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def engine(monkeypatch, tmp_path):
    """
    EvolutionEngine with all file I/O redirected to tmp_path.

    Creates the minimal WAI-Spoke directory structure needed.
    """
    # Minimal WAI-State.json so _get_wheel_id() works
    wai_dir = tmp_path / 'WAI-Spoke'
    wai_dir.mkdir()
    state = {
        'wheel': {'spoke_id': 'test-spoke'},
        '_index': {'sync_enabled': False},
    }
    (wai_dir / 'WAI-State.json').write_text(json.dumps(state))

    # Required lug directories
    for sub in ('hypothesis/open', 'hypothesis/testing', 'hypothesis/confirmed',
                'hypothesis/rejected', 'hypothesis/adopted', 'other/open'):
        (wai_dir / 'lugs' / 'bytype' / sub).mkdir(parents=True)

    monkeypatch.setattr(ee_mod, 'PROJECT_ROOT', tmp_path)
    return EvolutionEngine()


def _obs_path(tmp_path: Path, advisor_id: str) -> Path:
    return tmp_path / f'WAI-Spoke/advisors/{advisor_id}/observations_buffer.jsonl'


def _write_observations(tmp_path: Path, advisor_id: str, pattern_id: str,
                         fired_count: int, unfired_count: int = 0):
    """Write N fired + M unfired observations to the buffer."""
    buf = _obs_path(tmp_path, advisor_id)
    buf.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for _ in range(fired_count):
        rows.append({'id': str(uuid.uuid4()), 'advisor_id': advisor_id,
                     'pattern_id': pattern_id, 'fired': True,
                     'user_response': 'acted', 'observation_type': 'behavioral',
                     'observed_at': '2026-01-01T00:00:00Z', 'context': {}})
    for _ in range(unfired_count):
        rows.append({'id': str(uuid.uuid4()), 'advisor_id': advisor_id,
                     'pattern_id': pattern_id, 'fired': False,
                     'user_response': None, 'observation_type': 'behavioral',
                     'observed_at': '2026-01-01T00:00:00Z', 'context': {}})
    buf.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')


# ---------------------------------------------------------------------------
# record_observation
# ---------------------------------------------------------------------------

class TestRecordObservation:

    def test_creates_buffer_file(self, engine, tmp_path):
        engine.record_observation('test-advisor', 'pat1', fired=True)
        assert _obs_path(tmp_path, 'test-advisor').exists()

    def test_appends_valid_jsonl(self, engine, tmp_path):
        engine.record_observation('a1', 'p1', fired=True)
        engine.record_observation('a1', 'p1', fired=False)
        lines = [l for l in _obs_path(tmp_path, 'a1').read_text().splitlines() if l.strip()]
        assert len(lines) == 2
        for line in lines:
            obs = json.loads(line)
            assert 'id' in obs
            assert 'observation_type' in obs

    def test_required_fields_present(self, engine, tmp_path):
        engine.record_observation('adv', 'ptn', fired=True,
                                   user_response='acted', context={'k': 'v'})
        obs = json.loads(_obs_path(tmp_path, 'adv').read_text().strip())
        assert obs['advisor_id'] == 'adv'
        assert obs['pattern_id'] == 'ptn'
        assert obs['fired'] is True
        assert obs['user_response'] == 'acted'
        assert obs['observation_type'] == 'behavioral'
        assert obs['context'] == {'k': 'v'}
        assert obs['observed_at'].endswith('Z')
        uuid.UUID(obs['id'])  # raises if not valid UUID

    def test_default_observation_type(self, engine, tmp_path):
        engine.record_observation('adv', 'ptn', fired=False)
        obs = json.loads(_obs_path(tmp_path, 'adv').read_text().strip())
        assert obs['observation_type'] == 'behavioral'

    def test_multiple_advisors_get_separate_buffers(self, engine, tmp_path):
        engine.record_observation('advisor-a', 'p', fired=True)
        engine.record_observation('advisor-b', 'p', fired=True)
        assert _obs_path(tmp_path, 'advisor-a').exists()
        assert _obs_path(tmp_path, 'advisor-b').exists()


# ---------------------------------------------------------------------------
# record_corpus_test_observation
# ---------------------------------------------------------------------------

class TestCorpusTestObservation:

    def test_sets_corpus_test_observation_type(self, engine, tmp_path):
        engine.record_corpus_test_observation('my-test', 'pattern-x', fired=True)
        buf = _obs_path(tmp_path, 'corpus-test-my-test')
        obs = json.loads(buf.read_text().strip())
        assert obs['observation_type'] == 'corpus_test'
        assert obs['advisor_id'] == 'corpus-test-my-test'
        assert obs['pattern_id'] == 'pattern-x'
        assert obs['fired'] is True


# ---------------------------------------------------------------------------
# check_recurrence
# ---------------------------------------------------------------------------

class TestCheckRecurrence:

    def test_no_buffer_returns_false(self, engine, tmp_path):
        should_form, risk, count = engine.check_recurrence('new-adv', 'ptn')
        assert should_form is False
        assert risk == 'low'
        assert count == 0

    def test_below_low_threshold(self, engine, tmp_path):
        _write_observations(tmp_path, 'adv', 'ptn', fired_count=2)
        should_form, risk, count = engine.check_recurrence('adv', 'ptn')
        assert should_form is False
        assert count == 2

    def test_low_threshold_crossed(self, engine, tmp_path):
        _write_observations(tmp_path, 'adv', 'ptn', fired_count=3)
        should_form, risk, count = engine.check_recurrence('adv', 'ptn')
        assert should_form is True
        assert risk == 'low'
        assert count == 3

    def test_medium_threshold_crossed(self, engine, tmp_path):
        _write_observations(tmp_path, 'adv', 'ptn', fired_count=5)
        should_form, risk, count = engine.check_recurrence('adv', 'ptn')
        assert should_form is True
        assert risk == 'medium'
        assert count == 5

    def test_high_threshold_crossed(self, engine, tmp_path):
        _write_observations(tmp_path, 'adv', 'ptn', fired_count=10)
        should_form, risk, count = engine.check_recurrence('adv', 'ptn')
        assert should_form is True
        assert risk == 'high'
        assert count == 10

    def test_unfired_observations_excluded(self, engine, tmp_path):
        _write_observations(tmp_path, 'adv', 'ptn', fired_count=2, unfired_count=10)
        should_form, risk, count = engine.check_recurrence('adv', 'ptn')
        assert should_form is False
        assert count == 2

    def test_only_matching_pattern_counted(self, engine, tmp_path):
        _write_observations(tmp_path, 'adv', 'ptn-a', fired_count=5)
        _write_observations(tmp_path, 'adv', 'ptn-b', fired_count=1)
        # Append both to same buffer (engine writes per-advisor, not per-pattern)
        buf = _obs_path(tmp_path, 'adv')
        # Re-read to check only ptn-b
        should_form, _, count = engine.check_recurrence('adv', 'ptn-b')
        assert count == 1
        assert should_form is False


# ---------------------------------------------------------------------------
# check_and_form_if_ready
# ---------------------------------------------------------------------------

class TestCheckAndFormIfReady:

    def test_below_threshold_returns_none(self, engine, tmp_path):
        _write_observations(tmp_path, 'adv', 'ptn', fired_count=2)
        result = engine.check_and_form_if_ready('adv', 'ptn', 'proposed change')
        assert result is None

    def test_creates_hypothesis_when_threshold_crossed(self, engine, tmp_path):
        _write_observations(tmp_path, 'adv', 'ptn', fired_count=3)
        hyp_id = engine.check_and_form_if_ready('adv', 'ptn', 'proposed change')
        assert hyp_id is not None
        hyp_file = tmp_path / f'WAI-Spoke/lugs/bytype/hypothesis/open/{hyp_id}.json'
        assert hyp_file.exists()

    def test_deduplication_no_second_hypothesis(self, engine, tmp_path):
        _write_observations(tmp_path, 'adv', 'ptn', fired_count=5)
        first = engine.check_and_form_if_ready('adv', 'ptn', 'change v1')
        assert first is not None
        second = engine.check_and_form_if_ready('adv', 'ptn', 'change v2')
        assert second is None

    def test_different_advisors_get_separate_hypotheses(self, engine, tmp_path):
        _write_observations(tmp_path, 'adv-x', 'ptn', fired_count=3)
        _write_observations(tmp_path, 'adv-y', 'ptn', fired_count=3)
        id_x = engine.check_and_form_if_ready('adv-x', 'ptn', 'change x')
        id_y = engine.check_and_form_if_ready('adv-y', 'ptn', 'change y')
        assert id_x is not None
        assert id_y is not None
        assert id_x != id_y


# ---------------------------------------------------------------------------
# form_hypothesis
# ---------------------------------------------------------------------------

class TestFormHypothesis:

    def test_hypothesis_lug_type_is_hypothesis(self, engine, tmp_path):
        hyp_id = engine.form_hypothesis('adv', 'ptn', [], 'change', 'low')
        hyp_file = tmp_path / f'WAI-Spoke/lugs/bytype/hypothesis/open/{hyp_id}.json'
        lug = json.loads(hyp_file.read_text())
        assert lug['type'] == 'hypothesis'

    def test_hypothesis_lug_initial_status_open(self, engine, tmp_path):
        hyp_id = engine.form_hypothesis('adv', 'ptn', [], 'change', 'low')
        lug = json.loads((tmp_path / f'WAI-Spoke/lugs/bytype/hypothesis/open/{hyp_id}.json').read_text())
        assert lug['status'] == 'open'

    def test_hypothesis_lug_required_fields(self, engine, tmp_path):
        hyp_id = engine.form_hypothesis('my-adv', 'my-ptn', ['2026-01-01Z'], 'some change', 'medium')
        lug = json.loads((tmp_path / f'WAI-Spoke/lugs/bytype/hypothesis/open/{hyp_id}.json').read_text())
        assert lug['advisor_id'] == 'my-adv'
        assert lug['pattern_id'] == 'my-ptn'
        assert lug['evolution_risk'] == 'medium'
        assert lug['proposed_change'] == 'some change'
        assert lug['cohort_confirmation_count'] == 0
        assert lug['observation_basis'] == ['2026-01-01Z']


# ---------------------------------------------------------------------------
# promote_hypothesis
# ---------------------------------------------------------------------------

class TestPromoteHypothesis:

    def _create_hypothesis(self, engine, tmp_path, advisor_id='adv', pattern_id='ptn'):
        hyp_id = engine.form_hypothesis(advisor_id, pattern_id, [], 'change', 'low')
        return hyp_id

    def test_valid_status_transitions(self, engine, tmp_path):
        hyp_id = self._create_hypothesis(engine, tmp_path)
        for status in ('testing', 'confirmed', 'rejected'):
            assert engine.promote_hypothesis(hyp_id, status) is True
            lug_files = list((tmp_path / 'WAI-Spoke/lugs/bytype/hypothesis').rglob(f'{hyp_id}.json'))
            lug = json.loads(lug_files[0].read_text())
            assert lug['status'] == status

    def test_invalid_status_raises(self, engine, tmp_path):
        hyp_id = self._create_hypothesis(engine, tmp_path)
        with pytest.raises(ValueError):
            engine.promote_hypothesis(hyp_id, 'invalid-status')

    def test_not_found_returns_false(self, engine, tmp_path):
        result = engine.promote_hypothesis('hyp-nonexistent-00000000', 'testing')
        assert result is False

    def test_adopted_status_updates_file(self, engine, tmp_path):
        hyp_id = self._create_hypothesis(engine, tmp_path)
        result = engine.promote_hypothesis(hyp_id, 'adopted')
        assert result is True
        lug_files = list((tmp_path / 'WAI-Spoke/lugs/bytype/hypothesis').rglob(f'{hyp_id}.json'))
        lug = json.loads(lug_files[0].read_text())
        assert lug['status'] == 'adopted'


# ---------------------------------------------------------------------------
# check_watchdog_degradation
# ---------------------------------------------------------------------------

class TestCheckWatchdogDegradation:

    def test_no_buffer_returns_no_watchdog(self, engine, tmp_path):
        degraded, reason = engine.check_watchdog_degradation('adv')
        assert degraded is False
        assert reason == 'no_watchdog'

    def test_insufficient_data_midpoint_lt_5(self, engine, tmp_path):
        # 8 observations: midpoint=4, which is < 5
        _write_observations(tmp_path, 'adv', 'ptn', fired_count=8)
        degraded, reason = engine.check_watchdog_degradation('adv')
        assert degraded is False
        assert reason == 'insufficient_data'

    def test_no_degradation_stable_act_rate(self, engine, tmp_path):
        buf = _obs_path(tmp_path, 'adv')
        buf.parent.mkdir(parents=True, exist_ok=True)
        # 20 observations: 10 baseline (8 acted/10 fired), 10 recent (8 acted/10 fired) — no drop
        rows = []
        for i in range(10):
            rows.append({'id': str(uuid.uuid4()), 'advisor_id': 'adv',
                         'pattern_id': 'ptn', 'fired': True,
                         'user_response': 'acted' if i < 8 else 'dismissed',
                         'observation_type': 'behavioral',
                         'observed_at': '2026-01-01T00:00:00Z', 'context': {}})
        for i in range(10):
            rows.append({'id': str(uuid.uuid4()), 'advisor_id': 'adv',
                         'pattern_id': 'ptn', 'fired': True,
                         'user_response': 'acted' if i < 8 else 'dismissed',
                         'observation_type': 'behavioral',
                         'observed_at': '2026-01-02T00:00:00Z', 'context': {}})
        buf.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
        degraded, reason = engine.check_watchdog_degradation('adv')
        assert degraded is False
        assert reason == 'ok'

    def test_degradation_detected_on_30pct_drop(self, engine, tmp_path):
        buf = _obs_path(tmp_path, 'adv')
        buf.parent.mkdir(parents=True, exist_ok=True)
        # Baseline: 10 obs, all fired=True, all acted (100% act rate)
        # Recent: 10 obs, all fired=True, 0 acted (0% act rate) — clear 30%+ drop
        rows = []
        for _ in range(10):
            rows.append({'id': str(uuid.uuid4()), 'advisor_id': 'adv',
                         'pattern_id': 'p', 'fired': True, 'user_response': 'acted',
                         'observation_type': 'behavioral',
                         'observed_at': '2026-01-01T00:00:00Z', 'context': {}})
        for _ in range(10):
            rows.append({'id': str(uuid.uuid4()), 'advisor_id': 'adv',
                         'pattern_id': 'p', 'fired': True, 'user_response': 'dismissed',
                         'observation_type': 'behavioral',
                         'observed_at': '2026-01-02T00:00:00Z', 'context': {}})
        buf.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
        degraded, reason = engine.check_watchdog_degradation('adv')
        assert degraded is True
        assert 'Act rate dropped' in reason


# ---------------------------------------------------------------------------
# auto_rollback_if_degraded
# ---------------------------------------------------------------------------

class TestAutoRollback:

    def _build_degraded_buffer(self, tmp_path, advisor_id):
        """Write a buffer that will trigger watchdog degradation."""
        buf = _obs_path(tmp_path, advisor_id)
        buf.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for _ in range(10):
            rows.append({'id': str(uuid.uuid4()), 'advisor_id': advisor_id,
                         'pattern_id': 'p', 'fired': True, 'user_response': 'acted',
                         'observation_type': 'behavioral',
                         'observed_at': '2026-01-01T00:00:00Z', 'context': {}})
        for _ in range(10):
            rows.append({'id': str(uuid.uuid4()), 'advisor_id': advisor_id,
                         'pattern_id': 'p', 'fired': True, 'user_response': 'dismissed',
                         'observation_type': 'behavioral',
                         'observed_at': '2026-01-02T00:00:00Z', 'context': {}})
        buf.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')

    def test_returns_false_when_not_degraded(self, engine, tmp_path):
        result = engine.auto_rollback_if_degraded('clean-adv')
        assert result is False

    def test_returns_true_when_degraded(self, engine, tmp_path):
        self._build_degraded_buffer(tmp_path, 'deg-adv')
        result = engine.auto_rollback_if_degraded('deg-adv')
        assert result is True

    def test_creates_finding_lug(self, engine, tmp_path):
        self._build_degraded_buffer(tmp_path, 'deg-adv2')
        engine.auto_rollback_if_degraded('deg-adv2')
        finding_files = list((tmp_path / 'WAI-Spoke/lugs/bytype/other/open').glob('finding-watchdog-deg-adv2-*.json'))
        assert len(finding_files) == 1
        finding = json.loads(finding_files[0].read_text())
        assert finding['event_type'] == 'watchdog_rollback'
        assert finding['advisor_id'] == 'deg-adv2'

    def test_restores_backup_yaml_when_present(self, engine, tmp_path):
        advisor_id = 'backup-adv'
        self._build_degraded_buffer(tmp_path, advisor_id)
        advisor_dir = tmp_path / f'WAI-Spoke/advisors/{advisor_id}'
        advisor_dir.mkdir(parents=True, exist_ok=True)
        backup = advisor_dir / 'pre_adoption_backup.yaml'
        active = advisor_dir / 'active.yaml'
        backup.write_text('version: v0.9.0\nbehavior: old\n')
        active.write_text('version: v1.0.0\nbehavior: new\n')

        engine.auto_rollback_if_degraded(advisor_id)

        assert active.read_text() == 'version: v0.9.0\nbehavior: old\n'
