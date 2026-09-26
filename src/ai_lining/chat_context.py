"""Turns a shop's AI Lining dashboard into context the chat agents answer from."""

from __future__ import annotations

import json
import logging

from ai_lining.dashboard import DashboardDataSource, build_dashboard

logger = logging.getLogger(__name__)

# UI-only fields: the chat card and the canned quick-prompt buttons tell the model nothing.
_UI_ONLY_FIELDS = {
    "chat": True,
    "daily_observation": {"quick_prompts"},
    "watched_product": {"quick_prompts"},
    "sales_performance": {"quick_prompts"},
    "my_stock": {"quick_prompts"},
}

DASHBOARD_CONTEXT_INSTRUCTION = (
    "Below is this shop's live dashboard data (JSON). Ground every answer in it: quote its "
    "real figures, product names and stock levels, and base recommendations on them. Never "
    "invent numbers that aren't in it; if the data doesn't cover the question, say so and "
    "give general advice instead. In `hourlySales` and `trend`, the `peakIndex` / "
    "`markerIndex` entry is the one highlighted on the chart."
)


def build_dashboard_context(user_id: str, data_source: DashboardDataSource) -> str | None:
    """Return `user_id`'s dashboard data as a prompt section, or None if it can't be loaded."""
    try:
        dashboard = build_dashboard(user_id, data_source)
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.warning("Dashboard data unavailable for %r; chatting without it: %s", user_id, exc)
        return None
    data = dashboard.model_dump(by_alias=True, exclude=_UI_ONLY_FIELDS)
    return f"{DASHBOARD_CONTEXT_INSTRUCTION}\n\n{json.dumps(data, indent=2)}"
