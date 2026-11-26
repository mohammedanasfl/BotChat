# Security controls

A one-page summary of how the public chat API is protected. Details: [authentication.md](authentication.md),
[rag.md](rag.md), [api-contract.md](api-contract.md).

| Layer | Control | Where |
|---|---|---|
| Bots | Cloudflare Turnstile verified server-side (hostname + action, fails closed) | `services/turnstile.py`, `routes/session.py` |
| Identity | 15-minute HS256 session JWT; `401 unauthorized` / `session_expired` | `services/tokens.py`, `core/auth.py` |
| Browsers | Exact-origin CORS allowlist (defense in depth, not authentication) | `core/cors.py` |
| Abuse | Exact per-key rate limits (below) | `core/rate_limit.py`, `durable/rate_limiter.py` |
| Input | Body ≤ 32 KB (checked from `Content-Length` before reading); strict chat schema | `main.py`, `core/validation.py` |
| Cost | `maxOutputTokens` 1,024; minimal thinking; no automatic retries; Gemini free-tier quota is a hard cap | `prompts/builder.py` |
| Model | Knowledge-only answers; retrieved text and history treated as data; off-topic and injection refusal | `prompts/system_prompt.py` |
| Errors | Generic client messages; details only in logs, keyed by `request_id` | `app.py`, `core/errors.py` |
| Secrets | Worker secrets / git-ignored `.dev.vars`; excluded from logs and `repr` | `config/settings.py` |
| Index | The Worker can only read Vectorize; writes need the operator's `wrangler login` | `services/retrieval.py`, `indexer/` |

## Rate limits

| Scope | Key | Limit (per 60 s window) | Checked |
|---|---|---|---|
| `session-ip` | visitor IP (`CF-Connecting-IP`) | `RATE_LIMIT_SESSION_IP` = 5 | before calling Turnstile |
| `chat-ip` | visitor IP | `RATE_LIMIT_CHAT_IP` = 20 | before checking the token (also stops invalid-token floods) |
| `chat-session` | session id (`sub`) | `RATE_LIMIT_CHAT_SESSION` = 8 | after checking the token |

Over the limit gives `429 rate_limited` with `Retry-After: 60`, plus CORS headers so the widget can read it.
The limits are `wrangler.jsonc` vars, so they can change without code changes.

**Why a Durable Object instead of the Rate Limiting binding:** the binding works in local dev, but on live
workers.dev it always returned `success: true` (`{'success': True, 'rate': None}`; 60 requests from one IP
were never blocked). This is a known open Cloudflare issue
([workers-sdk#16097](https://github.com/cloudflare/workers-sdk/issues/16097)). Each limiter key now gets
its own `RateLimiter` Durable Object (SQLite-backed, available on the Free plan) holding an exact
fixed-window counter. The counting logic is the pure `count_hit()` function, which is unit-tested.

Verified in production (2026-11-26): 25 fast unauthenticated chats gave `401` ×20 then `429` ×5;
7 session requests gave `403` ×5 then `429` ×2. Durable Object calls cost a median of 2 ms CPU.

## Chat request validation (`POST /api/chat`)

| Field | Rule |
|---|---|
| `message` | string, 1–1,000 characters after trimming |
| `history` | optional list of ≤ 10 `{role: "user" or "assistant", content}`, each 1–2,000 characters |
| `conversation_id` | optional UUID (used only to link log lines) |

Violations give `422 validation_error` with a short message naming the field.

## Usage logging

Every answer logs one `chat_completed` event: `request_id`, anonymous `session` id, `conversation_id`,
prompt and output token counts, number of sources, `finish_reason` and duration. Message text, tokens and
IP addresses are never logged (a unit test checks this).

## Known limitations

- Client-supplied history can be forged (there is no server-side storage). It is bounded and treated as
  untrusted by the prompt rules.
- IP limits are shared by visitors behind the same address (offices, mobile carriers).
- The Gemini free tier may use prompts to improve Google's products. The widget shows a privacy note, and
  the paid tier should be used before real production use.
