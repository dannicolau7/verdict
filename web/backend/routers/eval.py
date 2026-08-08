"""POST /api/eval/run — streams Server-Sent Events as the eval progresses.

Uses standalone pipeline functions (no CrewAI dependency):
  generate_test_suite → execute_test_suite → judge_results → build_eval_report

Event stream format (each line: "data: <json>\n\n"):
  {"type": "progress", "stage": "generate|execute|judge|report", "detail": "…"}
  {"type": "complete",  "report": {…EvalReport…}}
  {"type": "error",     "message": "…"}
"""

from __future__ import annotations

import asyncio
import json
import logging

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

    def emit(stage: str, detail: str) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait, _sse({"type": "progress", "stage": stage, "detail": detail})
        )

    async def _run() -> None:
        try:
            from verdict.adapters.simple_rag import SimpleRAGAdapter
            from verdict.agents.executor import execute_test_suite
            from verdict.agents.judge import judge_results
            from verdict.agents.test_generator import generate_test_suite
            from verdict.caching.cache import CacheMode
            from verdict.models.schemas import TestPrompt
            from verdict.reports.builder import build_eval_report

            # 1. Pinned custom prompts
            pinned: list[TestPrompt] = [
                TestPrompt(
                    prompt=text.strip(),
                    category=req.custom_category,
                    severity="medium",
                    expected_behavior="User-defined custom prompt.",
                )
                for text in req.custom_prompts
                if text.strip()
            ]

            # 2. Generate
            emit("generate", f"Generating {req.num_per_category} prompts per category…")
            generated = await asyncio.to_thread(
                generate_test_suite,
                num_per_category=req.num_per_category,
                categories=req.categories if req.categories else None,
            )
            prompts = pinned + generated
            emit("generate", f"{len(prompts)} prompts ready ({len(pinned)} pinned).")

            # 3. Execute
            adapter = SimpleRAGAdapter(cache_mode=CacheMode.OFF, cache_dir=".verdict_cache")
            emit("execute", f"Executing {len(prompts)} prompts against SimpleRAG…")
            results = await execute_test_suite(prompts, adapter)
            emit("execute", f"{len(results)} responses received.")

            # 4. Judge
            emit("judge", f"Judging with {req.judge_model}…")
            judgments = await asyncio.to_thread(
                judge_results, prompts, results, [req.judge_model]
            )
            passed = sum(1 for j in judgments if j.passed)
            emit("judge", f"{passed}/{len(judgments)} passed.")

            # 5. Build report
            import uuid as _uuid
            emit("report", "Building evaluation report…")
            report = await asyncio.to_thread(
                build_eval_report,
                judgments=judgments,
                prompts=prompts,
                target_name=adapter.name,
                run_id=_uuid.uuid4().hex[:12],
                target_version=adapter.version,
                bootstrap_iterations=1000 if req.enable_ci else 0,
            )

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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
