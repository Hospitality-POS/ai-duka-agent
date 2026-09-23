"""Generates the dashboard's `insights` cards from real metrics via a chat model."""

from __future__ import annotations

from ai_lining.models import DailyObservation, Insight, WatchedProduct
from setup.business_identity import ChatModelClient

FALLBACK_INSIGHT = Insight(
    id="insight_unavailable",
    text="Insights are temporarily unavailable - check back shortly.",
)


def build_insight_prompt(
    watched_product: WatchedProduct, daily_observation: DailyObservation
) -> str:
    """Compose the prompt asking the model for three short, actionable retail insights."""
    return (
        "You are a retail business coach. Based on the numbers below, write exactly 3 short, "
        "actionable insights for a shop owner, one per line, with no numbering or bullets.\n\n"
        f"- Top-selling product: {watched_product.subtitle}, {watched_product.sales_value} "
        f"in sales, recommendation: {watched_product.recommendation}\n"
        f"- Today's sales peak: {daily_observation.peak_window} "
        f"({daily_observation.peak_sales})\n"
        f"- Performance vs yesterday: {daily_observation.performance_note}"
    )


def generate_insights(
    model_client: ChatModelClient,
    watched_product: WatchedProduct,
    daily_observation: DailyObservation,
) -> list[Insight]:
    """Ask the chat model for 3 insights from real metrics, falling back on any failure."""
    prompt = build_insight_prompt(watched_product, daily_observation)
    try:
        response = model_client.complete(prompt)
    except Exception:  # pragma: no cover - defensive branch
        return [FALLBACK_INSIGHT]

    lines = [line.strip("-* \t") for line in response.splitlines() if line.strip()]
    if not lines:
        return [FALLBACK_INSIGHT]

    return [Insight(id=f"insight_{i + 1}", text=line) for i, line in enumerate(lines[:3])]
