#!/usr/bin/env python3
"""Verification test for impl-pattern-gate-subagent-v1 (test-at-birth).

The .claude/agents/pattern-gate.md file is Basher-owned; framework AUTHORS the
definition + protocol and delivers it. This test certifies the authored
definition satisfies the full contract (frontmatter, read-only tools, both gate
modes, disposition protocol + 2-cycle retry cap, escalation surfacing, mandatory
emission, the 5 gate points) and that the emission command it specifies actually
works against the event bus. Live subagent dry-runs are a Basher/runtime
integration check.
"""
import importlib.util
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
DEF = os.path.join(ROOT, "WAI-Spoke/lugs/outgoing/pattern-gate.md")


def _body():
    with open(DEF, encoding="utf-8") as f:
        return f.read()


def _frontmatter(text):
    assert text.startswith("---"), "must have YAML frontmatter"
    _, fm, _body = text.split("---", 2)
    return fm


def test_definition_exists_and_frontmatter_is_readonly_haiku():
    text = _body()
    fm = _frontmatter(text).lower()
    assert "model: haiku" in fm, "gate must be a Haiku (cheap narrow certifier)"
    assert "read" in fm and "bash" in fm, "tools must include Read, Bash"
    # read-only by construction: no Write/Edit/Agent in the granted tools line
    tools_line = [l for l in fm.splitlines() if l.strip().startswith("tools:")][0].lower()
    for forbidden in ("write", "edit", "agent"):
        assert forbidden not in tools_line, f"gate must NOT grant {forbidden} (hallucinated success impossible)"


def test_both_gate_modes_defined():
    text = _body().lower()
    assert "pre" in text and "post" in text
    assert "precondition" in text or "before the step" in text
    assert "postcondition" in text or "after the step" in text


def test_disposition_protocol_and_retry_cap():
    text = _body()
    for d in ("approved", "halted", "escalate"):
        assert d in text, f"disposition {d} must be defined"
    low = text.lower()
    # read-only gate emits halted; a distinct write-authorized actor does the retry
    assert "do not perform the retry" in low or "does not perform the retry" in low \
        or "you do not perform the retry" in low
    assert "dispatcher" in low or "scheduler" in low
    # 2-cycle retry cap -> third failure escalates
    assert "attempt == 3" in text or "attempt < 3" in text
    assert "retry cap" in low or "2-cycle" in low or "two-cycle" in low


def test_no_plan_mode_and_observable_only_instruction():
    low = _body().lower()
    assert "no plan mode" in low and "execute immediately" in low
    assert "never against what you assume" in low or "only against what you can read" in low


def test_escalation_surfaces_to_human_and_historian():
    low = _body().lower()
    assert "historian" in low and "human" in low, "escalation must create a Historian signal + surface to human"


def test_mandatory_emission_and_five_gate_points():
    text = _body(); low = text.lower()
    assert "gate-log.jsonl" in text, "every invocation must emit to gate-log.jsonl"
    assert "event_bus.py" in text, "must specify the typed emission command"
    assert "silent" in low and "banned" in low
    for point in ("pre-dispatch", "teaching-import", "closeout", "inbox-acceptance", "session-integrity"):
        assert point in low, f"the 5 priority gate points must list {point}"


def test_specified_emission_command_actually_works():
    """The gate body tells the subagent to emit via tools/event_bus.py — confirm
    that exact emission path produces a valid typed gate event."""
    eb = importlib.util.spec_from_file_location("event_bus", os.path.join(ROOT, "tools", "event_bus.py"))
    m = importlib.util.module_from_spec(eb); eb.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as d:
        jr = os.path.join(d, "j.jsonl")
        eid = m.emit({"type": "gate", "actor": "pattern-gate", "status": "approved",
                      "ts": "2026-06-09T00:00:00", "subject_ref": "closeout/commit"}, jr)
        assert eid
        assert m.advisor_emitted("pattern-gate", jr) is True


def test_delivered_to_basher():
    import json
    lug = os.path.join(ROOT, "WAI-Spoke/lugs/outgoing/impl-basher-v4-claude-touchpoints-v1.json")
    d = json.load(open(lug))
    assert d.get("routed_to") == "basher" and d.get("delivered_at")
    assert ".claude/agents/pattern-gate.md" in d.get("file_targets", [])
    assert d.get("pattern_gate_body_file") == "pattern-gate.md"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("ALL PASS")
