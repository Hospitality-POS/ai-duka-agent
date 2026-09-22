import base64

from cryptography.hazmat.primitives import serialization
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from agents.parent_agent import ParentAgent, build_stage_advisor_agents
from ai_lining.dashboard import (
    DashboardDataSource,
    MockDashboardDataSource,
    apply_insight,
    build_dashboard,
    record_alert_action,
)
from ai_lining.models import (
    Alert,
    AlertActionRequest,
    ApplyInsightRequest,
    ChatCard,
    DailyObservation,
    Header,
    Insight,
    MyStock,
    SalesPerformance,
    WatchedProduct,
    WhatsHappening,
)
from encryption.rsa_crypto import decrypt_rsa, encrypt_rsa, generate_rsa_keys
from setup.model_provider import create_model_client, setup_openrouter

app = FastAPI(title="Duka AI Engine")

_dashboard_data_source = MockDashboardDataSource()


def get_dashboard_data_source() -> DashboardDataSource:
    """Return the `DashboardDataSource` used to serve the AI Lining dashboard routes."""
    return _dashboard_data_source


class OpenRouterRequest(BaseModel):
    api_key: str | None = None
    env_var_name: str = "OPENROUTER_API_KEY"


class ChatRequest(BaseModel):
    prompt: str
    level: str | None = None
    provider: str = "gemini"
    api_key: str | None = None
    model: str | None = None


class RSAEncryptRequest(BaseModel):
    data: str
    public_key_pem: str


class RSADecryptRequest(BaseModel):
    data: str
    private_key_pem: str


@app.get("/")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/rsa/generate-keys", methods=["GET", "POST"])
def generate_keys() -> dict[str, list[str]]:
    private_key, public_key = generate_rsa_keys()
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return {"keys": [private_key_pem, public_key_pem]}


@app.post("/rsa/encrypt")
def encrypt_rsa_payload(request: RSAEncryptRequest) -> dict[str, str]:
    try:
        public_key = serialization.load_pem_public_key(request.public_key_pem.encode("utf-8"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid public key: {exc}") from exc

    encrypted = encrypt_rsa(request.data, public_key)
    encoded = base64.b64encode(encrypted).decode("utf-8")
    return {"encrypted_data": encoded}


@app.post("/rsa/decrypt")
def decrypt_rsa_payload(request: RSADecryptRequest) -> dict[str, str]:
    try:
        private_key = serialization.load_pem_private_key(
            request.private_key_pem.encode("utf-8"), password=None
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid private key: {exc}") from exc

    try:
        encrypted_data = base64.b64decode(request.data)
        decrypted = decrypt_rsa(encrypted_data, private_key)
    except Exception as exc:  # pragma: no cover - defensive branch
        raise HTTPException(status_code=400, detail=f"Unable to decrypt data: {exc}") from exc

    return {"data": decrypted}


@app.post("/setup/openrouter")
def openrouter_setup(request: OpenRouterRequest) -> dict[str, object]:
    success, message = setup_openrouter(request.api_key, request.env_var_name)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, str]:
    try:
        model_client = create_model_client(request.provider, request.api_key, request.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parent_agent = ParentAgent(build_stage_advisor_agents(model_client))
    response = parent_agent.handle(request.prompt, request.level)
    return {"agent": parent_agent.pick_agent(request.level).name, "response": response}


@app.get("/ai-lining/{user_id}/dashboard")
def get_ai_lining_dashboard(
    user_id: str, data_source: DashboardDataSource = Depends(get_dashboard_data_source)
) -> dict[str, object]:
    dashboard = build_dashboard(user_id, data_source)
    return dashboard.model_dump(by_alias=True)


@app.get("/ai-lining/{user_id}/header")
def get_header(
    user_id: str, data_source: DashboardDataSource = Depends(get_dashboard_data_source)
) -> Header:
    return data_source.get_header(user_id)


@app.get("/ai-lining/{user_id}/daily-observation")
def get_daily_observation(
    user_id: str, data_source: DashboardDataSource = Depends(get_dashboard_data_source)
) -> DailyObservation:
    return data_source.get_daily_observation(user_id)


@app.get("/ai-lining/{user_id}/watched-product")
def get_watched_product(
    user_id: str, data_source: DashboardDataSource = Depends(get_dashboard_data_source)
) -> WatchedProduct:
    return data_source.get_watched_product(user_id)


@app.get("/ai-lining/{user_id}/alert")
def get_alert(
    user_id: str, data_source: DashboardDataSource = Depends(get_dashboard_data_source)
) -> Alert | None:
    return data_source.get_alert(user_id)


@app.get("/ai-lining/{user_id}/whats-happening")
def get_whats_happening(
    user_id: str, data_source: DashboardDataSource = Depends(get_dashboard_data_source)
) -> WhatsHappening:
    return data_source.get_whats_happening(user_id)


@app.get("/ai-lining/{user_id}/insights")
def get_insights(
    user_id: str, data_source: DashboardDataSource = Depends(get_dashboard_data_source)
) -> list[Insight]:
    return data_source.get_insights(user_id)


@app.post("/ai-lining/{user_id}/insights/apply")
def post_apply_insight(
    user_id: str,
    request: ApplyInsightRequest,
    data_source: DashboardDataSource = Depends(get_dashboard_data_source),
) -> dict[str, object]:
    success, message = apply_insight(user_id, request.insight_id, data_source)
    if not success:
        raise HTTPException(status_code=404, detail=message)
    return {"success": True, "message": message}


@app.get("/ai-lining/{user_id}/sales-performance")
def get_sales_performance(
    user_id: str, data_source: DashboardDataSource = Depends(get_dashboard_data_source)
) -> SalesPerformance:
    return data_source.get_sales_performance(user_id)


@app.get("/ai-lining/{user_id}/my-stock")
def get_my_stock(
    user_id: str, data_source: DashboardDataSource = Depends(get_dashboard_data_source)
) -> MyStock:
    return data_source.get_my_stock(user_id)


@app.get("/ai-lining/{user_id}/chat-card")
def get_chat_card(
    user_id: str, data_source: DashboardDataSource = Depends(get_dashboard_data_source)
) -> ChatCard:
    return data_source.get_chat_card(user_id)


@app.post("/ai-lining/{user_id}/alerts/action")
def post_alert_action(
    user_id: str,
    request: AlertActionRequest,
    data_source: DashboardDataSource = Depends(get_dashboard_data_source),
) -> dict[str, object]:
    success, message = record_alert_action(user_id, request.alert_id, data_source)
    if not success:
        raise HTTPException(status_code=404, detail=message)
    return {"success": True, "message": message}
