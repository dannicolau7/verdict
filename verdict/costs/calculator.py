"""Cost computation functions for Verdict.

Two main functions:
- compute_cost:       USD cost for a single LLM call (given token counts + model).
- compute_run_costs:  Full cost_breakdown dict for an EvalReport, splitting
                      harness (Verdict's own LLM calls) from target (the system
                      being evaluated).
"""

from __future__ import annotations

import logging

from verdict.costs.pricing import get_model_pricing
from verdict.models.schemas import ExecutionResult

logger = logging.getLogger(__name__)


def compute_cost(token_usage: dict[str, int], model: str) -> float | None:
    """Compute USD cost for a single LLM call.

    Args:
        token_usage: Dict with at least 'input_tokens' and 'output_tokens' keys.
        model:       Model identifier (e.g., 'claude-sonnet-4-6').

    Returns:
        Estimated cost in USD, or None if model is not in the pricing table.
    """
    pricing = get_model_pricing(model)
    if pricing is None:
        logger.debug("No pricing data for model %r — skipping cost computation.", model)
        return None

    input_tokens = token_usage.get("input_tokens", 0)
    output_tokens = token_usage.get("output_tokens", 0)

    cost = (
        input_tokens * pricing["input_per_1m_usd"] / 1_000_000
        + output_tokens * pricing["output_per_1m_usd"] / 1_000_000
    )
    return round(cost, 8)


def compute_run_costs(
    execution_results: list[ExecutionResult],
    harness_token_counts: dict[str, dict[str, int]],
    harness_models: dict[str, str] | None = None,
) -> dict:
    """Build the cost_breakdown dict for an EvalReport.

    Args:
        execution_results:   All ExecutionResult objects for this run.
        harness_token_counts: Token counts per harness agent, keyed by agent name.
                              E.g. {'generator': {'input_tokens': N, 'output_tokens': N},
                                    'judge': {...}, 'reporter': {...}}
        harness_models:      Model used per harness agent.  If None, costs are skipped
                             for agents without known models.

    Returns:
        cost_breakdown dict matching the EvalReport.cost_breakdown schema.
    """
    harness_models = harness_models or {}

    # ------------------------------------------------------------------ #
    # Target costs: sum over execution results                             #
    # ------------------------------------------------------------------ #
    target_input = 0
    target_output = 0
    target_cost = 0.0
    target_cost_known = True

    for result in execution_results:
        if result.token_usage:
            target_input += result.token_usage.get("input_tokens", 0)
            target_output += result.token_usage.get("output_tokens", 0)
        if result.estimated_cost_usd is not None:
            target_cost += result.estimated_cost_usd
        elif result.token_usage and result.model_used:
            c = compute_cost(result.token_usage, result.model_used)
            if c is not None:
                target_cost += c
            else:
                target_cost_known = False
        else:
            target_cost_known = False

    # ------------------------------------------------------------------ #
    # Harness costs: per-agent breakdown                                   #
    # ------------------------------------------------------------------ #
    harness_breakdown: dict[str, dict] = {}
    harness_total_cost = 0.0
    harness_cost_known = True

    for agent, tokens in harness_token_counts.items():
        model = harness_models.get(agent)
        inp = tokens.get("input_tokens", 0)
        out = tokens.get("output_tokens", 0)
        cost = compute_cost(tokens, model) if model else None
        if cost is None:
            harness_cost_known = False
        else:
            harness_total_cost += cost
        harness_breakdown[agent] = {
            "input_tokens": inp,
            "output_tokens": out,
            "estimated_cost_usd": cost if cost is not None else 0.0,
        }

    harness_entry: dict = {
        **harness_breakdown,
        "estimated_cost_usd": round(harness_total_cost, 6) if harness_cost_known else None,
    }

    target_entry: dict = {
        "input_tokens": target_input,
        "output_tokens": target_output,
        "estimated_cost_usd": round(target_cost, 6) if target_cost_known else None,
    }

    total: float | None = None
    if harness_cost_known and target_cost_known:
        total = round(harness_total_cost + target_cost, 6)
    elif target_cost_known:
        total = round(target_cost, 6)

    if not target_cost_known:
        logger.warning(
            "Some target executions are missing token_usage or model_used — "
            "target cost estimate is incomplete."
        )
    if not harness_cost_known:
        logger.warning(
            "Some harness agents have unknown model pricing — "
            "harness cost estimate is incomplete."
        )

    return {
        "harness": harness_entry,
        "target": target_entry,
        "total_cost_usd": total,
    }
