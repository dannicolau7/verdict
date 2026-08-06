"""Unit tests for verdict.adapters.trace_ingestor. No LLM calls."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from verdict.adapters.trace_ingestor import load_trace, load_traces
from verdict.models.trace_schemas import AgentTrace

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _minimal_trace_dict(**overrides) -> dict:
    base = {
        "trace_id": str(uuid.uuid4()),
        "agent_name": "test-agent",
        "task": "Perform the test task.",
        "expected_behavior": "Do it correctly and completely.",
        "tools_available": ["tool_a", "tool_b"],
        "steps": [
            {"step_id": 0, "step_type": "llm_call", "llm_output": "Planning…"},
            {"step_id": 1, "step_type": "final_answer", "llm_output": "Done."},
        ],
    }
    base.update(overrides)
    return base


def _write_trace(tmp_path: Path, data: dict, filename: str = "trace.json") -> Path:
    p = tmp_path / filename
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# load_trace
# ---------------------------------------------------------------------------

class TestLoadTrace:
    def test_loads_valid_trace(self, tmp_path: Path):
        p = _write_trace(tmp_path, _minimal_trace_dict())
        trace = load_trace(p)
        assert isinstance(trace, AgentTrace)
        assert trace.agent_name == "test-agent"

    def test_single_item_array_accepted(self, tmp_path: Path):
        p = tmp_path / "trace.json"
        p.write_text(json.dumps([_minimal_trace_dict()]), encoding="utf-8")
        trace = load_trace(p)
        assert isinstance(trace, AgentTrace)

    def test_multi_item_array_rejected(self, tmp_path: Path):
        p = tmp_path / "traces.json"
        p.write_text(json.dumps([_minimal_trace_dict(), _minimal_trace_dict()]), encoding="utf-8")
        with pytest.raises(ValueError, match="load_traces"):
            load_trace(p)

    def test_missing_required_field_rejected(self, tmp_path: Path):
        bad = _minimal_trace_dict()
        del bad["task"]
        p = _write_trace(tmp_path, bad)
        with pytest.raises(ValueError, match="Schema validation"):
            load_trace(p)

    def test_invalid_json_rejected(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_trace(p)

    def test_file_not_found_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_trace(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# load_traces
# ---------------------------------------------------------------------------

class TestLoadTraces:
    def test_loads_directory_of_traces(self, tmp_path: Path):
        for i in range(3):
            _write_trace(tmp_path, _minimal_trace_dict(agent_name=f"agent-{i}"), f"t{i}.json")
        traces = load_traces(tmp_path)
        assert len(traces) == 3
        assert all(isinstance(t, AgentTrace) for t in traces)

    def test_loads_single_object_file(self, tmp_path: Path):
        p = _write_trace(tmp_path, _minimal_trace_dict())
        traces = load_traces(p)
        assert len(traces) == 1

    def test_loads_array_file(self, tmp_path: Path):
        p = tmp_path / "multi.json"
        p.write_text(json.dumps([_minimal_trace_dict(), _minimal_trace_dict()]), encoding="utf-8")
        traces = load_traces(p)
        assert len(traces) == 2

    def test_empty_directory_raises(self, tmp_path: Path):
        sub = tmp_path / "empty"
        sub.mkdir()
        with pytest.raises(ValueError, match="No \\*.json"):
            load_traces(sub)

    def test_path_not_found_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_traces(tmp_path / "missing")

    def test_invalid_schema_in_array_raises(self, tmp_path: Path):
        p = tmp_path / "bad.json"
        bad = _minimal_trace_dict()
        del bad["agent_name"]
        p.write_text(json.dumps([bad]), encoding="utf-8")
        with pytest.raises(ValueError, match="Schema validation"):
            load_traces(p)

    def test_directory_skips_non_json_files(self, tmp_path: Path):
        _write_trace(tmp_path, _minimal_trace_dict(), "good.json")
        (tmp_path / "readme.txt").write_text("not json", encoding="utf-8")
        traces = load_traces(tmp_path)
        assert len(traces) == 1
