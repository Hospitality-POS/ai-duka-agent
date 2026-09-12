import base64

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from cryptography.hazmat.primitives import serialization

from agents.parent_agent import ParentAgent, build_stage_advisor_agents
from encryption.rsa_crypto import decrypt_rsa, encrypt_rsa, generate_rsa_keys
from setup.model_provider import create_model_client, setup_openrouter

app = FastAPI(title="Duka AI Engine")


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
        private_key = serialization.load_pem_private_key(request.private_key_pem.encode("utf-8"), password=None)
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
