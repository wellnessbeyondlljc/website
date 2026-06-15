#!/usr/bin/env python3
"""Acceptance proof for synthesize_turn.py ECC learning features.

Covers all acceptance criteria from impl-synthesize-turn-ecc-learning-v1
plus the adaptation that restored augment-buffer behavior in the
buffer_was_present=True path (commit 77abeaa2).
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

framework_root = Path(__file__).parent.parent
sys.path.insert(0, str(framework_root))
sys.path.insert(0, str(framework_root / ".claude" / "hooks"))

import synthesize_turn as st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_entry(uuid, session_id, text, ts="2026-06-06T00:00:01Z"):
    return {
        "type": "user",
        "promptSource": "typed",
        "uuid": uuid,
        "sessionId": session_id,
        "timestamp": ts,
        "gitBranch": "main",
        "message": {"content": text},
    }


def _assistant_entry(uuid, text, model="claude-sonnet-4-6",
                     in_tok=100, out_tok=50,
                     cache_read=10, cache_create=5,
                     ts="2026-06-06T00:00:02Z"):
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": ts,
        "message": {
            "model": model,
            "content": [{"type": "text", "text": text}],
            "usage": {
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_create,
            },
        },
    }


def _make_transcript(rows, tmp: Path) -> Path:
    p = tmp / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def _make_state(track_rel: str, tmp: Path) -> Path:
    p = tmp / "state.json"
    p.write_text(json.dumps({"_session_state": {"track_path": track_rel}}))
    return p


def _make_track(rows, track_path: Path):
    track_path.parent.mkdir(parents=True, exist_ok=True)
    track_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _read_track(track_path: Path):
    return [json.loads(l) for l in track_path.read_text().splitlines() if l.strip()]


def _read_usage(project_dir: Path):
    p = project_dir / "WAI-Spoke" / "runtime" / "provider_usage.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# AC1 + AC2: model and token fields on synthesized turns
# ---------------------------------------------------------------------------

class TestModelAndTokenFields:
    def test_single_assistant_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [
                _user_entry("u1", "sess1", "Do something"),
                _assistant_entry("a1", "Done.", model="claude-haiku-4-5-20251001",
                                 in_tok=200, out_tok=80, cache_read=20, cache_create=10),
            ]
            transcript = _make_transcript(rows, tmp)
            track_rel = "WAI-Spoke/sessions/s1/track.jsonl"
            track_path = tmp / track_rel
            track_path.parent.mkdir(parents=True, exist_ok=True)
            track_path.touch()
            state = _make_state(track_rel, tmp)

            st.live(str(state), str(transcript), str(tmp), buffer_was_present=False)

            entries = _read_track(track_path)
            turns = [e for e in entries if e.get("event") == "turn"]
            assert turns, "Expected a turn entry"
            t = turns[0]
            assert t["model"] == "claude-haiku-4-5-20251001"
            assert t["input_tokens"] == 200
            assert t["output_tokens"] == 80
            assert t["cache_read_tokens"] == 20
            assert t["cache_creation_tokens"] == 10

    def test_tokens_summed_across_multiple_assistant_entries(self):
        """Two assistant entries in one turn — tokens must be summed."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [
                _user_entry("u1", "sess1", "Multi-step task"),
                _assistant_entry("a1", "Step 1.", in_tok=100, out_tok=40, cache_read=5, cache_create=2),
                _assistant_entry("a2", "Step 2.", in_tok=150, out_tok=60, cache_read=8, cache_create=3),
            ]
            transcript = _make_transcript(rows, tmp)
            track_rel = "WAI-Spoke/sessions/s1/track.jsonl"
            track_path = tmp / track_rel
            track_path.parent.mkdir(parents=True, exist_ok=True)
            track_path.touch()
            state = _make_state(track_rel, tmp)

            st.live(str(state), str(transcript), str(tmp), buffer_was_present=False)

            t = [e for e in _read_track(track_path) if e.get("event") == "turn"][0]
            assert t["input_tokens"] == 250   # 100 + 150
            assert t["output_tokens"] == 100  # 40 + 60
            assert t["cache_read_tokens"] == 13
            assert t["cache_creation_tokens"] == 5

    def test_model_taken_from_first_assistant_entry(self):
        """model field uses the first assistant entry's model."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [
                _user_entry("u1", "sess1", "Task"),
                _assistant_entry("a1", "First.", model="claude-sonnet-4-6"),
                _assistant_entry("a2", "Second.", model="claude-haiku-4-5-20251001"),
            ]
            transcript = _make_transcript(rows, tmp)
            track_rel = "WAI-Spoke/sessions/s1/track.jsonl"
            track_path = tmp / track_rel
            track_path.parent.mkdir(parents=True, exist_ok=True)
            track_path.touch()
            state = _make_state(track_rel, tmp)

            st.live(str(state), str(transcript), str(tmp), buffer_was_present=False)

            t = [e for e in _read_track(track_path) if e.get("event") == "turn"][0]
            assert t["model"] == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# AC3 + AC4: correction detection
# ---------------------------------------------------------------------------

class TestCorrectionDetection:
    def test_fires_when_user_corrects_prior_assistant(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            prior_turn = {
                "event": "turn", "turn": 1, "session_id": "sess1",
                "user_intent": "Do something",
                "assistant_text": "I'll use approach A.",
                "tools_used": [], "files_touched": [],
            }
            rows = [
                _user_entry("u2", "sess1", "No, don't use approach A"),
                _assistant_entry("a2", "OK, switching."),
            ]
            transcript = _make_transcript(rows, tmp)
            track_rel = "WAI-Spoke/sessions/s1/track.jsonl"
            track_path = tmp / track_rel
            _make_track([prior_turn], track_path)
            state = _make_state(track_rel, tmp)

            st.live(str(state), str(transcript), str(tmp), buffer_was_present=False)

            entries = _read_track(track_path)
            corrections = [e for e in entries if e.get("event") == "correction"]
            assert corrections, "Expected a correction event"
            c = corrections[0]
            assert "don't" in c["keywords"]
            assert c["turn"] == 2
            assert c["session_id"] == "sess1"
            assert "ts" in c
            assert "trigger" in c
            assert "prior_action" in c
            assert "confidence" in c
            assert 0.0 < c["confidence"] <= 0.85

    def test_does_not_fire_without_prior_assistant_text(self):
        """AC3: correction detection must not fire when prior_assistant_text is empty."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [
                _user_entry("u1", "sess1", "No, don't do that"),
                _assistant_entry("a1", "OK."),
            ]
            transcript = _make_transcript(rows, tmp)
            track_rel = "WAI-Spoke/sessions/s1/track.jsonl"
            track_path = tmp / track_rel
            track_path.parent.mkdir(parents=True, exist_ok=True)
            track_path.touch()
            state = _make_state(track_rel, tmp)

            st.live(str(state), str(transcript), str(tmp), buffer_was_present=False)

            entries = _read_track(track_path)
            corrections = [e for e in entries if e.get("event") == "correction"]
            assert not corrections, "Should not fire when there is no prior assistant text"

    def test_does_not_fire_without_correction_keyword(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            prior_turn = {
                "event": "turn", "turn": 1, "session_id": "sess1",
                "assistant_text": "I did X.",
                "user_intent": "", "tools_used": [], "files_touched": [],
            }
            rows = [
                _user_entry("u2", "sess1", "Great, now do Y"),
                _assistant_entry("a2", "Done."),
            ]
            transcript = _make_transcript(rows, tmp)
            track_rel = "WAI-Spoke/sessions/s1/track.jsonl"
            track_path = tmp / track_rel
            _make_track([prior_turn], track_path)
            state = _make_state(track_rel, tmp)

            st.live(str(state), str(transcript), str(tmp), buffer_was_present=False)

            entries = _read_track(track_path)
            corrections = [e for e in entries if e.get("event") == "correction"]
            assert not corrections


# ---------------------------------------------------------------------------
# AC5: provider_usage.jsonl
# ---------------------------------------------------------------------------

class TestProviderUsageFeed:
    def test_row_written_on_synthesized_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [
                _user_entry("u1", "sess1", "Task", ts="2026-06-06T10:00:00Z"),
                _assistant_entry("a1", "Done.", model="claude-sonnet-4-6",
                                 in_tok=300, out_tok=100, cache_read=50, cache_create=25,
                                 ts="2026-06-06T10:00:05Z"),
            ]
            transcript = _make_transcript(rows, tmp)
            track_rel = "WAI-Spoke/sessions/s1/track.jsonl"
            track_path = tmp / track_rel
            track_path.parent.mkdir(parents=True, exist_ok=True)
            track_path.touch()
            state = _make_state(track_rel, tmp)

            st.live(str(state), str(transcript), str(tmp), buffer_was_present=False)

            rows_usage = _read_usage(tmp)
            assert rows_usage, "provider_usage.jsonl should have a row"
            row = rows_usage[0]
            assert row["session_id"] == "sess1"
            assert row["model"] == "claude-sonnet-4-6"
            assert row["input_tokens"] == 300
            assert row["output_tokens"] == 100
            assert row["cache_read_tokens"] == 50
            assert row["cache_creation_tokens"] == 25
            assert row["session_type"] == "interactive"
            assert "ts" in row

    def test_row_written_when_buffer_was_present(self):
        """Adaptation fix: provider_usage gets a row even when model wrote a rich buffer."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            existing_turn = {
                "event": "turn", "turn": 1, "session_id": "sess1",
                "user_intent": "", "assistant_text": "",
                "tools_used": [], "files_touched": [],
                "model": None, "input_tokens": 0, "output_tokens": 0,
                "cache_read_tokens": 0, "cache_creation_tokens": 0,
            }
            rows = [
                _user_entry("u1", "sess1", "Do X", ts="2026-06-06T10:00:00Z"),
                _assistant_entry("a1", "Done X.", model="claude-sonnet-4-6",
                                 in_tok=400, out_tok=120, ts="2026-06-06T10:00:06Z"),
            ]
            transcript = _make_transcript(rows, tmp)
            track_rel = "WAI-Spoke/sessions/s1/track.jsonl"
            track_path = tmp / track_rel
            _make_track([existing_turn], track_path)
            state = _make_state(track_rel, tmp)

            st.live(str(state), str(transcript), str(tmp), buffer_was_present=True)

            rows_usage = _read_usage(tmp)
            assert rows_usage, "provider_usage.jsonl should have a row even when buffer_was_present=True"
            row = rows_usage[0]
            assert row["model"] == "claude-sonnet-4-6"
            assert row["input_tokens"] == 400
            assert row["output_tokens"] == 120
            assert row["session_type"] == "interactive"


# ---------------------------------------------------------------------------
# AC6: backfill has no correction detection
# ---------------------------------------------------------------------------

class TestBackfillNoCorrectionDetection:
    def test_backfill_produces_no_correction_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [
                _user_entry("u1", "sess1", "No, don't do that"),
                _assistant_entry("a1", "OK."),
                _user_entry("u2", "sess1", "Stop, revert everything"),
                _assistant_entry("a2", "Reverted."),
            ]
            transcript = _make_transcript(rows, tmp)
            track_rel = "WAI-Spoke/sessions/s1/track.jsonl"
            track_path = tmp / track_rel
            track_path.parent.mkdir(parents=True, exist_ok=True)
            track_path.touch()
            state = _make_state(track_rel, tmp)

            st.backfill(str(state), str(transcript), str(tmp))

            entries = _read_track(track_path)
            corrections = [e for e in entries if e.get("event") == "correction"]
            assert not corrections, "backfill must not produce correction events"
            turns = [e for e in entries if e.get("event") == "turn"]
            assert len(turns) == 2


# ---------------------------------------------------------------------------
# Adaptation: buffer_was_present=True augments last track entry
# ---------------------------------------------------------------------------

class TestBufferPresentAugment:
    def test_augments_content_fields(self):
        """Rich buffer entry (empty content) gets user_intent + assistant_text from transcript."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            existing_turn = {
                "event": "turn", "turn": 1, "session_id": "sess1",
                "user_intent": "", "assistant_text": "",
                "tools_used": [], "files_touched": [],
                "summary": "model-authored insight",
            }
            rows = [
                _user_entry("u1", "sess1", "What is X?"),
                _assistant_entry("a1", "X is the answer."),
            ]
            transcript = _make_transcript(rows, tmp)
            track_rel = "WAI-Spoke/sessions/s1/track.jsonl"
            track_path = tmp / track_rel
            _make_track([existing_turn], track_path)
            state = _make_state(track_rel, tmp)

            st.live(str(state), str(transcript), str(tmp), buffer_was_present=True)

            entries = _read_track(track_path)
            t = [e for e in entries if e.get("event") == "turn"][0]
            assert t["user_intent"] == "What is X?"
            assert "X is the answer." in t["assistant_text"]
            assert t.get("summary") == "model-authored insight"  # existing field preserved

    def test_augments_token_fields(self):
        """Rich buffer entry (no tokens) gets model + token fields from transcript."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            existing_turn = {
                "event": "turn", "turn": 1, "session_id": "sess1",
                "user_intent": "", "assistant_text": "",
                "tools_used": [], "files_touched": [],
                "model": None, "input_tokens": 0, "output_tokens": 0,
                "cache_read_tokens": 0, "cache_creation_tokens": 0,
            }
            rows = [
                _user_entry("u1", "sess1", "Task"),
                _assistant_entry("a1", "Done.", model="claude-sonnet-4-6",
                                 in_tok=500, out_tok=200, cache_read=30, cache_create=15),
            ]
            transcript = _make_transcript(rows, tmp)
            track_rel = "WAI-Spoke/sessions/s1/track.jsonl"
            track_path = tmp / track_rel
            _make_track([existing_turn], track_path)
            state = _make_state(track_rel, tmp)

            st.live(str(state), str(transcript), str(tmp), buffer_was_present=True)

            entries = _read_track(track_path)
            t = [e for e in entries if e.get("event") == "turn"][0]
            assert t["model"] == "claude-sonnet-4-6"
            assert t["input_tokens"] == 500
            assert t["output_tokens"] == 200
            assert t["cache_read_tokens"] == 30
            assert t["cache_creation_tokens"] == 15

    def test_does_not_overwrite_existing_content(self):
        """Model-authored fields are not clobbered when already populated."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            existing_turn = {
                "event": "turn", "turn": 1, "session_id": "sess1",
                "user_intent": "original intent from model",
                "assistant_text": "original assistant text from model",
                "tools_used": [{"name": "Read", "count": 1}],
                "files_touched": ["/some/file.py"],
                "model": "claude-opus-4-8",
                "input_tokens": 999,
                "output_tokens": 888,
            }
            rows = [
                _user_entry("u1", "sess1", "Different transcript text"),
                _assistant_entry("a1", "Different transcript answer.", model="claude-haiku-4-5-20251001"),
            ]
            transcript = _make_transcript(rows, tmp)
            track_rel = "WAI-Spoke/sessions/s1/track.jsonl"
            track_path = tmp / track_rel
            _make_track([existing_turn], track_path)
            state = _make_state(track_rel, tmp)

            st.live(str(state), str(transcript), str(tmp), buffer_was_present=True)

            entries = _read_track(track_path)
            t = [e for e in entries if e.get("event") == "turn"][0]
            # All model-authored fields must be unchanged
            assert t["user_intent"] == "original intent from model"
            assert t["assistant_text"] == "original assistant text from model"
            assert t["model"] == "claude-opus-4-8"
            assert t["input_tokens"] == 999
            assert t["output_tokens"] == 888
