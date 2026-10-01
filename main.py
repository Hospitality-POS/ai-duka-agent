import base64
from dotenv import load_dotenv

load_dotenv()

import edge_tts
from cryptography.hazmat.primitives import serialization
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from agents.parent_agent import ParentAgent, build_stage_advisor_agents
from ai_lining.chat_tools import build_dashboard_tools
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
from setup.business_identity import ChatModelClient
from setup.model_provider import create_model_client, setup_openrouter
from setup.parent_backend import BasePointParentBackendClient

app = FastAPI(title="Duka AI Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _bearer_token(request: Request) -> str | None:
    """Extract the caller's own Parent Backend token from an `Authorization: Bearer` header."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token if scheme.lower() == "bearer" and token else None


def _build_insight_model_client() -> ChatModelClient | None:
    """Build the Gemini model client AI Lining uses to generate insights, once, at startup."""
    try:
        return create_model_client("gemini")
    except ValueError:
        return None


_insight_model_client = _build_insight_model_client()


def get_dashboard_data_source(request: Request) -> DashboardDataSource:
    """Build a `DashboardDataSource` authenticated with the caller's own bearer token.

    Auth sessions are the frontend's job: each request supplies its own Parent Backend
    token and company code, so no server-side credential is stored or shared across users.
    """
    token = _bearer_token(request)
    company_code = request.headers.get("companycode")
    if not token or _insight_model_client is None:
        return MockDashboardDataSource()
    return RealDashboardDataSource(
        BasePointParentBackendClient(api_key=token, company_code=company_code),
        _insight_model_client,
    )


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


class TTSRequest(BaseModel):
    text: str
    voice: str | None = "en-KE-AsiliaNeural"


@app.post("/tts")
async def generate_speech(req: TTSRequest):
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    cleaned = (
        req.text.replace("*", "")
        .replace("#", "")
        .replace("`", "")
        .strip()
    )
    if len(cleaned) > 4000:
        cleaned = cleaned[:4000]

    voice = req.voice or "en-KE-AsiliaNeural"
    try:
        communicate = edge_tts.Communicate(cleaned, voice)
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        # Fallback to JennyNeural if Kenyan voice fails
        try:
            communicate = edge_tts.Communicate(cleaned, "en-US-JennyNeural")
            audio_bytes = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_bytes += chunk["data"]
            return Response(content=audio_bytes, media_type="audio/mpeg")
        except Exception as inner_e:
            raise HTTPException(status_code=500, detail=f"TTS synthesis error: {inner_e}")


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
    tools = None
    if request.provider == "gemini" and request.user_id:
        tools = build_dashboard_tools(request.user_id, data_source)

    try:
        model_client = create_model_client(
            request.provider, request.api_key, request.model, tools=tools
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        parent_agent = ParentAgent(build_stage_advisor_agents(model_client))
        response = parent_agent.handle(request.prompt, request.level)
        return {"agent": parent_agent.pick_agent(request.level).name, "response": response}
    except Exception as exc:  # pragma: no cover - defensive branch
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
