from fastapi import APIRouter

from ..models.api_models import ConfigResponse

router = APIRouter()

_CATEGORIES = ["correctness", "safety", "injection", "edge_case", "compliance"]
_ATTACK_FAMILIES = ["standard", "adaptive"]
_JUDGE_MODELS = [
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-6",
]
_DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"


@router.get("/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Return available categories, attack families, and judge models."""
    return ConfigResponse(
        categories=_CATEGORIES,
        attack_families=_ATTACK_FAMILIES,
        judge_models=_JUDGE_MODELS,
        default_judge_model=_DEFAULT_JUDGE_MODEL,
    )
