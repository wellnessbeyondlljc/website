#!/usr/bin/env python3
"""Tests for goal_planner — the P1 replan ladder. Each rung + loop-safety + recording."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import capgraph_blocks as cb  # noqa: E402
import goal_planner as gp  # noqa: E402


@pytest.fixture
def root(tmp_path):
    (tmp_path / "WAI-Harness" / "spoke" / "local" / "capabilitygraph").mkdir(parents=True)
    return str(tmp_path)


def test_rung1_synthesize_allowlist(root):  # AC1
    lug = {"id": "l1", "type": "impl"}
    out = gp.replan_on_block(lug, "precondition_unmet", "file_exists: foo.py missing",
                             ctx=gp.new_ctx(), spoke_local=root)
    assert out["action"] == "requeue_setup" and out["rung"] == 1
    # a synthesized lug never re-synthesizes -> falls through to escalate
    out2 = gp.replan_on_block({"id": "l1b", "_synthesized": True}, "precondition_unmet",
                              "file_exists: x", ctx=gp.new_ctx(), spoke_local=root)
    assert out2["action"] == "escalate"
    # non-allowlisted precondition -> escalate
    out3 = gp.replan_on_block({"id": "l1c"}, "precondition_unmet", "needs_approval",
                              ctx=gp.new_ctx(), spoke_local=root)
    assert out3["action"] == "escalate"


def test_rung2_substitute_sibling(root):  # AC2
    lug = {"id": "l2", "goal_id": "goal-x"}
    out = gp.replan_on_block(lug, "stall", ctx=gp.new_ctx(), spoke_local=root,
                             sibling_lookup=lambda l: "sibling-lug-7")
    assert out["action"] == "substitute" and out["detail"].endswith("sibling-lug-7")


def test_rung3_demote_only_with_other_work(root):  # AC3
    lug = {"id": "l3", "initiative": "init-a"}
    out_yes = gp.replan_on_block(lug, "stall", ctx=gp.new_ctx(other_ready=True), spoke_local=root)
    assert out_yes["action"] == "demote" and out_yes["rung"] == 3
    out_no = gp.replan_on_block({"id": "l3b", "initiative": "init-a"}, "stall",
                                ctx=gp.new_ctx(other_ready=False), spoke_local=root)
    assert out_no["action"] == "escalate"


def test_rung4_escalate_default(root):  # AC4
    out = gp.replan_on_block({"id": "l4"}, "stall", ctx=gp.new_ctx(), spoke_local=root)
    assert out["action"] == "escalate" and out["rung"] == 4


def test_loop_safe_one_pass_per_run(root):  # AC4/loop-safety
    ctx = gp.new_ctx()
    lug = {"id": "l5", "goal_id": "g", "initiative": "i"}
    first = gp.replan_on_block(lug, "stall", ctx=ctx, spoke_local=root,
                               sibling_lookup=lambda l: "sib")
    assert first["action"] == "substitute"
    second = gp.replan_on_block(lug, "stall", ctx=ctx, spoke_local=root,
                                sibling_lookup=lambda l: "sib")
    assert second["action"] == "escalate"  # same key, same run -> no re-ladder


def test_records_block_and_stamps_resolution(root):  # records + resolution
    lug = {"id": "l6", "type": "impl"}
    out = gp.replan_on_block(lug, "stall", ctx=gp.new_ctx(), spoke_local=root)
    assert out["sig"] is not None
    hits = cb.consult(lug, spoke_local=root)
    assert hits and hits[0]["resolution"] == "escalated"


def test_never_raises_on_bad_lookup(root):
    out = gp.replan_on_block({"id": "l7", "goal_id": "g"}, "stall", ctx=gp.new_ctx(),
                             spoke_local=root,
                             sibling_lookup=lambda l: (_ for _ in ()).throw(RuntimeError("boom")))
    assert out["action"] == "escalate"  # exception -> safe escalate
