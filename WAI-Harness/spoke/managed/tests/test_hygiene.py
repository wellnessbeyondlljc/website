"""Acceptance proof: hygiene.py — stale-path self-heal (AC22) + Hygiene act-arm (AC34)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import hygiene as h  # noqa: E402


# --- AC22 self-healing stale-path redirect ---

def test_deprecated_v3_path_is_redirected_to_v4_home():
    healed, redirected = h.redirect_path("WAI-Spoke/lugs/incoming/x.json")
    assert redirected is True
    assert healed == "WAI-Harness/spoke/local/lugs/incoming/x.json"


def test_v3_state_file_redirect():
    healed, redirected = h.redirect_path("WAI-Spoke/WAI-State.json")
    assert redirected is True and healed == "WAI-Harness/spoke/local/WAI-State.json"


def test_advisors_redirect_to_spoke_advisors():
    healed, _ = h.redirect_path("WAI-Spoke/advisors/ozi/state.json")
    assert healed == "WAI-Harness/spoke/advisors/ozi/state.json"


def test_unmapped_v3_category_not_redirected_no_orphan():
    # a v3 category with no home-map entry stays in v3 (never silently dropped)
    healed, redirected = h.redirect_path("WAI-Spoke/some-legacy-thing/file.txt")
    assert redirected is False and healed == "WAI-Spoke/some-legacy-thing/file.txt"


def test_already_v4_path_unchanged():
    healed, redirected = h.redirect_path("WAI-Harness/spoke/local/lugs/x.json")
    assert redirected is False and healed == "WAI-Harness/spoke/local/lugs/x.json"


# --- AC34 detect + act-plan ---

def test_detect_misplaced():
    homes = {"lugs": "WAI-Harness/spoke/local/lugs", "tools": "tools"}
    disk = ["WAI-Harness/spoke/local/lugs/ok.json",   # in home -> fine
            "lugs/stray.json",                          # lugs cat but wrong home -> misplaced
            "tools/fine.py"]                            # in home -> fine
    mis = h.detect_misplaced(disk, homes)
    assert len(mis) == 1 and mis[0]["path"] == "lugs/stray.json"
    assert mis[0]["expected_home"] == "WAI-Harness/spoke/local/lugs"


def test_plan_relocates_misplaced_and_trashes_cruft_never_rm():
    mis = [{"path": "lugs/stray.json", "category": "lugs",
            "expected_home": "WAI-Harness/spoke/local/lugs"}]
    plan = h.plan_remediation(mis, cruft=["/home/mario/projects/wheelwright/framework/junk.tmp"])
    assert plan["relocate"][0]["to"] == "WAI-Harness/spoke/local/lugs/stray.json"
    # cruft goes to trash_bin preserving relative path — never rm
    t = plan["trash"][0]
    assert t["to"].startswith("/home/mario/projects/trash_bin/")
    assert "wheelwright/framework/junk.tmp" in t["to"]
    assert plan["human_gate"] is True   # Drop/trash requires sign-off
