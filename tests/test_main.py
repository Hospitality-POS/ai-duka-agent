
import httpx
import pytest
from fastapi.testclient import TestClient

from main import app, get_dashboard_data_source

client = TestClient(app)


def test_healthcheck() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_rsa_round_trip() -> None:
    private_key, public_key = client.post("/rsa/generate-keys").json()["keys"]
    payload = client.post(
        "/rsa/encrypt",
        json={"data": "hello world", "public_key_pem": public_key},
    )
    assert payload.status_code == 200

    result = client.post(
        "/rsa/decrypt",
        json={"data": payload.json()["encrypted_data"], "private_key_pem": private_key},
    )
    assert result.status_code == 200
    assert result.json()["data"] == "hello world"


def test_openrouter_setup_endpoint_requires_key() -> None:
    response = client.post("/setup/openrouter", json={"api_key": ""})
    assert response.status_code == 400


class _FailingDashboardSource:
    def __init__(self, status: int) -> None:
        self.status = status

    def get_header(self, user_id: str) -> None:
        request = httpx.Request("GET", "http://backend/biashara-ai/dashboard")
        response = httpx.Response(self.status, request=request)
        raise httpx.HTTPStatusError("backend error", request=request, response=response)


@pytest.mark.parametrize("backend_status,expected_status", [(401, 401), (404, 404), (500, 502)])
def test_parent_backend_errors_are_translated(backend_status: int, expected_status: int) -> None:
    app.dependency_overrides[get_dashboard_data_source] = lambda: _FailingDashboardSource(
        backend_status
    )
    try:
        response = client.get("/ai-lining/shop1/header")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == expected_status


def test_cors_preflight_allows_bearer_header() -> None:
    response = client.options(
        "/ai-lining/shop1/dashboard",
        headers={
            "Origin": "http://localhost:5000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


def test_dashboard_source_forwards_the_callers_company_code() -> None:
    from starlette.requests import Request

    request = Request(
        {
            "type": "http",
            "headers": [(b"authorization", b"Bearer tok1"), (b"companycode", b"co1")],
        }
    )
    source = get_dashboard_data_source(request)
    assert source._parent_backend._client.headers["companycode"] == "co1"
