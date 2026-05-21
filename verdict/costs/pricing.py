"""Model pricing table for Verdict cost computation.

Pricing table last updated: 2026-05-19.

IMPORTANT: Verify against official provider documentation before relying on
absolute cost figures:
  - Anthropic: https://www.anthropic.com/pricing
  - OpenAI:    https://openai.com/api/pricing

All values are USD per 1 million tokens.
"""

from __future__ import annotations

# Shape: {model_name: {input_per_1m_usd: float, output_per_1m_usd: float}}
# Source: official provider pricing pages (verify before use)
PRICING_TABLE: dict[str, dict[str, float]] = {
    # ------------------------------------------------------------------ #
    # Anthropic Claude models                                             #
    # ------------------------------------------------------------------ #
    # Source: https://www.anthropic.com/pricing
    "claude-opus-4-6": {
        "input_per_1m_usd": 15.00,
        "output_per_1m_usd": 75.00,
    },
    "claude-sonnet-4-6": {
        "input_per_1m_usd": 3.00,
        "output_per_1m_usd": 15.00,
    },
    "claude-haiku-4-5-20251001": {
        "input_per_1m_usd": 0.80,
        "output_per_1m_usd": 4.00,
    },
    # Common aliases / older model strings
    "claude-3-5-sonnet-20241022": {
        "input_per_1m_usd": 3.00,
        "output_per_1m_usd": 15.00,
    },
    "claude-3-5-haiku-20241022": {
        "input_per_1m_usd": 0.80,
        "output_per_1m_usd": 4.00,
    },
    "claude-3-opus-20240229": {
        "input_per_1m_usd": 15.00,
        "output_per_1m_usd": 75.00,
    },
    # ------------------------------------------------------------------ #
    # OpenAI models                                                        #
    # ------------------------------------------------------------------ #
    # Source: https://openai.com/api/pricing
    "gpt-4o": {
        "input_per_1m_usd": 2.50,
        "output_per_1m_usd": 10.00,
    },
    "gpt-4o-mini": {
        "input_per_1m_usd": 0.15,
        "output_per_1m_usd": 0.60,
    },
    "gpt-4-turbo": {
        "input_per_1m_usd": 10.00,
        "output_per_1m_usd": 30.00,
    },
    "gpt-4-turbo-preview": {
        "input_per_1m_usd": 10.00,
        "output_per_1m_usd": 30.00,
    },
    "gpt-3.5-turbo": {
        "input_per_1m_usd": 0.50,
        "output_per_1m_usd": 1.50,
    },
}


def get_model_pricing(model: str) -> dict[str, float] | None:
    """Return the pricing entry for a model, or None if not in the table.

    Performs an exact match first, then a prefix match for versioned aliases
    (e.g., 'claude-sonnet-4-6-20251201' -> 'claude-sonnet-4-6').

    Args:
        model: Model identifier string.

    Returns:
        dict with 'input_per_1m_usd' and 'output_per_1m_usd', or None.
    """
    if model in PRICING_TABLE:
        return PRICING_TABLE[model]
    # Prefix match for date-stamped variants
    for key in PRICING_TABLE:
        if model.startswith(key):
            return PRICING_TABLE[key]
    return None
