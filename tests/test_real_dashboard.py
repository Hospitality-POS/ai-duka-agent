from ai_lining.dashboard import RealDashboardDataSource


class _StubParentBackend:
    def get_catalog(self, user_id: str) -> list[dict]:
        return [{"_id": "prod1", "name": "Morning Coffee"}]

    def list_orders(self, user_id: str, start_date: str, end_date: str) -> list[dict]:
        return [
            {
                "created_at": "2026-01-15T07:00:00",
                "line_items": [{"product_id": "prod1", "quantity": 2, "unit_price": 500}],
            }
        ]

    def get_stock_levels(self, user_id: str) -> list[dict]:
        return [{"inventory": [{"product_id": "prod1", "quantity": 2}], "deliveries": [], "orders": []}]


class _StubModelClient:
    def complete(self, prompt: str) -> str:
        return "Insight one\nInsight two\nInsight three"


def test_real_dashboard_data_source_computes_watched_product_and_alert() -> None:
    source = RealDashboardDataSource(
        _StubParentBackend(), _StubModelClient(), velocity_window_days=1, stock_threshold_days=2.0
    )

    watched_product = source.get_watched_product("shop1")
    alert = source.get_alert("shop1")

    assert watched_product.subtitle == "Morning Coffee Sales"
    assert alert is not None
    assert alert.id == "low_stock_prod1"


def test_real_dashboard_data_source_generates_insights() -> None:
    source = RealDashboardDataSource(_StubParentBackend(), _StubModelClient())
    insights = source.get_insights("shop1")
    assert [i.text for i in insights] == ["Insight one", "Insight two", "Insight three"]


def test_real_dashboard_data_source_falls_back_to_mock_header() -> None:
    source = RealDashboardDataSource(_StubParentBackend(), _StubModelClient())
    header = source.get_header("shop1")
    assert header.shop_name == "Silikhe's Shop"
