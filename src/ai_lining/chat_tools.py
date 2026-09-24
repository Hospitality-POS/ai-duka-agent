"""Gemini function-calling tools that let the chat agent read a shop's real dashboard data.

Each tool wraps one `DashboardDataSource` method (see `dashboard.py`) bound to a specific
`user_id`. Gemini decides on its own, from each function's docstring, when a user's question
needs one of these called - see `GeminiChatClient` in `setup/model_provider.py`.
"""

from __future__ import annotations

from collections.abc import Callable

from ai_lining.dashboard import DashboardDataSource


def build_dashboard_tools(user_id: str, data_source: DashboardDataSource) -> list[Callable]:
    """Return Gemini tool functions giving the chat agent read access to `user_id`'s dashboard."""

    def get_todays_sales() -> dict:
        """Return the shop's hourly sales so far today, its peak sales window, and how that compares to last month."""
        return data_source.get_daily_observation(user_id).model_dump(by_alias=True)

    def get_watched_product() -> dict:
        """Return the shop's highest-velocity product: its recent sales trend and restock recommendation."""
        return data_source.get_watched_product(user_id).model_dump(by_alias=True)

    def get_active_stock_alert() -> dict | None:
        """Return the shop's current low-stock alert, or null if nothing is low on stock right now."""
        alert = data_source.get_alert(user_id)
        return alert.model_dump(by_alias=True) if alert else None

    def get_sales_performance() -> dict:
        """Return the shop's monthly sales performance for the past year."""
        return data_source.get_sales_performance(user_id).model_dump(by_alias=True)

    def get_stock_capital() -> dict:
        """Return the shop's total stock capital value and how it compares to last month."""
        return data_source.get_my_stock(user_id).model_dump(by_alias=True)

    def get_ai_insights() -> list[dict]:
        """Return the shop's current AI-generated insights and recommendations."""
        return [insight.model_dump(by_alias=True) for insight in data_source.get_insights(user_id)]

    return [
        get_todays_sales,
        get_watched_product,
        get_active_stock_alert,
        get_sales_performance,
        get_stock_capital,
        get_ai_insights,
    ]
