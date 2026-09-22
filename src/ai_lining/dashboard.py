"""Assembles the AI Lining dashboard for a user, one function per widget section.

`DashboardDataSource` is the Parent Backend Engine's dashboard API - it doesn't exist yet
(see `setup/business_identity.py` for the same pattern), so `MockDashboardDataSource` stands
in with static example data until that integration lands. Swap it out at the FastAPI
dependency in `main.py` once a real client exists; nothing here makes network calls.
"""

from __future__ import annotations

from typing import Protocol

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
