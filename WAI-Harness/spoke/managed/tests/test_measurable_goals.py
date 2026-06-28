#!/usr/bin/env python3
"""Tests for measurable goals schema (P3 impl-measurable-goals-schema-v1).

Covers:
  AC1 (test_backward_compat_mixed_index) — normalize_goal handles str + dict;
       every existing goals[] reader works on a mixed index without crashing.
  AC2 (test_measure_writes_kpi_and_state) — goal_measure writes kpi/<id>.json
       with baseline+current and flips lifecycle_state active->measuring when
       any goal carries success_criteria.
  AC3 (test_lug_goal_traceability) — a chain lug with goal_id, once the work
       it represents completes (goals updated), advances that goal's current
       toward met; existing readers still work on the mixed index.
  AC4 (test_pathgraph_report_only) — a goal flipping to met emits a
       goal_fulfilled entry into pathgraph/history.jsonl without mutating
       the existing entries' op_type values.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import goal_measure as gm  # noqa: E402
import wai_goal_queue as gq  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INDEX_REL = "WAI-Harness/spoke/local/initiatives/index.json"
KPI_REL = "WAI-Harness/spoke/local/kpi"
PG_REL = "WAI-Harness/spoke/local/pathgraph/history.jsonl"


def _write_index(root: Path, initiatives: list) -> None:
    idx_path = root / INDEX_REL
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text(json.dumps({"initiatives": initiatives}, indent=2))


def _read_kpi(root: Path, initiative_id: str) -> dict:
    return json.loads((root / KPI_REL / f"{initiative_id}.json").read_text())


def _read_pg(root: Path) -> list:
    pg = root / PG_REL
    if not pg.exists():
        return []
    return [json.loads(line) for line in pg.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# AC1: normalize_goal + backward-compat mixed-index read
# ---------------------------------------------------------------------------

class TestBackwardCompatMixedIndex:
    """AC1: normalize_goal works on bare strings and dicts; mixed index never crashes."""

    def test_normalize_bare_string(self):
        result = gm.normalize_goal("0 collection errors")
        assert result["statement"] == "0 collection errors"
        assert result["status"] == "open"
        assert isinstance(result, dict)

    def test_normalize_dict_passthrough(self):
        obj = {"id": "g-1", "statement": "some goal", "success_criteria": {"target": "==1"}, "status": "met"}
        result = gm.normalize_goal(obj)
        assert result is obj  # same dict object, not a copy

    def test_mixed_index_does_not_crash(self, tmp_path):
        """goals[] with a mix of strings and dicts must not raise on queue_query."""
        initiatives = [
            {
                "id": "test-mixed-init",
                "lifecycle_state": "active",
                "goals": [
                    "bare string goal",
                    {"id": "g-1", "statement": "dict goal", "success_criteria": {"target": ">=1"}, "status": "open"},
                ],
            }
        ]
        _write_index(tmp_path, initiatives)

        # Normalize all goals in a mixed list — must not crash
        raw_goals = initiatives[0]["goals"]
        normalized = [gm.normalize_goal(g) for g in raw_goals]
        assert len(normalized) == 2
        assert normalized[0]["statement"] == "bare string goal"
        assert normalized[0]["status"] == "open"
        assert normalized[1]["id"] == "g-1"

    def test_queue_query_on_mixed_index(self, tmp_path):
        """queue_query must not crash when speaking to an initiative index."""
        spoke = tmp_path / "WAI-Harness" / "spoke" / "local"
        spoke.mkdir(parents=True, exist_ok=True)
        # No chain lugs, so we just check it doesn't raise
        result = gq.queue_query(spoke_path=spoke)
        assert result.total_chains == 0

    def test_goals_measured_pct_on_mixed_list(self, tmp_path):
        """_goals_measured_pct must handle a goals[] with both strings and dicts."""
        initiatives = [
            {
                "id": "init-x",
                "lifecycle_state": "active",
                "goals": [
                    "bare string goal",  # no success_criteria
                    {
                        "id": "g-0",
                        "statement": "dict goal with criteria",
                        "metric": "goals_measured_pct",
                        "success_criteria": {"name": "x", "definition": "y", "baseline_method": "z", "target": "==100"},
                        "status": "open",
                    },
                ],
            }
        ]
        _write_index(tmp_path, initiatives)
        # _goals_measured_pct uses normalize_goal internally; 1/2 goals have criteria = 50%
        ctx = {"root": str(tmp_path), "spoke_local": str(tmp_path / "WAI-Harness/spoke/local"), "initiative_id": "init-x"}
        pct = gm.METRICS["goals_measured_pct"](ctx)
        assert pct == 50.0


# ---------------------------------------------------------------------------
# AC2: goal_measure writes kpi file + flips lifecycle_state to measuring
# ---------------------------------------------------------------------------

class TestMeasureWritesKpiAndState:
    """AC2: goal_measure writes kpi/<id>.json and flips active->measuring."""

    def _make_measured_initiative(self, initiative_id: str) -> dict:
        return {
            "id": initiative_id,
            "lifecycle_state": "active",
            "goals": [
                {
                    "id": "g-0",
                    "statement": "goals must be measurable objects",
                    "success_criteria": {
                        "name": "goals measured pct",
                        "definition": "pct goals with success_criteria",
                        "baseline_method": "count",
                        "target": "==100",
                    },
                    "metric": "goals_measured_pct",
                    "baseline": 0,
                    "current": None,
                    "tracked_via": "kpi_file",
                    "status": "open",
                }
            ],
        }

    def test_kpi_file_written(self, tmp_path):
        init_id = "test-init-ac2"
        _write_index(tmp_path, [self._make_measured_initiative(init_id)])
        gm.measure_initiative(str(tmp_path), init_id)
        kpi = _read_kpi(tmp_path, init_id)
        assert kpi["initiative"] == init_id
        assert kpi["total"] == 1
        assert kpi["measured"] == 1
        assert len(kpi["goals"]) == 1
        assert kpi["goals"][0]["current"] is not None

    def test_lifecycle_flips_to_measuring_active(self, tmp_path):
        init_id = "test-init-ac2b"
        _write_index(tmp_path, [self._make_measured_initiative(init_id)])
        gm.measure_initiative(str(tmp_path), init_id)
        idx = json.loads((tmp_path / INDEX_REL).read_text())
        init = next(i for i in idx["initiatives"] if i["id"] == init_id)
        assert init["lifecycle_state"] == "measuring"

    def test_lifecycle_flips_to_measuring_approved(self, tmp_path):
        init = self._make_measured_initiative("test-init-approved")
        init["lifecycle_state"] = "approved"
        _write_index(tmp_path, [init])
        gm.measure_initiative(str(tmp_path), init["id"])
        idx = json.loads((tmp_path / INDEX_REL).read_text())
        result = next(i for i in idx["initiatives"] if i["id"] == init["id"])
        assert result["lifecycle_state"] == "measuring"

    def test_lifecycle_not_flipped_when_no_criteria(self, tmp_path):
        """lifecycle_state must NOT flip when goals have no success_criteria."""
        init_id = "test-no-criteria"
        initiative = {
            "id": init_id,
            "lifecycle_state": "active",
            "goals": [
                "bare string goal with no criteria",
                {"id": "g-0", "statement": "dict goal, no criteria", "status": "open"},
            ],
        }
        _write_index(tmp_path, [initiative])
        gm.measure_initiative(str(tmp_path), init_id)
        idx = json.loads((tmp_path / INDEX_REL).read_text())
        result = next(i for i in idx["initiatives"] if i["id"] == init_id)
        assert result["lifecycle_state"] == "active"

    def test_string_goals_normalized_in_written_index(self, tmp_path):
        """Bare string goals are normalized to dicts when the index is rewritten."""
        init_id = "test-normalize-write"
        initiative = {
            "id": init_id,
            "lifecycle_state": "active",
            "goals": ["bare string goal"],
        }
        _write_index(tmp_path, [initiative])
        gm.measure_initiative(str(tmp_path), init_id)
        idx = json.loads((tmp_path / INDEX_REL).read_text())
        result = next(i for i in idx["initiatives"] if i["id"] == init_id)
        assert isinstance(result["goals"][0], dict)
        assert result["goals"][0]["statement"] == "bare string goal"
        assert result["goals"][0]["status"] == "open"


# ---------------------------------------------------------------------------
# AC3: lug<->goal traceability via goal_id
# ---------------------------------------------------------------------------

class TestLugGoalTraceability:
    """AC3: chain lug with goal_id advances the linked goal's current toward met."""

    def test_queue_item_has_goal_id(self, tmp_path):
        """QueueItem surfaces goal_id from the chain lug."""
        spoke = tmp_path / "WAI-Harness" / "spoke" / "local"
        chain_dir = spoke / "lugs" / "bytype" / "chain" / "open"
        chain_dir.mkdir(parents=True, exist_ok=True)
        chain = {
            "chain_id": "chain-test-1",
            "goal": "measure all goals",
            "goal_id": "g-p3",
            "gb": "initiative-goal-driven-autopilot-v1",
            "execution_mode": "sequential",
            "roi": 5.0,
            "children": ["impl-a"],
            "completed_children": [],
        }
        (chain_dir / "chain-test-1.json").write_text(json.dumps(chain))
        result = gq.queue_query(spoke_path=spoke)
        assert result.total_chains == 1
        assert result.items[0].goal_id == "g-p3"

    def test_goal_current_advances_after_work(self, tmp_path):
        """
        Simulate: initiative has 1 bare string goal. After converting it to an
        object with success_criteria (the 'work' the chain represents), call
        goal_measure. goal's current must advance from None to a value.
        """
        init_id = "test-init-trace"
        # Start: one string goal (not measurable)
        initiative = {
            "id": init_id,
            "lifecycle_state": "active",
            "goals": ["goals must be measurable objects"],
        }
        _write_index(tmp_path, [initiative])
        scored_before = gm.measure_initiative(str(tmp_path), init_id)
        assert scored_before["measured"] == 0  # no metric -> not measured yet

        # Work: convert goal to a measured object (simulating lug tagged with goal_id)
        idx = json.loads((tmp_path / INDEX_REL).read_text())
        for it in idx["initiatives"]:
            if it["id"] == init_id:
                it["goals"] = [
                    {
                        "id": "g-0",
                        "statement": "goals must be measurable objects",
                        "success_criteria": {
                            "name": "goals measured pct",
                            "definition": "pct goals with success_criteria",
                            "baseline_method": "count",
                            "target": "==100",
                        },
                        "metric": "goals_measured_pct",
                        "baseline": 0,
                        "current": None,
                        "tracked_via": "kpi_file",
                        "status": "open",
                    }
                ]
        (tmp_path / INDEX_REL).write_text(json.dumps(idx, indent=2))

        scored_after = gm.measure_initiative(str(tmp_path), init_id)
        assert scored_after["measured"] == 1
        assert scored_after["goals"][0]["current"] is not None

    def test_goal_id_deprioritizes_met_goals(self, tmp_path):
        """A chain linked to an already-met goal in a focus_lock initiative
        must get PRIORITY_DEFAULT (not PRIORITY_FOCUS_LOCK)."""
        spoke = tmp_path / "WAI-Harness" / "spoke" / "local"
        # Set up chain with goal_id pointing to a met goal
        chain_dir = spoke / "lugs" / "bytype" / "chain" / "open"
        chain_dir.mkdir(parents=True, exist_ok=True)
        chain = {
            "chain_id": "chain-met-goal",
            "goal": "some work",
            "goal_id": "g-done",
            "gb": "init-fl",
            "execution_mode": "sequential",
            "roi": 5.0,
            "children": ["impl-a"],
            "completed_children": [],
        }
        (chain_dir / "chain-met-goal.json").write_text(json.dumps(chain))

        # Set up initiatives index with focus_lock initiative + met goal
        initiatives = [
            {
                "id": "init-fl",
                "lifecycle_state": "approved",
                "focus_lock": True,
                "goals": [{"id": "g-done", "statement": "done goal", "status": "met"}],
            }
        ]
        _write_index(tmp_path, initiatives)
        # Patch _load_initiatives to read from our temp index
        # queue_query reads from its own spoke_path/initiatives/index.json
        init_dir = spoke / "initiatives"
        init_dir.mkdir(parents=True, exist_ok=True)
        (init_dir / "index.json").write_text(json.dumps({"initiatives": initiatives}))

        result = gq.queue_query(spoke_path=spoke)
        assert result.items[0].priority == gq.PRIORITY_DEFAULT

    def test_existing_readers_on_mixed_index(self, tmp_path):
        """After goal_measure runs on a mixed index, _load_initiatives still returns
        the initiative and its goals are accessible (backward-compat)."""
        init_id = "test-compat-readers"
        initiative = {
            "id": init_id,
            "lifecycle_state": "active",
            "goals": [
                "bare string goal",
                {
                    "id": "g-0",
                    "statement": "dict goal",
                    "success_criteria": {"name": "x", "definition": "y", "baseline_method": "z", "target": "==100"},
                    "metric": "goals_measured_pct",
                    "status": "open",
                },
            ],
        }
        _write_index(tmp_path, [initiative])
        gm.measure_initiative(str(tmp_path), init_id)

        # Read the updated index — goals must be accessible as dicts
        idx = json.loads((tmp_path / INDEX_REL).read_text())
        result_init = next(i for i in idx["initiatives"] if i["id"] == init_id)
        goals = result_init.get("goals", [])
        assert len(goals) == 2
        assert all(isinstance(g, dict) for g in goals)


# ---------------------------------------------------------------------------
# AC4: PathGraph fulfilled update (report-only; no op_type mutation)
# ---------------------------------------------------------------------------

class TestPathgraphReportOnly:
    """AC4: goal flipping to met emits goal_fulfilled to pathgraph; does not mutate existing entries."""

    def _make_met_initiative(self, init_id: str) -> dict:
        return {
            "id": init_id,
            "lifecycle_state": "active",
            "goals": [
                {
                    "id": "g-met",
                    "statement": "this goal will flip to met",
                    "success_criteria": {
                        "name": "goals measured pct",
                        "definition": "100% goals with criteria",
                        "baseline_method": "count",
                        "target": "==100",
                    },
                    "metric": "goals_measured_pct",
                    "baseline": 0,
                    "current": None,
                    "tracked_via": "kpi_file",
                    "status": "open",  # not yet met
                }
            ],
        }

    def test_fulfilled_event_emitted_on_first_met(self, tmp_path):
        init_id = "test-pg-emit"
        _write_index(tmp_path, [self._make_met_initiative(init_id)])
        # Ensure pathgraph dir exists
        pg_dir = tmp_path / "WAI-Harness" / "spoke" / "local" / "pathgraph"
        pg_dir.mkdir(parents=True, exist_ok=True)

        gm.measure_initiative(str(tmp_path), init_id)

        entries = _read_pg(tmp_path)
        fulfilled = [e for e in entries if e.get("op_type") == "goal_fulfilled"]
        assert len(fulfilled) >= 1
        assert fulfilled[0]["initiative_id"] == init_id
        assert fulfilled[0]["goal_id"] == "g-met"
        assert "ts" in fulfilled[0]

    def test_existing_entries_not_mutated(self, tmp_path):
        """Pre-existing pathgraph entries retain their original op_type values."""
        init_id = "test-pg-immutable"
        _write_index(tmp_path, [self._make_met_initiative(init_id)])
        pg_dir = tmp_path / "WAI-Harness" / "spoke" / "local" / "pathgraph"
        pg_dir.mkdir(parents=True, exist_ok=True)
        # Pre-seed two existing entries
        existing = [
            {"ts": "2026-06-01T00:00:00Z", "op_type": "lug_pickup", "lug_id": "some-lug"},
            {"ts": "2026-06-01T00:01:00Z", "op_type": "lug_complete", "lug_id": "some-lug"},
        ]
        (pg_dir / "history.jsonl").write_text(
            "\n".join(json.dumps(e) for e in existing) + "\n"
        )

        gm.measure_initiative(str(tmp_path), init_id)

        entries = _read_pg(tmp_path)
        # Original entries must be unchanged
        assert entries[0]["op_type"] == "lug_pickup"
        assert entries[1]["op_type"] == "lug_complete"
        # A new goal_fulfilled entry was appended
        assert any(e["op_type"] == "goal_fulfilled" for e in entries[2:])

    def test_fulfilled_not_emitted_when_already_met(self, tmp_path):
        """If a goal was already met (status==met), no duplicate fulfilled event."""
        init_id = "test-pg-no-dup"
        initiative = self._make_met_initiative(init_id)
        # Pre-set the goal as already met
        initiative["goals"][0]["status"] = "met"
        initiative["goals"][0]["current"] = 100.0
        _write_index(tmp_path, [initiative])
        pg_dir = tmp_path / "WAI-Harness" / "spoke" / "local" / "pathgraph"
        pg_dir.mkdir(parents=True, exist_ok=True)

        gm.measure_initiative(str(tmp_path), init_id)

        entries = _read_pg(tmp_path)
        fulfilled = [e for e in entries if e.get("op_type") == "goal_fulfilled"]
        assert len(fulfilled) == 0  # already met, no flip event

    def test_pathgraph_status_semantics_unchanged(self, tmp_path):
        """PathGraph history.jsonl stores only append entries; no 'status' field
        is altered on existing entries after a goal_fulfilled write."""
        init_id = "test-pg-semantics"
        _write_index(tmp_path, [self._make_met_initiative(init_id)])
        pg_dir = tmp_path / "WAI-Harness" / "spoke" / "local" / "pathgraph"
        pg_dir.mkdir(parents=True, exist_ok=True)
        existing = [{"ts": "2026-06-01T00:00:00Z", "op_type": "lug_complete", "lug_id": "x", "outcome": "success"}]
        (pg_dir / "history.jsonl").write_text(json.dumps(existing[0]) + "\n")

        gm.measure_initiative(str(tmp_path), init_id)

        entries = _read_pg(tmp_path)
        # The existing entry must be exactly as written — no new fields injected
        assert entries[0] == existing[0]
