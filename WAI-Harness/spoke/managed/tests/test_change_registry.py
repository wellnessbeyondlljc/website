#!/usr/bin/env python3
"""Verification test for impl-change-registry-core-v1 (test-at-birth).

Covers verify[]: register (valid appends with defaults / missing key rejected),
silent-mutation guard (uncovered remote write flagged for revert), native
incorporation (target advances status, originator cannot), optimistic concurrency
(stale rev rejected), master/Trainer distribution gate, new-spoke entry.
"""
import importlib.util
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "tools", f"{mod}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


CR = _load("change_registry")


def _entry(**over):
    e = {"change_id": "chg-1", "origin": {"spoke": "website", "session": "s1", "actor_kind": "agent"},
         "target": "basher", "scope": "spoke-file", "what_changed": "hook tweak",
         "why": "fix", "files": [".claude/hooks/x.sh"]}
    e.update(over)
    return e


def test_register_sets_defaults_and_rejects_incomplete():
    with tempfile.TemporaryDirectory() as d:
        reg = os.path.join(d, "change-registry.jsonl")
        e = CR.register_change(_entry(), reg, now_iso="2026-06-09T00:00:00Z")
        assert e["incorporation_status"] == "registered"
        assert e["maintenance_owner"] == "basher", "maintenance is always the target"
        assert e["registered_at"]
        assert sum(1 for _ in open(reg)) == 1
        # missing required key -> rejected
        try:
            CR.register_change({"change_id": "x"}, reg)
            assert False, "incomplete entry must be rejected"
        except CR.RegistryError:
            pass
        # bad scope -> rejected
        try:
            CR.register_change(_entry(scope="whatever"), reg)
            assert False
        except CR.RegistryError:
            pass


def test_silent_mutation_guard_flags_uncovered_write():
    registry = [{"target": "basher", "files": [".claude/hooks/x.sh"]}]
    # a covered write -> not flagged
    g1 = CR.silent_mutation_guard([{"target": "basher", "files": [".claude/hooks/x.sh"]}], registry)
    assert g1["ok"] and not g1["flagged"]
    # an uncovered remote write -> flagged for revert (silent mutation)
    g2 = CR.silent_mutation_guard([{"target": "basher", "files": ["secret.py"]}], registry)
    assert not g2["ok"] and g2["action"] == "revert" and g2["flagged"]


def test_native_agent_advances_status_originator_cannot():
    with tempfile.TemporaryDirectory() as d:
        reg = os.path.join(d, "r.jsonl")
        CR.register_change(_entry(), reg, now_iso="2026-06-09T00:00:00Z")
        # originator (website) cannot self-mark accepted
        try:
            CR.advance_status("chg-1", "accepted", by_spoke="website", registry_path=reg)
            assert False, "originator must not advance native-only status"
        except CR.RegistryError:
            pass
        # the target (basher, native agent) can
        m = CR.advance_status("chg-1", "accepted", by_spoke="basher", registry_path=reg)
        assert m["incorporation_status"] == "accepted" and m["incorporated_by"] == "basher"
        assert m["maintenance_owner"] == "basher"


def test_optimistic_concurrency_rejects_stale_rev():
    assert CR.check_rev(5, 5)["ok"] is True
    stale = CR.check_rev(5, 3)
    assert stale["ok"] is False and stale.get("stale") and "reconcile" in stale["reason"]
    # missing rev -> cannot apply (last-write-wins banned)
    assert CR.check_rev(5, None)["ok"] is False


def test_master_change_gated_until_trainer_canonicalizes():
    with tempfile.TemporaryDirectory() as d:
        reg = os.path.join(d, "r.jsonl")
        e = CR.register_change(_entry(change_id="m1", target="MyWheel", scope="harness-managed"),
                               reg, now_iso="2026-06-09T00:00:00Z")
        assert CR.requires_trainer_canonicalization(e) is True
        assert CR.is_distributable(e) is False, "MyWheel change not distributable until canonicalized"
        e["canonicalized_by_trainer"] = "trainer-session-1"
        assert CR.is_distributable(e) is True
        # a normal spoke-file change is distributable once registered
        assert CR.is_distributable(_entry()) is True


def test_new_spoke_entry_and_registration():
    res = CR.new_spoke_entry(origin={"spoke": "website"}, new_wheel_id="newspoke",
                             blueprint_version="4.0.0-pre", path="/home/x/newspoke",
                             now_iso="2026-06-09T00:00:00Z")
    assert res["registry_entry"]["scope"] == "new-spoke"
    assert res["registry_entry"]["target"] == "newspoke"
    reg = res["hub_registration"]
    assert reg["wheel_id"] == "newspoke" and reg["certification_score"] is None
    assert reg["status"] == "registered-degraded", "not live until certified, but registered"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("ALL PASS")
