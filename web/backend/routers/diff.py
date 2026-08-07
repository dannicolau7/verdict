"""POST /api/diff/compare — aggregate diff between two completed runs.

Takes two run IDs already in the in-memory store and returns a side-by-side
comparison of pass rates and per-category breakdowns.  No new LLM calls.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..store import run_store

router = APIRouter()


class DiffCompareRequest(BaseModel):
    run_id_a: str
    run_id_b: str


class CategoryDiff(BaseModel):
    category: str
    a_pass_rate: float | None
    b_pass_rate: float | None
    delta: float | None
    a_total: int
    b_total: int


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
    """Return an aggregate diff between two historical runs."""
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
