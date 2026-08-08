"""Diff endpoints.

POST /api/diff/compare  — aggregate diff between two completed runs (no LLM)
POST /api/diff/run      — fresh diff: shared test suite, two adapters, SSE stream
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..models.api_models import (
    CategoryDiff,
    DiffRunRequest,
    DiffRunResponse,
    PerPromptRow,
)
from ..store import run_store

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Historical compare
# ---------------------------------------------------------------------------

class DiffCompareRequest(BaseModel):
    run_id_a: str
    run_id_b: str


class DiffCompareResponse(BaseModel):
    run_id_a: str
    run_id_b: str
    target_a: str
    target_b: str
    timestamp_a: str
    timestamp_b: str
    a_pass_rate: float
    b_pass_rate: float
    pass_rate_delta: float
    a_total_tests: int
    b_total_tests: int
    categories: list[CategoryDiff]


@router.post("/diff/compare", response_model=DiffCompareResponse)
async def compare_runs(req: DiffCompareRequest) -> DiffCompareResponse:
    """Aggregate diff between two historical runs — no new LLM calls."""
    run_a = run_store.get(req.run_id_a)
    run_b = run_store.get(req.run_id_b)
    if run_a is None:
        raise HTTPException(status_code=404, detail=f"Run {req.run_id_a!r} not found.")
    if run_b is None:
        raise HTTPException(status_code=404, detail=f"Run {req.run_id_b!r} not found.")
    if req.run_id_a == req.run_id_b:
        raise HTTPException(status_code=400, detail="Run A and Run B must be different.")

    cats_a: dict = run_a.get("category_breakdown", {})
    cats_b: dict = run_b.get("category_breakdown", {})
    all_cats = sorted(set(cats_a) | set(cats_b))

    categories: list[CategoryDiff] = []
    for cat in all_cats:
        a_stats = cats_a.get(cat)
        b_stats = cats_b.get(cat)
        a_rate = a_stats["pass_rate"] if a_stats else None
        b_rate = b_stats["pass_rate"] if b_stats else None
        delta = round(b_rate - a_rate, 4) if (a_rate is not None and b_rate is not None) else None
        categories.append(CategoryDiff(
            category=cat,
            a_pass_rate=a_rate,
            b_pass_rate=b_rate,
            delta=delta,
            a_total=a_stats["total"] if a_stats else 0,
            b_total=b_stats["total"] if b_stats else 0,
        ))

    return DiffCompareResponse(
        run_id_a=req.run_id_a,
        run_id_b=req.run_id_b,
        target_a=run_a["target_system"],
        target_b=run_b["target_system"],
        timestamp_a=run_a["timestamp"],
        timestamp_b=run_b["timestamp"],
        a_pass_rate=run_a["pass_rate"],
        b_pass_rate=run_b["pass_rate"],
        pass_rate_delta=round(run_b["pass_rate"] - run_a["pass_rate"], 4),
        a_total_tests=run_a["total_tests"],
        b_total_tests=run_b["total_tests"],
        categories=categories,
    )


# ---------------------------------------------------------------------------
# Fresh run diff
# ---------------------------------------------------------------------------

def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _category_diffs(per_judgment: list[dict]) -> list[CategoryDiff]:
    cats: dict = defaultdict(lambda: {"a_pass": 0, "b_pass": 0, "total": 0})
    for j in per_judgment:
        cat = j["category"]
        cats[cat]["total"] += 1
        if j["a_passed"]:
            cats[cat]["a_pass"] += 1
        if j["b_passed"]:
            cats[cat]["b_pass"] += 1
    result = []
    for cat, c in sorted(cats.items()):
        a_rate = round(c["a_pass"] / c["total"], 4) if c["total"] else 0.0
        b_rate = round(c["b_pass"] / c["total"], 4) if c["total"] else 0.0
        result.append(CategoryDiff(
            category=cat,
            a_pass_rate=a_rate,
            b_pass_rate=b_rate,
            delta=round(b_rate - a_rate, 4),
            a_total=c["total"],
            b_total=c["total"],
        ))
    return result


@router.post("/diff/run")
async def run_diff_fresh(req: DiffRunRequest) -> StreamingResponse:
    """Run a fresh diff: one shared test suite, two adapter configurations, SSE stream."""
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def on_progress(stage: str, detail: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, _sse({"type": "progress", "stage": stage, "detail": detail}))

    async def _run() -> None:
        try:
            from verdict.adapters.simple_rag import SimpleRAGAdapter
            from verdict.agents.executor import execute_test_suite
            from verdict.agents.judge import judge_results
            from verdict.agents.test_generator import generate_test_suite
            from verdict.caching.cache import CacheMode

            adapter_a = SimpleRAGAdapter(response_model=req.model_a, cache_mode=CacheMode.OFF)
            adapter_b = SimpleRAGAdapter(response_model=req.model_b, cache_mode=CacheMode.OFF)

            # 1. Generate shared suite
            on_progress("generate", f"Generating {req.num_per_category} prompts per category…")
            prompts = await asyncio.to_thread(
                generate_test_suite,
                num_per_category=req.num_per_category,
                categories=req.categories or None,
            )
            on_progress("generate", f"{len(prompts)} prompts generated.")

            # 2. Execute both adapters concurrently
            on_progress("execute", f"Executing against {req.model_a} and {req.model_b} concurrently…")
            results_a, results_b = await asyncio.gather(
                execute_test_suite(prompts, adapter_a),
                execute_test_suite(prompts, adapter_b),
            )
            on_progress("execute", f"{len(results_a)} + {len(results_b)} responses received.")

            # 3. Judge both
            on_progress("judge", f"Judging adapter A ({req.model_a})…")
            judgments_a = await asyncio.to_thread(
                judge_results, prompts, results_a, [req.judge_model]
            )
            on_progress("judge", f"Judging adapter B ({req.model_b})…")
            judgments_b = await asyncio.to_thread(
                judge_results, prompts, results_b, [req.judge_model]
            )

            # 4. Build per-prompt comparison
            on_progress("report", "Building diff report…")
            prompt_map = {p.id: p for p in prompts}
            ja_map = {j.prompt_id: j for j in judgments_a}
            jb_map = {j.prompt_id: j for j in judgments_b}

            per_judgment: list[dict] = []
            regressions: list[PerPromptRow] = []
            improvements: list[PerPromptRow] = []
            unchanged = 0
            a_pass = b_pass = 0

            for pid, ja in ja_map.items():
                jb = jb_map.get(pid)
                if jb is None:
                    continue
                p = prompt_map.get(pid)
                if ja.passed:
                    a_pass += 1
                if jb.passed:
                    b_pass += 1

                row = {
                    "prompt_id": pid,
                    "prompt_text": (p.prompt[:120] if p else ""),
                    "category": (p.category if p else "unknown"),
                    "severity": (p.severity if p else "medium"),
                    "a_passed": ja.passed,
                    "b_passed": jb.passed,
                    "a_failure_mode": ja.failure_mode.value if ja.failure_mode else None,
                    "b_failure_mode": jb.failure_mode.value if jb.failure_mode else None,
                    "a_reasoning": ja.reasoning[:200],
                    "b_reasoning": jb.reasoning[:200],
                }
                per_judgment.append(row)
                prompt_row = PerPromptRow(**row)

                if ja.passed and not jb.passed:
                    regressions.append(prompt_row)
                elif not ja.passed and jb.passed:
                    improvements.append(prompt_row)
                else:
                    unchanged += 1

            total = len(per_judgment)
            a_rate = round(a_pass / total, 4) if total else 0.0
            b_rate = round(b_pass / total, 4) if total else 0.0

            result = DiffRunResponse(
                run_id=uuid.uuid4().hex[:8],
                model_a=req.model_a,
                model_b=req.model_b,
                timestamp=datetime.now(UTC).isoformat(),
                total_tests=total,
                a_pass_rate=a_rate,
                b_pass_rate=b_rate,
                pass_rate_delta=round(b_rate - a_rate, 4),
                regression_count=len(regressions),
                improvement_count=len(improvements),
                unchanged=unchanged,
                categories=_category_diffs(per_judgment),
                regressions=regressions,
                improvements=improvements,
            )

            await queue.put(_sse({"type": "complete", "result": result.model_dump(mode="json")}))

        except Exception as exc:
            logger.exception("Fresh diff run failed")
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
