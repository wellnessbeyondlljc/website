"""test_ap_intake_and_groom_reconcile_v1.py

Covers two s135 fixes that close the AP wobble->roll pipeline:

  #1 Phase 0a autonomous intake (ozi_autopilot.OziAutopilot._phase0a_intake):
     delivered lugs in lugs/incoming/ are drained into lugs/bytype/<type>/<status>/
     so the expediter/groom/dispatch can see them; dedicated-handler types and
     unknown types are LEFT in incoming (never lost); idempotent.

  #2 Expediter<->groom reconcile (spoke_expediter.groom_eligible / count_dispatchable):
     a lug with the right type+model but missing PEV no longer counts as
     'dispatchable' (it would be rejected by the groom score>=3 gate).
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import ozi_autopilot  # noqa: E402
import spoke_expediter  # noqa: E402


# ---------------------------------------------------------------------------
# #1 intake
# ---------------------------------------------------------------------------

def _intake_ns(spoke_wai, dry_run=False):
    """Minimal stand-in carrying only what _phase0a_intake touches."""
    ns = types.SimpleNamespace(spoke_wai=Path(spoke_wai), dry_run=dry_run)
    ns._INTAKE_SKIP_TYPES = ozi_autopilot.OziAutopilot._INTAKE_SKIP_TYPES
    ns._INTAKE_TYPE_FOLDER = ozi_autopilot.OziAutopilot._INTAKE_TYPE_FOLDER
    return ns


def _write_lug(d, lug_id, ltype, status="open", **extra):
    p = Path(d) / f"{lug_id}.json"
    obj = {"id": lug_id, "type": ltype, "status": status, "title": lug_id}
    obj.update(extra)
    p.write_text(json.dumps(obj))
    return p


def test_intake_moves_work_lug_to_bytype():
    with tempfile.TemporaryDirectory() as tmp:
        wai = Path(tmp) / "WAI-Harness" / "spoke" / "local"
        incoming = wai / "lugs" / "incoming"
        incoming.mkdir(parents=True)
        _write_lug(incoming, "impl-x-v1", "implementation")
        _write_lug(incoming, "feat-y-v1", "feature")
        _write_lug(incoming, "sig-z-v1", "signal", status="undelivered")

        summary = ozi_autopilot.OziAutopilot._phase0a_intake(_intake_ns(wai))

        assert summary["moved"] == 3, summary
        assert (wai / "lugs" / "bytype" / "implementation" / "open" / "impl-x-v1.json").exists()
        assert (wai / "lugs" / "bytype" / "feature" / "open" / "feat-y-v1.json").exists()
        assert (wai / "lugs" / "bytype" / "signal" / "undelivered" / "sig-z-v1.json").exists()
        # incoming drained
        assert not list(incoming.glob("*.json"))


def test_intake_leaves_dedicated_and_unknown_types():
    with tempfile.TemporaryDirectory() as tmp:
        wai = Path(tmp) / "WAI-Harness" / "spoke" / "local"
        incoming = wai / "lugs" / "incoming"
        incoming.mkdir(parents=True)
        _write_lug(incoming, "initiative-install-v9", "initiative_install")
        _write_lug(incoming, "weird-thing-v1", "totally_unknown_type")

        summary = ozi_autopilot.OziAutopilot._phase0a_intake(_intake_ns(wai))

        assert summary["moved"] == 0
        assert summary["skipped"] == 2
        # both remain in incoming (never lost)
        assert (incoming / "initiative-install-v9.json").exists()
        assert (incoming / "weird-thing-v1.json").exists()


def test_intake_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        wai = Path(tmp) / "WAI-Harness" / "spoke" / "local"
        incoming = wai / "lugs" / "incoming"
        incoming.mkdir(parents=True)
        _write_lug(incoming, "impl-x-v1", "implementation")
        ozi_autopilot.OziAutopilot._phase0a_intake(_intake_ns(wai))
        # re-deliver the same id; second pass must not double-place or crash
        _write_lug(incoming, "impl-x-v1", "implementation")
        summary = ozi_autopilot.OziAutopilot._phase0a_intake(_intake_ns(wai))
        assert summary["moved"] == 0 and summary["skipped"] == 1
        assert (wai / "lugs" / "bytype" / "implementation" / "open" / "impl-x-v1.json").exists()
        assert not list(incoming.glob("*.json"))


def test_intake_dry_run_moves_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        wai = Path(tmp) / "WAI-Harness" / "spoke" / "local"
        incoming = wai / "lugs" / "incoming"
        incoming.mkdir(parents=True)
        _write_lug(incoming, "impl-x-v1", "implementation")
        summary = ozi_autopilot.OziAutopilot._phase0a_intake(_intake_ns(wai, dry_run=True))
        assert summary["moved"] == 1
        assert (incoming / "impl-x-v1.json").exists()  # untouched on disk


# ---------------------------------------------------------------------------
# #2 groom reconcile
# ---------------------------------------------------------------------------

_FULL_PEV = dict(
    title="a real title over ten chars",
    perceive="there is a concrete problem here",
    execute=["step one is concrete", "step two is concrete"],
    verify="run the tests and confirm green",
    acceptance_criteria=["it works"],
    model_fit="sonnet",
    type="implementation",
    execution_mode="autonomous",
)


def test_groom_eligible_true_for_full_pev():
    assert spoke_expediter.groom_eligible(dict(_FULL_PEV)) is True


def test_groom_eligible_false_without_pev():
    thin = dict(_FULL_PEV)
    thin["perceive"] = ""
    assert spoke_expediter.groom_eligible(thin) is False
    thin2 = dict(_FULL_PEV)
    thin2["execute"] = []
    assert spoke_expediter.groom_eligible(thin2) is False
    thin3 = dict(_FULL_PEV)
    thin3["verify"] = ""
    thin3["acceptance_criteria"] = []
    assert spoke_expediter.groom_eligible(thin3) is False


def test_count_dispatchable_excludes_pev_incomplete():
    good = dict(_FULL_PEV, id="good-v1")
    # right type + model + autonomous, but NO perceive/verify/ac -> groom would reject
    bad = dict(title="thin lug here", type="implementation", model_fit="sonnet",
               execution_mode="autonomous", execute=["do a thing"], id="bad-v1")
    out = spoke_expediter.count_dispatchable([good, bad])
    ids = [s["id"] for s in out]
    assert "good-v1" in ids and "bad-v1" not in ids, ids


# ---------------------------------------------------------------------------
# tender lane retired — AP absorbs all executable work
# ---------------------------------------------------------------------------

def test_assign_execution_mode_never_returns_tender():
    base = dict(routed_to="LOCAL", blocked_by=[])
    # opus, low-quality, and sonnet all route to an executable lane, never tender
    for mf, q in [("OPUS", 9), ("SONNET", 8), ("HAIKU", 3), ("SONNET", 2)]:
        mode, _sub, _hint = spoke_expediter.assign_execution_mode(
            dict(base, model_fit=mf), q, [], "/tmp/x")
        assert mode in ("subagent", "gastown"), (mf, q, mode)
        assert mode != "tender"
    # haiku + high quality is still the cheap gastown lane
    mode, _sub, _hint = spoke_expediter.assign_execution_mode(
        dict(base, model_fit="HAIKU"), 8, [], "/tmp/x")
    assert mode == "gastown"


def test_column_for_work_autonomous_regardless_of_model_tier():
    # opus + full model + decent quality -> autonomous now (was needs-you/tender)
    s = dict(type="implementation", model_fit="opus", quality_score=4)
    assert spoke_expediter._column_for("work", s) == "autonomous"
    s2 = dict(type="implementation", model_fit="sonnet", quality_score=9)
    assert spoke_expediter._column_for("work", s2) == "autonomous"


def test_column_for_still_holds_manual_and_blocked():
    assert spoke_expediter._column_for("work", dict(type="implementation", model_fit="opus", execution_mode="manual")) == "needs-you"
    assert spoke_expediter._column_for("work", dict(type="implementation", model_fit="opus", blocked=True)) == "needs-you"
