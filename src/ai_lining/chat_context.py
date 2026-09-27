"""Turns a shop's dashboard and inventory into context the chat agents answer from."""

from __future__ import annotations

import json
import logging

import httpx

from ai_lining.dashboard import DashboardDataSource, build_dashboard
from setup.parent_backend import BasePointParentBackendClient

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


# Keeps the prompt bounded for large catalogs; lowest-stock items are listed first, so the
# ones a shop owner most needs to act on survive the cut.
INVENTORY_ITEM_LIMIT = 150

INVENTORY_CONTEXT_INSTRUCTION = (
    "Below is this shop's current inventory from its POS (lowest stock first; prices in "
    "Ksh; cost is the supplier price per unit). Use it for questions about stock levels, "
    "what to reorder, what's out of stock, margins and stock value. Quote the real item "
    "names and quantities."
)


def _number(value: object) -> float | None:
    """Return `value` as a float, or None if it's missing or not numeric."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _ksh(amount: float) -> str:
    return f"Ksh {amount:,.0f}"


def build_inventory_context(
    user_id: str, parent_backend: BasePointParentBackendClient
) -> str | None:
    """Return the shop's inventory as a prompt section, or None if it can't be loaded."""
    try:
        items = parent_backend.get_inventory(user_id)
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning("Inventory unavailable for %r; chatting without it: %s", user_id, exc)
        return None
    if not items:
        return f"{INVENTORY_CONTEXT_INSTRUCTION}\n\nThe shop has no inventory items recorded."

    items = sorted(items, key=lambda item: _number(item.get("quantity")) or 0.0)
    total_value = 0.0
    out_of_stock = 0
    lines = []
    for item in items:
        quantity = _number(item.get("quantity")) or 0.0
        price = _number(item.get("price"))
        cost = _number(item.get("supplier_price"))
        if quantity <= 0:
            out_of_stock += 1
        if cost is not None:
            total_value += quantity * cost
        if len(lines) < INVENTORY_ITEM_LIMIT:
            parts = [f"{item.get('name') or item.get('_id')}: {quantity:g} in stock"]
            if price is not None:
                parts.append(f"sells {_ksh(price)}")
            if cost is not None:
                parts.append(f"costs {_ksh(cost)}")
            lines.append("- " + " | ".join(parts))

    summary = (
        f"{len(items)} items, {out_of_stock} out of stock, total stock value at cost "
        f"{_ksh(total_value)}."
    )
    if len(items) > INVENTORY_ITEM_LIMIT:
        summary += f" Listing the {INVENTORY_ITEM_LIMIT} lowest-stock items."
    return f"{INVENTORY_CONTEXT_INSTRUCTION}\n\n{summary}\n" + "\n".join(lines)


def build_chat_context(
    user_id: str,
    data_source: DashboardDataSource,
    parent_backend: BasePointParentBackendClient | None,
) -> str | None:
    """Combine the shop's dashboard and (with a backend client) inventory into chat context."""
    sections = [build_dashboard_context(user_id, data_source)]
    if parent_backend is not None:
        sections.append(build_inventory_context(user_id, parent_backend))
    return "\n\n".join(section for section in sections if section) or None
