# API Contract — Abinaya Garments AI Chatbot

> Draft agreed in Phase 0 (2026-11-26). Changes to this contract require updating both backend and frontend.

Error envelope for every non-stream error:
```json
{ "error": { "code": "session_expired", "message": "Your session has expired." }, "request_id": "r_9b1f2c" }
```
| Code | HTTP | Code | HTTP |
|---|---|---|---|
| `bad_request` | 400 | `payload_too_large` | 413 |
| `unauthorized` | 401 | `validation_error` | 422 |
| `session_expired` | 401 | `rate_limited` | 429 + `Retry-After` |
| `forbidden_origin` | 403 | `internal_error` | 500 |
| `turnstile_failed` | 403 | `upstream_unavailable` | 503 |
| `not_found` / `method_not_allowed` | 404 / 405 | | |

Messages are generic; details only in logs (keyed by `request_id`).

### Public Worker endpoints
| Endpoint | Auth | Request | Success |
|---|---|---|---|
| `GET /api/health` | none | — | `200 {"status":"ok","version":"0.1.0"}` |
| `GET /api/health/ready` | none (IP-limited, cached ~30 s) | — | `200 {"status":"ready"}` / `503 {"status":"not_ready"}` — checks Vectorize `describe()` (dimensions match, index non-empty) and a no-token Gemini model lookup; no details exposed |
| `OPTIONS /api/*` | — | preflight | `204`, exact `Access-Control-Allow-Origin`, `Vary: Origin`, `Access-Control-Allow-Headers: Authorization, Content-Type`, `Access-Control-Max-Age: 600` |
| `POST /api/session` | Origin + Turnstile | `{"turnstile_token":"0.AbC…"}` (≤ 4 KB) | `200 {"session_token":"eyJ…","token_type":"Bearer","expires_in":900,"expires_at":"2026-11-26T10:15:00Z"}` |
| `POST /api/chat` | Origin + Bearer JWT | below (≤ 32 KB) | `200 text/event-stream` |

```http
POST /api/chat
Authorization: Bearer eyJhbGciOiJIUzI1NiIsImtpZCI6InYxIiwidHlwIjoiSldUIn0…
Content-Type: application/json
Accept: text/event-stream
Origin: https://abinayagarment.dentcare-demo.workers.dev

{
  "message": "Do you print company logos on polo t-shirts?",
  "history": [
    { "role": "user", "content": "Hi" },
    { "role": "assistant", "content": "Hello! How can I help you today?" }
  ],
  "conversation_id": "3f8a6c2e-6a1b-4f43-9a51-0c6e2f9d1b77"
}
```
Initial limits (configurable): `message` 1–1,000 chars; `history` ≤ 10 items, each ≤ 2,000 chars, roles
`user|assistant`, alternating; `conversation_id` optional UUID used only for log correlation.

SSE response (`Content-Type: text/event-stream; charset=utf-8`, `Cache-Control: no-cache, no-transform`,
`X-Accel-Buffering: no`):
```
event: start
data: {"request_id":"r_9b1f2c","conversation_id":"3f8a6c2e-…"}

event: token
data: {"text":"Yes — we offer custom logo "}

event: token
data: {"text":"printing on polos for corporate orders."}

event: complete
data: {"finish_reason":"stop","sources":[{"document":"services.md","section":"Custom branding","chunk_id":"services-002"}]}

```
Failure after streaming started:
```
event: error
data: {"code":"upstream_unavailable","message":"The assistant is temporarily unavailable. Please try again."}

```
Contract rules: exactly one `start`; zero or more `token`; exactly one terminal `complete` **or** `error`, then the
stream closes. Auth, validation and rate-limit failures happen **before** streaming and use JSON + HTTP status.
`finish_reason` ∈ `stop | max_tokens | safety | other`. `: ping` comment lines may appear (clients ignore them).

### Knowledge index record (Vectorize, internal)
```json
{
  "id": "products-003",
  "values": [0.0123, -0.0456, "… 768 floats"],
  "metadata": {
    "document": "products.md",
    "section": "Polo T-Shirts",
    "text": "Classic Polo T-Shirt — …",
    "content_sha256": "9f2c…",
    "embedding_model": "gemini-embedding-001",
    "dimensions": 768,
    "index_version": "20261126T101500Z"
  }
}
```
Metadata index on `document` (string) for optional filtering. Chunk text ≤ ~1,500 chars keeps metadata well under 10 KiB.

### Indexer CLI (operator only, never deployed)
| Command | Does |
|---|---|
| `python -m indexer chunks` | Load + chunk knowledge files, print chunk report (no API calls) |
| `python -m indexer reindex --env dev\|prod [--full]` | Embed new/changed chunks, upsert, delete stale ids, write manifest |
| `python -m indexer query "text" --env dev\|prod` | Embed query + Vectorize REST query → ranked chunks with scores |
| `python -m indexer eval --env dev` | Run labelled question set → hit-rate report, used to calibrate `MIN_SCORE` |

Credentials (operator `.env`, git-ignored): `GEMINI_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`
(scoped to **Vectorize Write** only).
