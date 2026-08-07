from fastapi import APIRouter, HTTPException

from ..models.api_models import EvalReport, RunListItem
from ..store import run_store

router = APIRouter()


@router.get("/runs", response_model=list[RunListItem])
async def list_runs() -> list[RunListItem]:
    """Return past runs, newest first."""
    return [RunListItem(**r) for r in run_store.all_runs()]


@router.get("/runs/{run_id}", response_model=EvalReport)
async def get_run(run_id: str) -> EvalReport:
    """Return a single run by ID."""
    data = run_store.get(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found.")
    return EvalReport(**data)
