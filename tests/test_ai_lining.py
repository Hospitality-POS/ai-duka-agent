from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_dashboard_matches_widget_contract() -> None:
    response = client.get("/ai-lining/u1/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["header"]["shopName"] == "Silikhe's Shop"
    assert len(body["dailyObservation"]["hourlySales"]) == 12
    assert len(body["salesPerformance"]["monthLabels"]) == 12
    assert body["alert"]["id"] == "low_stock_morning_coffee"


def test_individual_section_routes_return_the_same_data_as_the_dashboard() -> None:
    dashboard = client.get("/ai-lining/u1/dashboard").json()
    header = client.get("/ai-lining/u1/header").json()
    assert header == dashboard["header"]

    insights = client.get("/ai-lining/u1/insights").json()
    assert insights == dashboard["insights"]


def test_apply_insight_rejects_unknown_id() -> None:
    response = client.post("/ai-lining/u1/insights/apply", json={"insight_id": "nope"})
    assert response.status_code == 404


def test_apply_insight_accepts_known_id() -> None:
    response = client.post("/ai-lining/u1/insights/apply", json={"insight_id": "insight_1"})
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_alert_action_rejects_unknown_id() -> None:
    response = client.post("/ai-lining/u1/alerts/action", json={"alert_id": "nope"})
    assert response.status_code == 404


def test_alert_action_accepts_known_id() -> None:
    response = client.post(
        "/ai-lining/u1/alerts/action", json={"alert_id": "low_stock_morning_coffee"}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
