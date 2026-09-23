"""Assembles the AI Lining dashboard for a user, one function per widget section.

`MockDashboardDataSource` returns static example data. `RealDashboardDataSource` computes
`dailyObservation`, `watchedProduct`, `alert`, and `insights` from the real Parent Backend
Engine (see `setup/parent_backend.py`) - `header`, `whatsHappening`, `salesPerformance`, and
`myStock` still have no real data source (no shop-listing endpoint, no historical stock
snapshots, no confirmed product cost field) and fall back to the mock values.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from ai_lining.analytics import compute_daily_observation, compute_watched_product
from ai_lining.insight_generation import generate_insights
from ai_lining.models import (
    AiLiningDashboard,
    Alert,
    ChatCard,
    DailyObservation,
    Header,
    Insight,
    MyStock,
    SalesPerformance,
    WatchedProduct,
    WhatsHappening,
)
from setup.business_identity import ChatModelClient
from setup.parent_backend import BasePointParentBackendClient


class DashboardDataSource(Protocol):
    """Read access to the Parent Backend Engine's AI Lining dashboard data."""

    def get_header(self, user_id: str) -> Header: ...
    def get_daily_observation(self, user_id: str) -> DailyObservation: ...
    def get_watched_product(self, user_id: str) -> WatchedProduct: ...
    def get_alert(self, user_id: str) -> Alert | None: ...
    def get_whats_happening(self, user_id: str) -> WhatsHappening: ...
    def get_insights(self, user_id: str) -> list[Insight]: ...
    def get_sales_performance(self, user_id: str) -> SalesPerformance: ...
    def get_my_stock(self, user_id: str) -> MyStock: ...
    def get_chat_card(self, user_id: str) -> ChatCard: ...
    def apply_insight(self, user_id: str, insight_id: str) -> bool: ...
    def record_alert_action(self, user_id: str, alert_id: str) -> bool: ...


class MockDashboardDataSource:
    """A `DashboardDataSource` backed by static example data before the real integration exists."""

    def get_header(self, user_id: str) -> Header:
        """Return a placeholder header for `user_id`."""
        return Header(shop_name="Silikhe's Shop", role="Store Manager", ai_health="87%")

    def get_daily_observation(self, user_id: str) -> DailyObservation:
        """Return a placeholder hourly-sales observation for `user_id`."""
        return DailyObservation(
            hourly_sales=[4200, 3800, 5200, 4600, 6100, 5400, 9000, 5800, 4900, 6300, 5100, 4400],
            peak_index=6,
            peak_sales="2000 Sales",
            peak_window="From 6:30 - 9:30AM",
            performance_percent="30%",
            performance_note="Your sales performance is 30% better compare to last month",
            quick_prompts=[
                "Why did sales peak at this time?",
                "Compare this to last week",
                "Explain this trend in plain terms",
            ],
        )

    def get_watched_product(self, user_id: str) -> WatchedProduct:
        """Return a placeholder watched-product card for `user_id`."""
        return WatchedProduct(
            amount="Ksh 1250",
            subtitle="Morning Coffee Sales",
            sales_label="Sales",
            sales_value="Ksh 23,000",
            trend=[2.0, 2.6, 2.3, 3.2, 3.0, 3.8, 4.4, 4.1, 5.0],
            marker_index=6,
            recommendation="You're Likely To Run Out Tomorrow Around 10:00 AM.",
            quick_prompts=[
                "Why did sales peak at this time?",
                "Compare this to last week",
                "Explain this trend in plain terms",
            ],
        )

    def get_alert(self, user_id: str) -> Alert | None:
        """Return the active low-stock alert for `user_id`, or None if there isn't one."""
        return Alert(
            id="low_stock_morning_coffee",
            title="Morning Coffee",
            message="You may run out of Morning Coffee before your busiest sales period.",
            action_label="See what to do",
        )

    def get_whats_happening(self, user_id: str) -> WhatsHappening:
        """Return a placeholder explanation card for `user_id`."""
        return WhatsHappening(
            observation="More Customers Are Buying Coffee During The Morning Rush.",
            implication=(
                "This Is Increasing Your Daily Revenue, But Your Current Stock May Not Last "
                "Through Tomorrow."
            ),
            stock_label="Stock remaining",
            stock_value="78 units",
            stock_status="Low Stock",
        )

    def get_insights(self, user_id: str) -> list[Insight]:
        """Return placeholder insights for `user_id`."""
        return [
            Insight(
                id="insight_1",
                text=(
                    "Your Morning Coffee sales are performing exceptionally today. Pair them "
                    "with pastries to maximize your average ticket."
                ),
            ),
            Insight(
                id="insight_2",
                text=(
                    "Restocking Morning Coffee before 9:00 AM keeps your busiest window "
                    "covered and protects tomorrow's revenue."
                ),
            ),
            Insight(
                id="insight_3",
                text=(
                    "Counter sales outpace online 3:1 before noon. Move your promo staff to "
                    "the counter during the morning rush."
                ),
            ),
        ]

    def get_sales_performance(self, user_id: str) -> SalesPerformance:
        """Return a placeholder monthly-sales performance card for `user_id`."""
        return SalesPerformance(
            monthly_sales=[3.2, 4.6, 3.4, 5.2, 4.0, 3.0, 4.2, 5.4, 4.8, 3.6, 4.4, 5.0],
            month_labels=[
                "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
            ],
            highlight_index=7,
            annotation="4600 Live sales in May",
            stock_percent="30%",
            stock_note=(
                "You have 30% more stock available than last month, helping you stay ahead "
                "of demand."
            ),
            quick_prompts=[
                "Why did sales peak at this time?",
                "Compare this to last week",
                "Explain this trend in plain terms",
            ],
        )

    def get_my_stock(self, user_id: str) -> MyStock:
        """Return a placeholder stock-capital card for `user_id`."""
        return MyStock(
            capital_label="Total Capital",
            capital_value="Ksh 274,000",
            note="Orders Coming From Suppliers Which Exceeds The Capital By 2%",
            quick_prompts=[
                "Break down this total for me",
                "Compare this to last month",
                "What's driving this number?",
            ],
        )

    def get_chat_card(self, user_id: str) -> ChatCard:
        """Return the chat entry-point card."""
        return ChatCard(title="Start a Chat", subtitle="Real-time chatting with business analytics")

    def apply_insight(self, user_id: str, insight_id: str) -> bool:
        """Record that `user_id` applied `insight_id`; the mock always succeeds."""
        return True

    def record_alert_action(self, user_id: str, alert_id: str) -> bool:
        """Record that `user_id` opened `alert_id`'s suggested action; the mock always succeeds."""
        return True


class RealDashboardDataSource(MockDashboardDataSource):
    """A `DashboardDataSource` computing what it can from the real Parent Backend Engine.

    `user_id` is treated as the shop_id `BasePointParentBackendClient.list_orders` expects.
    Sections with no real data source yet (`header`, `whatsHappening`, `salesPerformance`,
    `myStock`) fall back to `MockDashboardDataSource`.
    """

    def __init__(
        self,
        parent_backend: BasePointParentBackendClient,
        model_client: ChatModelClient,
        velocity_window_days: int = 7,
        stock_threshold_days: float = 2.0,
    ) -> None:
        self._parent_backend = parent_backend
        self._model_client = model_client
        self._velocity_window_days = velocity_window_days
        self._stock_threshold_days = stock_threshold_days

    def _recent_orders(self, user_id: str, days: int) -> list[dict]:
        """Fetch `user_id`'s orders from `days` ago through today, in East Africa Time."""
        today = datetime.now(ZoneInfo("Africa/Nairobi")).date()
        start = (today - timedelta(days=days)).isoformat()
        return self._parent_backend.list_orders(user_id, start, today.isoformat())

    def _watched_product_and_alert(self, user_id: str) -> tuple[WatchedProduct, Alert | None]:
        recent_orders = self._recent_orders(user_id, self._velocity_window_days)
        catalog = self._parent_backend.get_catalog(user_id)
        product_names = {product["_id"]: product.get("name", "") for product in catalog}

        stock_levels = self._parent_backend.get_stock_levels(user_id)
        stock_by_product = {
            item["_id"]: item.get("quantity", 0) for item in stock_levels[0]["inventory"]
        }

        return compute_watched_product(
            recent_orders,
            stock_by_product,
            product_names,
            self._velocity_window_days,
            self._stock_threshold_days,
        )

    def get_daily_observation(self, user_id: str) -> DailyObservation:
        """Compute today's hourly sales, compared against yesterday, from real orders."""
        orders_today = self._recent_orders(user_id, 0)
        orders_yesterday_through_today = self._recent_orders(user_id, 1)
        orders_yesterday = [
            order for order in orders_yesterday_through_today if order not in orders_today
        ]
        return compute_daily_observation(orders_today, orders_yesterday)

    def get_watched_product(self, user_id: str) -> WatchedProduct:
        """Return the highest-velocity product from real orders and stock."""
        watched_product, _alert = self._watched_product_and_alert(user_id)
        return watched_product

    def get_alert(self, user_id: str) -> Alert | None:
        """Return a low-stock alert if the watched product is within the days-of-stock threshold."""
        _watched_product, alert = self._watched_product_and_alert(user_id)
        return alert

    def get_insights(self, user_id: str) -> list[Insight]:
        """Generate insights from the real watched product and daily observation."""
        watched_product = self.get_watched_product(user_id)
        daily_observation = self.get_daily_observation(user_id)
        return generate_insights(self._model_client, watched_product, daily_observation)


def build_dashboard(user_id: str, data_source: DashboardDataSource) -> AiLiningDashboard:
    """Assemble the full AI Lining dashboard for `user_id` from `data_source`."""
    return AiLiningDashboard(
        header=data_source.get_header(user_id),
        daily_observation=data_source.get_daily_observation(user_id),
        watched_product=data_source.get_watched_product(user_id),
        alert=data_source.get_alert(user_id),
        whats_happening=data_source.get_whats_happening(user_id),
        insights=data_source.get_insights(user_id),
        sales_performance=data_source.get_sales_performance(user_id),
        my_stock=data_source.get_my_stock(user_id),
        chat=data_source.get_chat_card(user_id),
    )


def apply_insight(
    user_id: str, insight_id: str, data_source: DashboardDataSource
) -> tuple[bool, str]:
    """Apply `insight_id` for `user_id` and report whether it succeeded."""
    insight_ids = {insight.id for insight in data_source.get_insights(user_id)}
    if insight_id not in insight_ids:
        return False, f"Insight {insight_id!r} was not found for this user."

    if data_source.apply_insight(user_id, insight_id):
        return True, "Insight applied."
    return False, "Failed to apply insight."


def record_alert_action(
    user_id: str, alert_id: str, data_source: DashboardDataSource
) -> tuple[bool, str]:
    """Record that `user_id` acted on `alert_id` and report whether it succeeded."""
    alert = data_source.get_alert(user_id)
    if alert is None or alert.id != alert_id:
        return False, f"Alert {alert_id!r} was not found for this user."

    if data_source.record_alert_action(user_id, alert_id):
        return True, "Alert action recorded."
    return False, "Failed to record alert action."
