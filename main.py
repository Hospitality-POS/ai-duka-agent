import base64
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from cryptography.hazmat.primitives import serialization
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.parent_agent import ParentAgent, build_stage_advisor_agents
from ai_lining.chat_context import build_chat_context
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
from business_growth_strategy.leveling_engine import BusinessLevelingEngine
from encryption.rsa_crypto import decrypt_rsa, encrypt_rsa, generate_rsa_keys
from setup.business_identity import (
    ChatModelClient,
    build_user_response,
    get_onboarding_questions,
    is_existing_user,
    onboard_or_refresh_business,
)
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


@app.exception_handler(ValidationError)
def parent_backend_payload_mismatch(request: Request, exc: ValidationError) -> JSONResponse:
    """Report a Parent Backend payload that doesn't match the expected shape as a 502."""
    fields = ", ".join(".".join(str(part) for part in error["loc"]) for error in exc.errors())
    return JSONResponse(
        status_code=502, content={"detail": f"Unexpected Parent Backend data in: {fields}"}
    )


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
    return RealDashboardDataSource(_parent_backend_client(request, token))


def _parent_backend_client(request: Request, token: str) -> BasePointParentBackendClient:
    """Build a Parent Backend client with the caller's own token and tenant code."""
    return BasePointParentBackendClient(
        company_code=request.headers.get("companycode"), api_key=token
    )


def get_parent_backend(request: Request) -> BasePointParentBackendClient:
    """Require the caller's bearer token and build a Parent Backend client from it."""
    token = _bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization: Bearer token.")
    return _parent_backend_client(request, token)


def get_optional_parent_backend(request: Request) -> BasePointParentBackendClient | None:
    """Build a Parent Backend client when the caller sent a bearer token, else None."""
    token = _bearer_token(request)
    return _parent_backend_client(request, token) if token else None


def get_identity_model_client() -> ChatModelClient:
    """Build the model client that writes the digital identity and its goals."""
    try:
        return create_model_client("gemini")
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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


class IdentityRequest(BaseModel):
    answers: dict[str, str] | None = None


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
    request: ChatRequest,
    data_source: DashboardDataSource = Depends(get_dashboard_data_source),
    parent_backend: BasePointParentBackendClient | None = Depends(get_optional_parent_backend),
) -> dict[str, str]:
    try:
        model_client = create_model_client(request.provider, request.api_key, request.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    context = None
    if request.user_id:
        context = build_chat_context(request.user_id, data_source, parent_backend)

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
) -> WatchedProduct | None:
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


IDENTITY_ORDER_WINDOW_DAYS = 30


@app.get("/identity/questions")
def identity_questions() -> dict[str, list[str]]:
    return {"questions": get_onboarding_questions()}


@app.post("/identity/{shop_id}")
def create_identity(
    shop_id: str,
    request: IdentityRequest,
    parent_backend: BasePointParentBackendClient = Depends(get_parent_backend),
    model_client: ChatModelClient = Depends(get_identity_model_client),
) -> dict[str, object]:
    if request.answers is None and not is_existing_user(shop_id, parent_backend):
        raise HTTPException(
            status_code=422,
            detail="Shop not found in the Parent Backend: send onboarding answers "
            "(see GET /identity/questions).",
        )

    today = datetime.now(ZoneInfo("Africa/Nairobi")).date()
    leveling_engine = BusinessLevelingEngine(model_client)
    blueprint, level, goals = onboard_or_refresh_business(
        shop_id,
        parent_backend,
        vector_store=None,
        leveling_engine=leveling_engine,
        goal_agent=leveling_engine,
        model_client=model_client,
        start_date=(today - timedelta(days=IDENTITY_ORDER_WINDOW_DAYS)).isoformat(),
        end_date=today.isoformat(),
        onboarding_answers=request.answers,
    )
    return build_user_response(blueprint, level, goals)
