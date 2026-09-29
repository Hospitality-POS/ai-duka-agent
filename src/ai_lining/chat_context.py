"""Turns a shop's dashboard and inventory into context the chat agents answer from."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta

import httpx

from ai_lining.dashboard import DashboardDataSource, build_dashboard
from setup.parent_backend import BasePointParentBackendClient

logger = logging.getLogger(__name__)

DATE_RANGE_QUESTION = (
    "What date range should I use? Please give me dates like "
    "`from 2026-09-01 to 2026-09-26`, or say `this week` or `last month`."
)

_DATE_SENSITIVE_TERMS = (
    "sales",
    "sold",
    "sell",
    "selling",
    "revenue",
    "orders",
    "performance",
    "trend",
    "compare",
    "growth",
    "historical",
)
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def date_range_from_prompt(prompt: str, today: date | None = None) -> tuple[str, str] | None:
    """Extract an explicit or common relative date range from a user prompt."""
    current = today or date.today()
    dates = []
    for value in _ISO_DATE.findall(prompt):
        try:
            dates.append(date.fromisoformat(value))
        except ValueError:
            continue
    if len(dates) >= 2:
        start, end = dates[:2]
        return (start.isoformat(), end.isoformat()) if start <= end else None

    normalized = prompt.lower()
    if "yesterday" in normalized:
        value = current - timedelta(days=1)
        return value.isoformat(), value.isoformat()
    if "today" in normalized:
        value = current
        return value.isoformat(), value.isoformat()
    if "last week" in normalized:
        start = current - timedelta(days=current.weekday() + 7)
        return start.isoformat(), (start + timedelta(days=6)).isoformat()
    if "this week" in normalized:
        start = current - timedelta(days=current.weekday())
        return start.isoformat(), current.isoformat()
    if "last month" in normalized:
        first_of_current_month = current.replace(day=1)
        end = first_of_current_month - timedelta(days=1)
        start = end.replace(day=1)
        return start.isoformat(), end.isoformat()
    if "this month" in normalized:
        return current.replace(day=1).isoformat(), current.isoformat()
    return None


def prompt_needs_date_range(prompt: str) -> bool:
    """Return whether a prompt asks for time-dependent business data."""
    normalized = prompt.lower()
    return any(term in normalized for term in _DATE_SENSITIVE_TERMS)

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


def build_dashboard_context(
    user_id: str,
    data_source: DashboardDataSource,
    from_date: str | None = None,
    to_date: str | None = None,
) -> str | None:
    """Return `user_id`'s dashboard data as a prompt section, or None if it can't be loaded."""
    try:
        dashboard = build_dashboard(user_id, data_source, from_date, to_date)
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.warning("Dashboard data unavailable for %r; chatting without it: %s", user_id, exc)
        return None
    data = dashboard.model_dump(by_alias=True, exclude=_UI_ONLY_FIELDS)
    date_note = (
        f"The dashboard covers {from_date} through {to_date}."
        if from_date and to_date
        else "The dashboard uses the backend's default current range."
    )
    return f"{DASHBOARD_CONTEXT_INSTRUCTION} {date_note}\n\n{json.dumps(data, indent=2)}"


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
    from_date: str | None = None,
    to_date: str | None = None,
) -> str | None:
    """Combine the shop's dashboard and (with a backend client) inventory into chat context."""
    sections = [build_dashboard_context(user_id, data_source, from_date, to_date)]
    if parent_backend is not None:
        sections.append(build_inventory_context(user_id, parent_backend))
    return "\n\n".join(section for section in sections if section) or None
