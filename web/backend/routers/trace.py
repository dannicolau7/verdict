"""Trace evaluation endpoint.

POST /api/trace/run  — multipart file upload (AgentTrace JSON), SSE stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/trace/run")
async def run_trace_eval(
    file: UploadFile,
    judge_model: Annotated[str, Form()] = "claude-sonnet-4-6",
) -> StreamingResponse:
    """Upload AgentTrace JSON → run trace judge → SSE stream progress + report."""
    content = await file.read()
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def emit(event_type: str, detail: str) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait, _sse({"type": event_type, "detail": detail})
        )

    async def _run() -> None:
        try:
            from verdict.adapters.trace_ingestor import load_traces
            from verdict.agents.trace_judge import judge_traces
            from verdict.reports.trace_builder import build_trace_eval_report

            # Parse
            emit("parse", "Parsing trace file…")
            try:
                raw = json.loads(content)
            except json.JSONDecodeError as exc:
                await queue.put(_sse({"type": "error", "message": f"Invalid JSON: {exc}"}))
                return

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as f:
                json.dump(raw, f)
                tmp_path = Path(f.name)

            try:
                traces = load_traces(tmp_path)
            except (ValueError, FileNotFoundError) as exc:
                tmp_path.unlink(missing_ok=True)
                await queue.put(_sse({"type": "error", "message": str(exc)}))
                return
            finally:
                tmp_path.unlink(missing_ok=True)

            agent_name = traces[0].agent_name if traces else "unknown"
            n = len(traces)
            emit("parse", f"{n} trace{'s' if n != 1 else ''} loaded for agent '{agent_name}'.")

            # Judge each trace individually so we can emit per-trace progress
            judgments = []
            for i, trace in enumerate(traces):
                emit("judge", f"Judging trace {i + 1} of {n}: {trace.task[:70]}…")
                result = await asyncio.to_thread(judge_traces, [trace], [judge_model])
                judgments.extend(result)
                status = "PASS" if result[0].overall_passed else "FAIL"
                score_str = f" (score {result[0].overall_score}/5)" if result[0].overall_score else ""
                emit("judge", f"Trace {i + 1} → {status}{score_str}")

            # Build report
            emit("build", "Building trace eval report…")
            report = await asyncio.to_thread(build_trace_eval_report, judgments, agent_name)

            await queue.put(_sse({
                "type": "complete",
                "report": report.model_dump(mode="json"),
                "traces": [t.model_dump(mode="json") for t in traces],
            }))

        except Exception as exc:
            logger.exception("Trace eval failed")
            await queue.put(_sse({"type": "error", "message": str(exc)}))
        finally:
            await queue.put(None)

    asyncio.create_task(_run())

    async def generate():
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
