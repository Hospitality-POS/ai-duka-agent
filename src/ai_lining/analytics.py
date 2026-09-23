"""Turns raw Parent Backend Engine data (orders, catalog, stock) into dashboard metrics.

Field names verified against a real `GET /orders` and `GET /product-inventory` response
from the BasePoint API on 2026-09-23: `order.createdAt` (UTC, trailing "Z"), line items'
`price` field, and `order_items[].product_id` as a nested `{_id, name}` object rather than
a plain id string. Amounts are plain KES (not minor/cent units).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from ai_lining.models import Alert, DailyObservation, WatchedProduct

QUICK_PROMPTS = [
    "Why did sales peak at this time?",
    "Compare this to last week",
    "Explain this trend in plain terms",
]

_NAIROBI = ZoneInfo("Africa/Nairobi")


def _line_item_product_id(line_item: dict) -> str | None:
    """Return a line item's product id, whether `product_id` is a nested object or a plain id."""
    product_id = line_item.get("product_id")
    return product_id.get("_id") if isinstance(product_id, dict) else product_id


def _line_item_product_name(line_item: dict) -> str | None:
    """Return a line item's product name, if `product_id` was returned as a nested object."""
    product_id = line_item.get("product_id")
    return product_id.get("name") if isinstance(product_id, dict) else None


def _line_item_quantity(line_item: dict) -> float:
    """Return a line item's quantity, defaulting to 0 if the field is missing."""
    return line_item.get("quantity", 0)


def _line_item_revenue(line_item: dict) -> float:
    """Return a line item's revenue in KES (`price` is already a plain KES amount)."""
    return _line_item_quantity(line_item) * line_item.get("price", 0)


def _order_datetime(order: dict) -> datetime:
    """Parse an order's `createdAt` (UTC) and convert it to East Africa Time."""
    timestamp = order["createdAt"].replace("Z", "+00:00")
    return datetime.fromisoformat(timestamp).astimezone(_NAIROBI)


def format_kes(amount: float) -> str:
    """Format a KES amount as a display string."""
    return f"Ksh {amount:,.0f}"


def compute_daily_observation(
    orders_today: list[dict], orders_previous_day: list[dict]
) -> DailyObservation:
    """Bucket today's orders into 12 two-hour windows (East Africa Time) vs. yesterday's total."""
    buckets = [0.0] * 12
    for order in orders_today:
        bucket = _order_datetime(order).hour // 2
        for line_item in order.get("line_items", []):
            buckets[bucket] += _line_item_revenue(line_item)

    peak_index = max(range(12), key=lambda i: buckets[i])
    start_hour, end_hour = peak_index * 2, peak_index * 2 + 2

    today_total = sum(buckets)
    previous_total = sum(
        _line_item_revenue(item)
        for order in orders_previous_day
        for item in order.get("line_items", [])
    )
    percent = ((today_total - previous_total) / previous_total * 100) if previous_total else 0.0
    direction = "better" if percent >= 0 else "lower"

    return DailyObservation(
        hourly_sales=buckets,
        peak_index=peak_index,
        peak_sales=format_kes(buckets[peak_index]),
        peak_window=f"From {start_hour:02d}:00 - {end_hour:02d}:00",
        performance_percent=f"{abs(percent):.0f}%",
        performance_note=(
            f"Your sales performance is {abs(percent):.0f}% {direction} compare to yesterday"
        ),
        quick_prompts=QUICK_PROMPTS,
    )


def compute_watched_product(
    recent_orders: list[dict],
    stock_by_product: dict[str, float],
    product_names: dict[str, str],
    velocity_window_days: int,
    stock_threshold_days: float,
) -> tuple[WatchedProduct, Alert | None]:
    """Pick the highest-velocity product and flag it if it'll run out within the threshold."""
    quantity_by_product: dict[str, float] = defaultdict(float)
    revenue_by_product: dict[str, float] = defaultdict(float)
    daily_quantity: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    names_seen: dict[str, str] = {}

    for order in recent_orders:
        order_day = _order_datetime(order).date().isoformat()
        for item in order.get("line_items", []):
            product_id = _line_item_product_id(item)
            name = _line_item_product_name(item)
            if name:
                names_seen[product_id] = name
            quantity_by_product[product_id] += _line_item_quantity(item)
            revenue_by_product[product_id] += _line_item_revenue(item)
            daily_quantity[product_id][order_day] += _line_item_quantity(item)

    if not quantity_by_product:
        raise ValueError("No orders in the velocity window to determine a watched product.")

    product_id = max(quantity_by_product, key=quantity_by_product.get)
    product_name = names_seen.get(product_id) or product_names.get(product_id, "Top Product")
    total_quantity = quantity_by_product[product_id]
    velocity_per_day = total_quantity / velocity_window_days

    trend_days = sorted(daily_quantity[product_id])
    trend = [daily_quantity[product_id][day] for day in trend_days] or [0.0]
    marker_index = max(range(len(trend)), key=lambda i: trend[i])

    current_stock = stock_by_product.get(product_id, 0.0)
    days_of_stock = (current_stock / velocity_per_day) if velocity_per_day > 0 else float("inf")

    average_daily_revenue = revenue_by_product[product_id] / max(len(trend_days), 1)
    watched_product = WatchedProduct(
        amount=format_kes(average_daily_revenue),
        subtitle=f"{product_name} Sales",
        sales_label="Sales",
        sales_value=format_kes(revenue_by_product[product_id]),
        trend=trend,
        marker_index=marker_index,
        recommendation=(
            f"You're Likely To Run Out Of {product_name} In About {days_of_stock:.0f} Day(s)."
            if days_of_stock <= stock_threshold_days
            else f"{product_name} stock levels look healthy for now."
        ),
        quick_prompts=QUICK_PROMPTS,
    )

    alert = None
    if days_of_stock <= stock_threshold_days:
        alert = Alert(
            id=f"low_stock_{product_id}",
            title=product_name,
            message=f"You may run out of {product_name} within {days_of_stock:.0f} day(s).",
            action_label="See what to do",
        )

    return watched_product, alert
