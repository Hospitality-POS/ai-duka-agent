import json
from pathlib import Path

from ai_lining.dashboard import RealDashboardDataSource, build_dashboard

SAMPLE_DASHBOARD = json.loads(
    (Path(__file__).parent.parent / "docs" / "ai_lining_dashboard_sample.json").read_text(
        encoding="utf-8"
    )
)


class _StubParentBackend:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def get_dashboard(self, user_id: str) -> dict:
        self.calls += 1
        return self.payload


def test_real_dashboard_data_source_reads_every_section_from_one_call() -> None:
    backend = _StubParentBackend(SAMPLE_DASHBOARD)
    dashboard = build_dashboard("shop1", RealDashboardDataSource(backend))

    assert dashboard.model_dump(by_alias=True) == SAMPLE_DASHBOARD
    assert backend.calls == 1


def test_real_dashboard_data_source_accepts_null_stock_percent_and_alert() -> None:
    payload = {
        **SAMPLE_DASHBOARD,
        "alert": None,
        "salesPerformance": {**SAMPLE_DASHBOARD["salesPerformance"], "stockPercent": None},
    }
    source = RealDashboardDataSource(_StubParentBackend(payload))

    assert source.get_alert("shop1") is None
    assert source.get_sales_performance("shop1").stock_percent is None
