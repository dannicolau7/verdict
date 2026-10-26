"""Read production traces into AgentTraces: Verdict JSON, JSONL, OpenTelemetry, LangSmith.

    load_any(path, fmt="auto") -> (format, list[AgentTrace])

Formats
    verdict    AgentTrace JSON file or a directory of them
    jsonl      one object per line: input/prompt/question, output/response/answer,
               optional tool_calls (name, arguments, result, error), id, agent
    otel       OTLP/JSON export ({"resourceSpans": [...]}, one object or one per line),
               GenAI (gen_ai.*) or OpenInference (input.value, tool.name, …) attributes
    langsmith  run export: JSON array or JSONL of runs with run_type, inputs, outputs,
               trace_id and parent_run_id

Only the standard library is used; nothing here calls a network service.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from verdict.models.trace_schemas import AgentTrace, TraceStep

FORMATS = ("verdict", "jsonl", "otel", "langsmith")


class TraceImportError(ValueError):
    """Raised when a trace file cannot be read as the requested format."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _text(value: Any) -> str | None:
    """Best-effort text from strings, chat messages, or common wrapper dicts."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        # chat messages: prefer the last user message, else the last message
        msgs = [m for m in value if isinstance(m, dict)]
        users = [m for m in msgs if m.get("role") in ("user", "human")]
        if users or msgs:
            pick = (users or msgs)[-1]
            return _text(pick.get("content") if "content" in pick else pick)
        return " ".join(t for t in (_text(v) for v in value) if t)
    if isinstance(value, dict):
        for key in ("content", "text", "input", "question", "query", "prompt", "output",
                    "answer", "response", "result", "messages", "generations"):
            if key in value:
                return _text(value[key])
        return json.dumps(value, sort_keys=True)
    return str(value)


def _first(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _args(value: Any) -> dict[str, Any]:
    value = _maybe_json(value)
    if isinstance(value, dict):
        return value
    return {} if value is None else {"input": value}


def _read_records(path: Path) -> list[Any]:
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("["):
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    if stripped.startswith("{"):
        try:
            return [json.loads(text)]
        except json.JSONDecodeError:
            pass  # not a single object: fall through to JSONL
    out = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if s and not s.startswith("#"):
            try:
                out.append(json.loads(s))
            except json.JSONDecodeError as exc:
                raise TraceImportError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    return out


def _build(
    trace_id: str,
    agent: str,
    task: str | None,
    steps: list[TraceStep],
    output: str | None,
    error: str | None = None,
    tools: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AgentTrace:
    if output is not None and not any(s.step_type == "final_answer" for s in steps):
        steps = steps + [TraceStep(step_id=len(steps), step_type="final_answer", llm_output=output)]
    return AgentTrace(
        trace_id=trace_id,
        agent_name=agent or "unknown",
        task=task or "",
        expected_behavior="",
        tools_available=tools or sorted({s.tool_name for s in steps if s.tool_name}),
        steps=steps,
        final_output=output,
        error=error,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Generic JSONL
# ---------------------------------------------------------------------------


def _from_jsonl(records: list[Any], path: Path) -> list[AgentTrace]:
    traces = []
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise TraceImportError(f"{path}: record {i} is not an object")
        task = _text(_first(r, "input", "prompt", "question", "query", "messages", "inputs"))
        output = _text(_first(r, "output", "response", "answer", "completion", "outputs"))
        if task is None:
            raise TraceImportError(f"{path}: record {i} has no input/prompt/question")
        steps = []
        for j, c in enumerate(_first(r, "tool_calls", "steps", "tools") or []):
            if not isinstance(c, dict):
                continue
            steps.append(TraceStep(
                step_id=j,
                step_type="tool_call",
                tool_name=str(_first(c, "name", "tool", "tool_name") or "tool"),
                tool_arguments=_args(_first(c, "arguments", "args", "input", "parameters")),
                tool_result=_text(_first(c, "result", "output")),
                error=_text(c.get("error")),
            ))
        traces.append(_build(
            str(_first(r, "id", "trace_id", "run_id") or f"{path.stem}-{i + 1}"),
            str(_first(r, "agent", "agent_name", "app") or path.stem),
            task, steps, output, _text(r.get("error")),
            metadata={k: v for k, v in r.items() if k in ("tags", "user_feedback", "score")},
        ))
    return traces


# ---------------------------------------------------------------------------
# OpenTelemetry (OTLP/JSON)
# ---------------------------------------------------------------------------


def _otel_value(v: dict[str, Any]) -> Any:
    for key in ("stringValue", "boolValue", "doubleValue"):
        if key in v:
            return v[key]
    if "intValue" in v:
        return int(v["intValue"])
    if "arrayValue" in v:
        return [_otel_value(x) for x in v["arrayValue"].get("values", [])]
    if "kvlistValue" in v:
        return {kv["key"]: _otel_value(kv.get("value", {})) for kv in v["kvlistValue"].get("values", [])}
    return None


def _attrs(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {a["key"]: _otel_value(a.get("value", {})) for a in items or [] if "key" in a}


_IN = ("gen_ai.prompt", "gen_ai.input.messages", "input.value", "llm.input_messages")
_OUT = ("gen_ai.completion", "gen_ai.output.messages", "output.value", "llm.output_messages")


def _from_otel(records: list[Any], path: Path) -> list[AgentTrace]:
    spans: dict[str, list[dict[str, Any]]] = defaultdict(list)
    service: dict[str, str] = {}
    for rec in records:
        if not isinstance(rec, dict) or "resourceSpans" not in rec:
            raise TraceImportError(f"{path}: expected OTLP/JSON with 'resourceSpans'")
        for rs in rec["resourceSpans"]:
            res = _attrs(rs.get("resource", {}).get("attributes"))
            for ss in rs.get("scopeSpans", rs.get("instrumentationLibrarySpans", [])):
                for sp in ss.get("spans", []):
                    sp = {**sp, "_attrs": _attrs(sp.get("attributes"))}
                    spans[sp["traceId"]].append(sp)
                    service.setdefault(sp["traceId"], str(res.get("service.name", path.stem)))

    traces = []
    for tid, group in spans.items():
        group.sort(key=lambda s: int(s.get("startTimeUnixNano", 0)))
        root = next((s for s in group if not s.get("parentSpanId")), group[0])
        ra = root["_attrs"]
        task = _text(_maybe_json(_first(ra, *_IN)))
        output = _text(_maybe_json(_first(ra, *_OUT)))
        steps: list[TraceStep] = []
        for sp in group:
            a = sp["_attrs"]
            tool = a.get("gen_ai.tool.name") or a.get("tool.name")
            if tool is None and str(sp.get("name", "")).startswith("execute_tool "):
                tool = sp["name"].split(" ", 1)[1]
            status = sp.get("status", {})
            err = status.get("message") or ("error" if status.get("code") in (2, "STATUS_CODE_ERROR") else None)
            dur = (int(sp.get("endTimeUnixNano", 0)) - int(sp.get("startTimeUnixNano", 0))) / 1e6
            if tool:
                steps.append(TraceStep(
                    step_id=len(steps), step_type="tool_call", tool_name=str(tool),
                    tool_arguments=_args(_first(a, "gen_ai.tool.call.arguments", "tool.parameters", "input.value")),
                    tool_result=_text(_maybe_json(_first(a, "gen_ai.tool.call.result", "output.value"))),
                    error=err, latency_ms=max(dur, 0.0),
                ))
            elif sp is not root and _first(a, *_IN, *_OUT) is not None:
                if task is None:
                    task = _text(_maybe_json(_first(a, *_IN)))
                steps.append(TraceStep(
                    step_id=len(steps), step_type="llm_call",
                    llm_input=_text(_maybe_json(_first(a, *_IN))),
                    llm_output=_text(_maybe_json(_first(a, *_OUT))),
                    error=err, latency_ms=max(dur, 0.0),
                ))
        if output is None:
            outs = [s.llm_output for s in steps if s.step_type == "llm_call" and s.llm_output]
            output = outs[-1] if outs else None
        rs_ = root.get("status", {})
        root_err = rs_.get("message") if rs_.get("code") in (2, "STATUS_CODE_ERROR") else None
        traces.append(_build(tid, service.get(tid, path.stem), task, steps, output, root_err))
    return traces


# ---------------------------------------------------------------------------
# LangSmith run export
# ---------------------------------------------------------------------------


def _from_langsmith(records: list[Any], path: Path) -> list[AgentTrace]:
    runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        if not isinstance(r, dict) or "run_type" not in r:
            raise TraceImportError(f"{path}: expected LangSmith runs with 'run_type'")
        runs[str(r.get("trace_id") or r.get("id"))].append(r)

    traces = []
    for tid, group in runs.items():
        group.sort(key=lambda r: str(r.get("start_time") or ""))
        root = next((r for r in group if not r.get("parent_run_id")), group[0])
        steps = [
            TraceStep(
                step_id=i, step_type="tool_call", tool_name=str(r.get("name") or "tool"),
                tool_arguments=_args(_maybe_json((r.get("inputs") or {}).get("input", r.get("inputs")))),
                tool_result=_text((r.get("outputs") or {}).get("output", r.get("outputs"))),
                error=r.get("error"),
            )
            for i, r in enumerate(x for x in group if x.get("run_type") == "tool")
        ]
        feedback = root.get("feedback_stats") or root.get("feedback")
        traces.append(_build(
            tid, str(root.get("name") or path.stem),
            _text(root.get("inputs")), steps, _text(root.get("outputs")), root.get("error"),
            metadata={"feedback": feedback} if feedback else None,
        ))
    return traces


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def detect_format(path: Path, records: list[Any] | None = None) -> str:
    if path.is_dir():
        return "verdict"
    records = _read_records(path) if records is None else records
    head = next((r for r in records if isinstance(r, dict)), {})
    if "resourceSpans" in head:
        return "otel"
    if "run_type" in head:
        return "langsmith"
    if "steps" in head and "task" in head:
        return "verdict"
    return "jsonl"


def load_any(path: str | Path, fmt: str = "auto") -> tuple[str, list[AgentTrace]]:
    p = Path(path)
    if not p.exists():
        raise TraceImportError(f"not found: {p}")
    if fmt not in ("auto", *FORMATS):
        raise TraceImportError(f"unknown format {fmt!r}; use one of auto, {', '.join(FORMATS)}")
    try:
        records = None if p.is_dir() else _read_records(p)
    except json.JSONDecodeError as exc:
        raise TraceImportError(f"{p}: invalid JSON: {exc}") from exc
    fmt = detect_format(p, records) if fmt == "auto" else fmt
    if fmt == "verdict":
        from verdict.adapters.trace_ingestor import load_traces

        try:
            if p.is_dir():
                return fmt, load_traces(p)
            return fmt, [AgentTrace(**r) for r in records or []]
        except (ValueError, TypeError) as exc:
            raise TraceImportError(f"{p}: not valid AgentTrace JSON: {exc}") from exc
    assert records is not None
    parser = {"jsonl": _from_jsonl, "otel": _from_otel, "langsmith": _from_langsmith}[fmt]
    try:
        traces = parser(records, p)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, TraceImportError):
            raise
        raise TraceImportError(f"{p}: could not read as {fmt}: {exc}") from exc
    if not traces:
        raise TraceImportError(f"{p}: no traces found")
    return fmt, traces
