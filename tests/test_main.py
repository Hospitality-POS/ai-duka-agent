
from fastapi.testclient import TestClient

from main import app

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
