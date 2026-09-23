"""Turns raw Parent Backend Engine data (orders, catalog, stock) into dashboard metrics.

Money and quantity field names are inferred from the endpoint mapping notes ("money in
minor units", "order_items -> line items") since no real payload has been seen yet -
verify `_line_item_quantity`/`_line_item_revenue_minor` against a live response before
trusting the numbers this produces.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from ai_lining.models import Alert, DailyObservation, WatchedProduct

QUICK_PROMPTS = [
    "Why did sales peak at this time?",
    "Compare this to last week",
    "Explain this trend in plain terms",
]


def _line_item_quantity(line_item: dict) -> float:
    """Return a line item's quantity, defaulting to 0 if the field is missing."""
    return line_item.get("quantity", 0)


def _line_item_revenue_minor(line_item: dict) -> float:
    """Return a line item's revenue in minor currency units (cents)."""
    unit_price_minor = line_item.get("unit_price", line_item.get("price", 0))
    return _line_item_quantity(line_item) * unit_price_minor


def _order_hour(order: dict) -> int:
    """Return the hour (0-23) an order was placed, from its `created_at` timestamp."""
    return datetime.fromisoformat(order["created_at"]).hour


def format_kes(minor_units: float) -> str:
    """Format an amount in minor currency units (cents) as a KES display string."""
    return f"Ksh {minor_units / 100:,.0f}"


def compute_daily_observation(
    orders_today: list[dict], orders_previous_day: list[dict]
) -> DailyObservation:
    """Bucket today's orders into 12 two-hour windows and compare the total to yesterday."""
    buckets = [0.0] * 12
    for order in orders_today:
        for line_item in order.get("line_items", []):
            bucket = _order_hour(order) // 2
            buckets[bucket] += _line_item_revenue_minor(line_item)

    peak_index = max(range(12), key=lambda i: buckets[i])
    start_hour, end_hour = peak_index * 2, peak_index * 2 + 2

    today_total = sum(buckets)
    previous_total = sum(
        _line_item_revenue_minor(item)
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

    for order in recent_orders:
        order_day = order.get("created_at", "")[:10]
        for item in order.get("line_items", []):
            product_id = item.get("product_id")
            quantity_by_product[product_id] += _line_item_quantity(item)
            revenue_by_product[product_id] += _line_item_revenue_minor(item)
            daily_quantity[product_id][order_day] += _line_item_quantity(item)

    if not quantity_by_product:
        raise ValueError("No orders in the velocity window to determine a watched product.")

    product_id = max(quantity_by_product, key=quantity_by_product.get)
    product_name = product_names.get(product_id, "Top Product")
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
