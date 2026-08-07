from fastapi import APIRouter, HTTPException

from ..models.api_models import EvalReport, RunListItem
from .eval import _runs  # shared in-memory store

router = APIRouter()


@router.get("/runs", response_model=list[RunListItem])
async def list_runs() -> list[RunListItem]:
    """Return past runs, newest first."""
    items = []
    for run_id, data in reversed(list(_runs.items())):
        items.append(
            RunListItem(
                run_id=run_id,
                target_system=data["target_system"],
                timestamp=data["timestamp"],
                pass_rate=data["pass_rate"],
                total_tests=data["total_tests"],
            )
        )
    return items


@router.get("/runs/{run_id}", response_model=EvalReport)
async def get_run(run_id: str) -> EvalReport:
    """Return a single run by ID."""
    data = _runs.get(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found.")
    return EvalReport(**data)
