"""Estimated cost per LLM call, from a small hardcoded price table."""

from __future__ import annotations

from coding_agent.models import Usage

# USD per 1M tokens: (input, output). Prices as of mid-2026; keep approximate —
# the estimate is for observability dashboards, not billing.
_PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "text-embedding-3-small": (0.02, 0.0),
}


def estimate_cost_usd(model: str, usage: Usage | None) -> float | None:
    """Best-effort cost estimate; None when usage or the model price is unknown."""
    if usage is None:
        return None
    prices = _PRICES_PER_MILLION.get(model)
    if prices is None:
        return None
    input_price, output_price = prices
    return (usage.prompt_tokens * input_price + usage.completion_tokens * output_price) / 1_000_000
