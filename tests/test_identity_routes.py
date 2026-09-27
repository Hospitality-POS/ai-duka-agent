import json

import pytest
from fastapi.testclient import TestClient

from main import app, get_identity_model_client, get_parent_backend

client = TestClient(app)

GOALS = [{"name": "Restock", "description": "Never run out", "condition": "0 stockouts"}]


class _StubParentBackend:
    def __init__(self, shop_exists: bool) -> None:
        self.shop_exists = shop_exists

    def list_locations(self, user_id: str) -> list[dict]:
        return [{"_id": user_id, "name": "shop 1"}] if self.shop_exists else []

    def get_catalog(self, user_id: str) -> list[dict]:
        return [{"_id": "prod1"}]

    def list_orders(self, user_id: str, start_date: str, end_date: str) -> list[dict]:
        return [{"_id": "ord1"}]

    def get_stock_levels(self, user_id: str) -> list[dict]:
        return []

    def list_invoices(self, user_id: str) -> list[dict]:
        return []

    def list_procurement(self, user_id: str) -> list[dict]:
        return []

    def get_day_summary(self, user_id: str) -> dict:
        return {}


class _StubModelClient:
    def complete(self, prompt: str) -> str:
        return json.dumps(GOALS) if "JSON array" in prompt else "A busy coffee duka."


@pytest.fixture
def override(request: pytest.FixtureRequest):
    app.dependency_overrides[get_parent_backend] = lambda: _StubParentBackend(request.param)
    app.dependency_overrides[get_identity_model_client] = _StubModelClient
    yield
    app.dependency_overrides.clear()


def test_identity_questions_lists_onboarding_questions() -> None:
    response = client.get("/identity/questions")
    assert response.status_code == 200
    assert "What does your business sell?" in response.json()["questions"]


@pytest.mark.parametrize("override", [True], indirect=True)
def test_existing_shop_gets_identity_from_backend_data(override: None) -> None:
    response = client.post("/identity/shop1", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["narrative"] == "A busy coffee duka."
    assert body["level"] == "early_stage"
    assert body["goals"] == GOALS


@pytest.mark.parametrize("override", [False], indirect=True)
def test_new_shop_without_answers_is_asked_to_onboard(override: None) -> None:
    response = client.post("/identity/shop1", json={})
    assert response.status_code == 422


@pytest.mark.parametrize("override", [False], indirect=True)
def test_new_shop_gets_identity_from_answers(override: None) -> None:
    answers = {"What does your business sell?": "Coffee"}
    response = client.post("/identity/shop1", json={"answers": answers})

    assert response.status_code == 200
    assert response.json()["level"] == "early_stage"


def test_identity_requires_bearer_token() -> None:
    response = client.post("/identity/shop1", json={})
    assert response.status_code == 401
