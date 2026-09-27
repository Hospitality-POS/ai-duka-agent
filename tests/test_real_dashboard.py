import json
from pathlib import Path

import httpx
import pytest

from ai_lining.chat_context import build_dashboard_context
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


def test_real_dashboard_data_source_accepts_nullable_sections() -> None:
    payload = {
        **SAMPLE_DASHBOARD,
        "alert": None,
        "watchedProduct": None,
        "dailyObservation": {**SAMPLE_DASHBOARD["dailyObservation"], "performancePercent": None},
        "salesPerformance": {**SAMPLE_DASHBOARD["salesPerformance"], "stockPercent": None},
    }
    source = RealDashboardDataSource(_StubParentBackend(payload))

    assert source.get_alert("shop1") is None
    assert source.get_watched_product("shop1") is None
    assert source.get_daily_observation("shop1").performance_percent is None
    assert source.get_sales_performance("shop1").stock_percent is None
    assert build_dashboard_context("shop1", source) is not None


class _DownParentBackend:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def get_dashboard(self, user_id: str) -> dict:
        raise self.exc


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://backend/biashara-ai/dashboard")
    return httpx.HTTPStatusError(
        "backend error", request=request, response=httpx.Response(status, request=request)
    )


@pytest.mark.parametrize(
    "exc", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), _status_error(503)]
)
def test_real_dashboard_data_source_falls_back_to_demo_data_when_backend_is_down(
    exc: Exception,
) -> None:
    dashboard = build_dashboard("shop1", RealDashboardDataSource(_DownParentBackend(exc)))
    assert dashboard.model_dump(by_alias=True) == SAMPLE_DASHBOARD


def test_real_dashboard_data_source_raises_backend_client_errors() -> None:
    source = RealDashboardDataSource(_DownParentBackend(_status_error(401)))
    with pytest.raises(httpx.HTTPStatusError):
        source.get_header("shop1")
