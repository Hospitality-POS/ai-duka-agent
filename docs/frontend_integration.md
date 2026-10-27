# Duka AI Engine — Frontend Integration Guide

How a client app (Flutter, web, etc.) talks to every route exposed by `main.py`.
For the AI Lining dashboard specifically, see [`ai_lining_integration.md`](ai_lining_integration.md) —
this doc covers the rest of the API and links out to that one.

## Base URL

Local dev: `http://localhost:8000` (`uvicorn main:app --reload`).

`/chat` and `/setup/openrouter` require the caller's own Parent Backend login: send
`Authorization: Bearer <token>` and `companycode: <code>` headers. The token is checked
against the Parent Backend (`GET /biashara-ai/permissions`) before any model call; a
missing, invalid, or expired token returns 401.

## Error handling

All endpoints return standard FastAPI error bodies on failure:

```json
{ "detail": "<message>" }
```

Non-2xx responses map to `HTTPException` — read `detail` and surface it to the user rather
than a generic "something went wrong."

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Healthcheck |
| GET/POST | `/rsa/generate-keys` | Generate an RSA key pair |
| POST | `/rsa/encrypt` | Encrypt a string with a public key |
| POST | `/rsa/decrypt` | Decrypt a payload with a private key |
| POST | `/setup/openrouter` | Validate an OpenRouter API key |
| POST | `/chat` | Send a prompt to a stage advisor agent |
| GET | `/ai-lining/{user_id}/...` | AI Lining dashboard — see [`ai_lining_integration.md`](ai_lining_integration.md) |

### `GET /`

```json
{ "status": "ok" }
```

### `GET` or `POST /rsa/generate-keys`

No request body. Returns a fresh key pair as PEM strings, private key first:

```json
{ "keys": ["-----BEGIN RSA PRIVATE KEY-----...", "-----BEGIN PUBLIC KEY-----..."] }
```

Store the private key client-side (or wherever it needs to decrypt later) — the server
doesn't persist either key.

### `POST /rsa/encrypt`

```json
{ "data": "plain text", "public_key_pem": "-----BEGIN PUBLIC KEY-----..." }
```

```json
{ "encrypted_data": "base64-encoded-ciphertext" }
```

RSA-OAEP with SHA-256 caps the plaintext at roughly 190 bytes for a 2048-bit key — this
is for small payloads (tokens, short identifiers), not documents.

### `POST /rsa/decrypt`

```json
{ "data": "base64-encoded-ciphertext", "private_key_pem": "-----BEGIN RSA PRIVATE KEY-----..." }
```

```json
{ "data": "plain text" }
```

400 on an invalid key or ciphertext that doesn't decrypt.

### `POST /setup/openrouter`

```json
{ "api_key": "sk-or-..." }
```

`api_key` is optional — omit it to validate the server's `OPENROUTER_API_KEY`. Returns 200
with `{"success": true, "message": "..."}`, or 400 with the failure reason if the key is
missing/invalid.

### `POST /chat`

```json
{
  "prompt": "How do I grow my customer base?",
  "level": "early",
  "provider": "gemini",
  "api_key": "...",
  "model": "gemini-2.5-flash"
}
```

Only `prompt` is required. `provider` defaults to `"gemini"` (the other option is
`"openrouter"`); omit `api_key` to fall back to the provider's env var
(`GEMINI_API_KEY` / `OPENROUTER_API_KEY`). `level` selects which stage advisor agent
answers (see `src/agents/parent_agent.py`); omit it to let the parent agent pick.

```json
{ "agent": "early-stage-advisor", "response": "..." }
```

400 if the provider is unknown or no API key is available; 401 without valid auth headers.

## Suggested client flow

1. On first launch, call `/rsa/generate-keys` once and cache the pair (or generate keys
   however your client already handles crypto — the server doesn't require its own keys).
2. Call `/setup/openrouter` (or validate Gemini the same way, once that route exists) before
   letting the user chat, so a bad key surfaces during setup instead of on first prompt.
3. Use `/chat` for free-form advice; use the `/ai-lining/{user_id}/...` routes for the
   dashboard — see [`ai_lining_integration.md`](ai_lining_integration.md) for shapes and the
   full request/response examples.
