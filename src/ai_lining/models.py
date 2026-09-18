"""Response models for the AI Lining dashboard, field names mirroring the Flutter widget props."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Header(BaseModel):
    """The shop identity and AI-health strip at the top of the dashboard."""

    model_config = ConfigDict(populate_by_name=True)

    shop_name: str = Field(alias="shopName")
    role: str
    ai_health: str = Field(alias="aiHealth")


class DailyObservation(BaseModel):
    """The hourly-sales chart card, including its peak window and quick prompts."""

    model_config = ConfigDict(populate_by_name=True)

    hourly_sales: list[float] = Field(alias="hourlySales")
    peak_index: int = Field(alias="peakIndex")
    peak_sales: str = Field(alias="peakSales")
    peak_window: str = Field(alias="peakWindow")
    performance_percent: str = Field(alias="performancePercent")
    performance_note: str = Field(alias="performanceNote")
    quick_prompts: list[str] = Field(alias="quickPrompts")


class WatchedProduct(BaseModel):
    """The single tracked product's sales trend and restock recommendation."""

    model_config = ConfigDict(populate_by_name=True)

    amount: str
    subtitle: str
    sales_label: str = Field(alias="salesLabel")
    sales_value: str = Field(alias="salesValue")
    trend: list[float]
    marker_index: int = Field(alias="markerIndex")
    recommendation: str
    quick_prompts: list[str] = Field(alias="quickPrompts")


class Alert(BaseModel):
    """A single actionable alert surfaced above the fold."""

    id: str
    title: str
    message: str
    action_label: str = Field(alias="actionLabel")

    model_config = ConfigDict(populate_by_name=True)


class WhatsHappening(BaseModel):
    """The plain-language explanation card pairing an observation with its stock impact."""

    model_config = ConfigDict(populate_by_name=True)

    observation: str
    implication: str
    stock_label: str = Field(alias="stockLabel")
    stock_value: str = Field(alias="stockValue")
    stock_status: str = Field(alias="stockStatus")


class Insight(BaseModel):
    """A single AI-generated insight, identified so `onApplyInsight()` can reference it."""

    id: str
    text: str


class SalesPerformance(BaseModel):
    """The monthly-sales chart card, including its highlighted month and quick prompts."""

    model_config = ConfigDict(populate_by_name=True)

    monthly_sales: list[float] = Field(alias="monthlySales")
    month_labels: list[str] = Field(alias="monthLabels")
    highlight_index: int = Field(alias="highlightIndex")
    annotation: str
    stock_percent: str = Field(alias="stockPercent")
    stock_note: str = Field(alias="stockNote")
    quick_prompts: list[str] = Field(alias="quickPrompts")


class MyStock(BaseModel):
    """The total-capital-at-risk summary card."""

    model_config = ConfigDict(populate_by_name=True)

    capital_label: str = Field(alias="capitalLabel")
    capital_value: str = Field(alias="capitalValue")
    note: str
    quick_prompts: list[str] = Field(alias="quickPrompts")


class ChatCard(BaseModel):
    """The entry point into the real-time chat feature."""

    title: str
    subtitle: str


class AiLiningDashboard(BaseModel):
    """The full AI Lining dashboard, one key per widget section."""

    model_config = ConfigDict(populate_by_name=True)

    header: Header
    daily_observation: DailyObservation = Field(alias="dailyObservation")
    watched_product: WatchedProduct = Field(alias="watchedProduct")
    alert: Alert | None = None
    whats_happening: WhatsHappening = Field(alias="whatsHappening")
    insights: list[Insight]
    sales_performance: SalesPerformance = Field(alias="salesPerformance")
    my_stock: MyStock = Field(alias="myStock")
    chat: ChatCard


class ApplyInsightRequest(BaseModel):
    """Marks an insight as applied so the dashboard can reflect the user's choice."""

    insight_id: str


class AlertActionRequest(BaseModel):
    """Records that the user opened an alert's suggested action."""

    alert_id: str
