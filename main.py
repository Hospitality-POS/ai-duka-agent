import base64
import logging
import os

import httpx
from cryptography.hazmat.primitives import serialization
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from agents.parent_agent import ParentAgent, build_stage_advisor_agents
from ai_lining.chat_context import build_dashboard_context
from ai_lining.dashboard import (
    DashboardDataSource,
    MockDashboardDataSource,
    RealDashboardDataSource,
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
from setup.parent_backend import BasePointParentBackendClient

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Duka AI Engine")

# Browser (Flutter web) clients need CORS. Auth is a bearer header, not cookies, so no
# credentials mode is needed; narrow the origins in production via CORS_ALLOW_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Backend statuses the app can act on (re-login, wrong shop id) pass through; anything else
# is the Parent Backend failing, not the caller.
_PASSTHROUGH_BACKEND_STATUSES = {401, 403, 404}


@app.exception_handler(httpx.HTTPStatusError)
def parent_backend_status_error(request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    """Translate a Parent Backend error response into one the app can act on."""
    status = exc.response.status_code
    detail = f"Parent Backend {status}: {exc.response.text[:200]}"
    logger.warning("%s %s -> %s", exc.request.method, exc.request.url, detail)
    if status in _PASSTHROUGH_BACKEND_STATUSES:
        return JSONResponse(status_code=status, content={"detail": detail})
    return JSONResponse(status_code=502, content={"detail": detail})


@app.exception_handler(httpx.RequestError)
def parent_backend_unreachable(request: Request, exc: httpx.RequestError) -> JSONResponse:
    """Report an unreachable Parent Backend as a 502 instead of a generic 500."""
    logger.warning("Parent Backend unreachable: %r", exc)
    return JSONResponse(status_code=502, content={"detail": "Parent Backend is unreachable."})


def _bearer_token(request: Request) -> str | None:
    """Extract the caller's own Parent Backend token from an `Authorization: Bearer` header."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token if scheme.lower() == "bearer" and token else None


def get_dashboard_data_source(request: Request) -> DashboardDataSource:
    """Build a `DashboardDataSource` authenticated with the caller's own bearer token.

    Auth sessions are the frontend's job: each request supplies its own Parent Backend
    token, so no server-side credential is stored or shared across users.
    """
    token = _bearer_token(request)
    if not token:
        return MockDashboardDataSource()
    parent_backend = BasePointParentBackendClient(
        company_code=request.headers.get("companycode"), api_key=token
    )
    return RealDashboardDataSource(parent_backend)


class OpenRouterRequest(BaseModel):
    api_key: str | None = None
    env_var_name: str = "OPENROUTER_API_KEY"


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    prompt: str
    level: str | None = None
    provider: str = "gemini"
    api_key: str | None = Field(default=None, alias="apiKey")
    model: str | None = None
    user_id: str | None = Field(default=None, alias="userId")


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
def chat(
    request: ChatRequest, data_source: DashboardDataSource = Depends(get_dashboard_data_source)
) -> dict[str, str]:
    try:
        model_client = create_model_client(request.provider, request.api_key, request.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    context = None
    if request.user_id:
        context = build_dashboard_context(request.user_id, data_source)

    parent_agent = ParentAgent(build_stage_advisor_agents(model_client))
    response = parent_agent.handle(request.prompt, request.level, context)
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
