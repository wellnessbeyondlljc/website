"""Unit tests for the work_category heuristic classifier."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'WAI-Spoke'))

from db.work_category import categorize_session


def test_vibe_fix_with_bug():
    result = categorize_session('fix', ['bug'])
    assert result == ['bug_fix'], f"Expected ['bug_fix'], got {result}"


def test_vibe_build_with_feature():
    result = categorize_session('build', ['feature'])
    assert result == ['feature_dev'], f"Expected ['feature_dev'], got {result}"


def test_vibe_think_no_lugs():
    result = categorize_session('think', [])
    assert 'research' in result, f"Expected 'research' in {result}"
    assert 'planning' in result, f"Expected 'planning' in {result}"


def test_vibe_grind():
    result = categorize_session('grind', ['task'])
    assert result == ['maintenance'], f"Expected ['maintenance'], got {result}"


def test_vibe_ship():
    result = categorize_session('ship', [])
    assert result == ['ship'], f"Expected ['ship'], got {result}"


def test_unknown_vibe_falls_back_to_general():
    result = categorize_session('unknown_vibe', [])
    assert result == ['general'], f"Expected ['general'], got {result}"


def test_empty_vibe_falls_back_to_general():
    result = categorize_session('', [])
    assert result == ['general'], f"Expected ['general'], got {result}"


def test_returns_list_not_string():
    result = categorize_session('build', [])
    assert isinstance(result, list), f"Expected list, got {type(result)}"


if __name__ == '__main__':
    # Run all test_ functions manually
    import inspect
    module = sys.modules[__name__]
    tests = [name for name, obj in inspect.getmembers(module)
             if name.startswith('test_') and callable(obj)]
    passed = failed = 0
    for test_name in tests:
        try:
            getattr(module, test_name)()
            print(f'  PASS {test_name}')
            passed += 1
        except AssertionError as e:
            print(f'  FAIL {test_name}: {e}')
            failed += 1
    print(f'\n{passed} passed, {failed} failed')
