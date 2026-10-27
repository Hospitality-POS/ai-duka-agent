import pytest
from fastapi.testclient import TestClient

import main
from main import app
from setup.parent_backend import BasePointParentBackendClient

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


AUTH_HEADERS = {"Authorization": "Bearer tok1", "companycode": "co1"}


@pytest.fixture
def parent_backend_accepts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Make the Parent Backend accept only `tok1`/`co1`, recording each verified pair."""
    calls: list[tuple[str, str]] = []
    original_init = BasePointParentBackendClient.__init__

    def init(self, *args, api_key=None, company_code=None, **kwargs) -> None:
        original_init(self, *args, api_key=api_key, company_code=company_code, **kwargs)
        self._test_credentials = (api_key, company_code)

    def verify_token(self) -> bool:
        calls.append(self._test_credentials)
        return self._test_credentials == ("tok1", "co1")

    monkeypatch.setattr(BasePointParentBackendClient, "__init__", init)
    monkeypatch.setattr(BasePointParentBackendClient, "verify_token", verify_token)
    return calls


@pytest.fixture
def no_model_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record providers `/chat` tries to build a model client for, without calling them."""
    providers: list[str] = []

    def create_model_client(provider, *args, **kwargs):
        providers.append(provider)
        raise ValueError("model calls disabled in tests")

    monkeypatch.setattr(main, "create_model_client", create_model_client)
    return providers


@pytest.mark.parametrize(
    "headers",
    [{}, {"companycode": "co1"}, {"Authorization": "Bearer tok1"}, {"Authorization": "tok1"}],
)
def test_chat_requires_auth_headers(
    headers: dict[str, str], parent_backend_accepts: list, no_model_calls: list[str]
) -> None:
    response = client.post("/chat", json={"prompt": "hi", "provider": "openai"}, headers=headers)
    assert response.status_code == 401
    assert parent_backend_accepts == []
    assert no_model_calls == []


def test_chat_rejects_token_the_parent_backend_does_not_accept(
    parent_backend_accepts: list, no_model_calls: list[str]
) -> None:
    response = client.post(
        "/chat",
        json={"prompt": "hi", "provider": "openai"},
        headers={"Authorization": "Bearer forged", "companycode": "co1"},
    )
    assert response.status_code == 401
    assert parent_backend_accepts == [("forged", "co1")]
    assert no_model_calls == []


def test_chat_reaches_model_for_authenticated_caller(
    parent_backend_accepts: list, no_model_calls: list[str]
) -> None:
    response = client.post(
        "/chat", json={"prompt": "hi", "provider": "openai"}, headers=AUTH_HEADERS
    )
    assert response.status_code == 400
    assert no_model_calls == ["openai"]


def test_openrouter_setup_requires_auth(
    parent_backend_accepts: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "setup_openrouter", lambda *args: pytest.fail("not authenticated"))
    response = client.post("/setup/openrouter", json={})
    assert response.status_code == 401


def test_openrouter_setup_ignores_caller_env_var_name(
    parent_backend_accepts: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    received: list[tuple] = []

    def setup_openrouter(*args) -> tuple[bool, str]:
        received.append(args)
        return False, "OpenRouter API key is not set in environment variables."

    monkeypatch.setattr(main, "setup_openrouter", setup_openrouter)
    response = client.post(
        "/setup/openrouter",
        json={"env_var_name": "PARENT_BACKEND_API_KEY"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 400
    assert received == [(None,)]


def test_openrouter_setup_endpoint_requires_key(parent_backend_accepts: list) -> None:
    response = client.post("/setup/openrouter", json={"api_key": ""}, headers=AUTH_HEADERS)
    assert response.status_code == 400
