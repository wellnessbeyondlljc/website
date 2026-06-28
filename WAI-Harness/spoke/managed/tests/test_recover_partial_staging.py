import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))

import recover_partial_staging as rps  # noqa: E402


def _runtime(base):
    return os.path.join(base, 'runtime')


def test_recovers_partial_staging(tmp_path):
    base = str(tmp_path)
    os.makedirs(_runtime(base))
    staging_path = os.path.join(_runtime(base), 'closeout-staging.json')
    with open(staging_path, 'w') as f:
        json.dump(
            {'type': 'partial', 'version': '4.3.1', 'session_id': 's999'}, f
        )

    result = rps.recover_partial_staging(base)

    assert result['recovered'] is True
    assert any('harvesting draft state' in i for i in result['items'])
    assert any('version=4.3.1' in i and 'session=s999' in i for i in result['items'])

    # Staging buffer is (re)marked as a fresh 'partial' recovery point.
    new_state = json.load(open(staging_path))
    assert new_state['type'] == 'partial'
    assert 'started_at' in new_state


def test_clean_no_op_when_no_staging(tmp_path):
    base = str(tmp_path)
    # No runtime/ dir at all — nothing to recover.
    result = rps.recover_partial_staging(base)

    assert result['recovered'] is False
    assert result['items'] == []

    # A fresh partial staging buffer is created (recovery point), session unknown.
    staging_path = os.path.join(_runtime(base), 'closeout-staging.json')
    assert os.path.exists(staging_path)
    new_state = json.load(open(staging_path))
    assert new_state['type'] == 'partial'
    assert new_state['session_id'] == 'unknown'


def test_session_id_from_guard(tmp_path):
    base = str(tmp_path)
    os.makedirs(_runtime(base))
    with open(os.path.join(_runtime(base), 'session-guard.json'), 'w') as f:
        json.dump({'session_id': 's-guard-42'}, f)

    result = rps.recover_partial_staging(base)

    assert result['recovered'] is False
    staging_path = os.path.join(_runtime(base), 'closeout-staging.json')
    new_state = json.load(open(staging_path))
    assert new_state['session_id'] == 's-guard-42'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
