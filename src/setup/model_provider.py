# we will need to integrate with two models: Gemini and OpenRouter.

import logging
import os

from google import genai
from google.genai.errors import ServerError
from openrouter import OpenRouter

logger = logging.getLogger(__name__)

# Env vars hold the actual keys; never hardcode a key here.
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL_VERSION", "gemini-3.7-flash")
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"

# Models to try, in order, when the primary Gemini model returns a 503 (e.g. "high demand").
GEMINI_FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.8-flash").split(",")
    if m.strip()
]


def setup_openrouter(
    api_key: str | None = None, env_var_name: str = "OPENROUTER_API_KEY"
) -> tuple[bool, str]:
    """Validate an OpenRouter API key and confirm the client can access model metadata."""
    resolved_key = api_key or os.getenv(env_var_name)
    if not resolved_key:
        return False, "OpenRouter API key is not set in environment variables."

    try:
        with OpenRouter(api_key=resolved_key) as client:
            response = client.get_models()
            if response:
                return True, "OpenRouter setup successful."
            return False, "Failed to retrieve models from OpenRouter."
    except Exception as exc:  # pragma: no cover - defensive branch
        return False, f"An error occurred while setting up OpenRouter: {exc}"


def setup_gemini(
    api_key: str | None = None, env_var_name: str = "GEMINI_API_KEY"
) -> tuple[bool, str]:
    """Validate a Gemini API key and confirm the client can generate content."""
    resolved_key = api_key or os.getenv(env_var_name)
    if not resolved_key:
        return False, "Gemini API key is not set in environment variables."

    try:
        client = genai.Client(api_key=resolved_key)
        response = client.models.generate_content(
            model=DEFAULT_GEMINI_MODEL, contents="Hello, Gemini! Are we connected?"
        )
        if response and response.text:
            return True, "Gemini setup successful."
        return False, "Gemini did not return a response."
    except Exception as exc:  # pragma: no cover - defensive branch
        return False, f"An error occurred while setting up Gemini: {exc}"


class OpenRouterChatClient:
    """A `ChatModelClient` (see `setup/business_identity.py`) backed by the OpenRouter API."""

    def __init__(self, api_key: str, model: str = DEFAULT_OPENROUTER_MODEL) -> None:
        self._api_key = api_key
        self._model = model

    def complete(self, prompt: str) -> str:
        """Send a prompt to OpenRouter and return the completion text."""
        with OpenRouter(api_key=self._api_key) as client:
            response = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content


class GeminiChatClient:
    """A `ChatModelClient` (see `setup/business_identity.py`) backed by the Google Gemini API."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_GEMINI_MODEL,
        fallback_models: list[str] | None = None,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._fallback_models = (
            GEMINI_FALLBACK_MODELS if fallback_models is None else fallback_models
        )

    def complete(self, prompt: str) -> str:
        """Send a prompt to Gemini, falling back to other models if one is unavailable."""
        last_error: ServerError | None = None
        for model in (self._model, *self._fallback_models):
            try:
                response = self._client.models.generate_content(model=model, contents=prompt)
                return response.text
            except ServerError as exc:  # pragma: no cover - defensive branch
                logger.warning("Gemini model %r unavailable, trying next fallback: %s", model, exc)
                last_error = exc
        raise last_error


MODEL_CLIENTS = {
    "openrouter": OpenRouterChatClient,
    "gemini": GeminiChatClient,
}

PROVIDER_ENV_VARS = {
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def create_model_client(
    provider: str, api_key: str | None = None, model: str | None = None
) -> OpenRouterChatClient | GeminiChatClient:
    """Build a `ChatModelClient` for the given provider, so callers can switch models at will."""
    try:
        client_cls = MODEL_CLIENTS[provider]
    except KeyError as exc:
        raise ValueError(
            f"Unknown model provider {provider!r}; choose one of {sorted(MODEL_CLIENTS)}"
        ) from exc

    resolved_key = api_key or os.getenv(PROVIDER_ENV_VARS[provider])
    if not resolved_key:
        raise ValueError(f"No API key provided or set in {PROVIDER_ENV_VARS[provider]}.")

    return client_cls(resolved_key, model) if model else client_cls(resolved_key)
