"""POST /api/eval/run — streams Server-Sent Events as the eval progresses.

Event stream format (each line: "data: <json>\n\n"):
  {"type": "progress", "stage": "generate", "detail": "…"}
  {"type": "complete",  "report": {…EvalReport…}}
  {"type": "error",     "message": "…"}
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..models.api_models import EvalRunRequest
from ..store import run_store

logger = logging.getLogger(__name__)
router = APIRouter()


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/eval/run")
async def run_eval(req: EvalRunRequest) -> StreamingResponse:
    """Start an evaluation and stream progress as SSE."""
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_progress(stage: str, detail: str) -> None:
        event = _sse({"type": "progress", "stage": stage, "detail": detail})
        loop.call_soon_threadsafe(queue.put_nowait, event)

    async def _run() -> None:
        try:
            from verdict.adapters.simple_rag import SimpleRAGAdapter
            from verdict.caching.cache import CacheMode
            from verdict.crews.eval_crew import EvalCrew
            from verdict.models.schemas import TestPrompt

            pinned = [
                TestPrompt(
                    prompt=text.strip(),
                    category=req.custom_category,
                    severity="medium",
                    expected_behavior="User-defined custom prompt.",
                )
                for text in req.custom_prompts
                if text.strip()
            ]

            adapter = SimpleRAGAdapter(cache_mode=CacheMode.off, cache_dir=".verdict_cache")
            crew = EvalCrew(
                adapter=adapter,
                num_per_category=req.num_per_category,
                categories=req.categories if req.categories else None,
                model=req.judge_model,
                bootstrap_iterations=1000 if req.enable_ci else 0,
                adaptive=req.attack_mode == "adaptive",
                pinned_prompts=pinned,
            )
            result = await asyncio.to_thread(
                lambda: crew.kickoff(on_progress=on_progress)
            )

            report = result.report
            report_dict = report.model_dump(mode="json")

            # Normalise category_breakdown for the API schema
            norm: dict = {}
            for cat, stats in report_dict.get("category_breakdown", {}).items():
                norm[cat] = {
                    "total": stats.get("total", 0),
                    "passed": stats.get("passed", 0),
                    "failed": stats.get("failed", 0),
                    "pass_rate": stats.get("pass_rate", 0.0),
                    "failure_modes": stats.get("failure_modes", {}),
                    "critical_failures": stats.get("critical_failures", []),
                }
            report_dict["category_breakdown"] = norm

            run_store.save(report.run_id, report_dict)
            await queue.put(_sse({"type": "complete", "report": report_dict}))

        except Exception as exc:
            logger.exception("Eval run failed")
            await queue.put(_sse({"type": "error", "message": str(exc)}))
        finally:
            await queue.put(None)  # sentinel

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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
