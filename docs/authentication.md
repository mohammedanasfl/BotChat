# Authentication

Visitors are anonymous. A visitor proves once that they are human (Cloudflare Turnstile) and receives a
short-lived signed session token, which they send with each chat message.

```
widget ── Turnstile token ──► POST /api/session ──► siteverify ──► session token (15 min)
widget ── Authorization: Bearer <session token> ──► POST /api/chat
```

## POST /api/session

Request: `{"turnstile_token": "<token from the Turnstile widget>"}`

The Worker calls `https://challenges.cloudflare.com/turnstile/v0/siteverify` with the secret, the token,
the visitor IP (`CF-Connecting-IP`) and a random `idempotency_key`, then requires:

- `success: true`;
- `hostname` in `TURNSTILE_ALLOWED_HOSTNAMES` (production: `abinayagarment.dentcare-demo.workers.dev`);
- `action == "chat_session"` (required in production; Cloudflare's test keys don't send an action).

Outcomes:

| Siteverify reply | Meaning | Response |
|---|---|---|
| 200 `success: true` and checks pass | human, right site | `200` session |
| 200 or **400** with `success: false` (e.g. `invalid-input-response`) | bad, expired or reused token | `403 turnstile_failed` (reason logged) |
| `invalid-input-secret` / `missing-input-secret` | **our** secret is wrong | `500` + `config_error` log |
| network error, timeout or 5xx | Turnstile unavailable | `503`, **fail closed**, never a free session |

Real siteverify answers rejected input with **HTTP 400 plus a JSON result** (the test keys answer 200), so
400 is treated as a verification result rather than an outage. Found while verifying the deployment.

Response: `{"session_token", "token_type": "Bearer", "expires_in": 900, "expires_at": "…Z"}`

## Session token

A standard JWT (RFC 7519) signed with HMAC-SHA256, implemented with the Python standard library in
`src/services/tokens.py`. Unit tests cross-check it against PyJWT in both directions.

| Claim | Value |
|---|---|
| `iss` / `aud` | `abinaya-chat-api` / `abinaya-chat-widget` |
| `sub` | random anonymous session id (`s_…`), used for per-session rate limits in Phase 7 |
| `jti` | random token id |
| `iat` / `exp` | issued at / expires (`SESSION_TTL_SECONDS`, default 900) |

Verification accepts only `alg: HS256` (rejecting `none` and algorithm confusion), compares signatures in
constant time, and checks `iss`, `aud`, `exp` and `iat` with 30 s of leeway.

| Problem | Response |
|---|---|
| No `Authorization: Bearer` header, malformed or modified token, wrong key, issuer or audience | `401 unauthorized` |
| Valid token past `exp` | `401 session_expired` (the widget renews silently via Turnstile) |

There is no refresh endpoint: Turnstile is the only way to get a session. Rotating `SESSION_SIGNING_KEY`
invalidates every session; visitors renew automatically.

## Secrets and configuration

| Name | Where | Notes |
|---|---|---|
| `TURNSTILE_SECRET_KEY` | Worker secret | From the Turnstile widget in the Cloudflare dashboard |
| `SESSION_SIGNING_KEY` | Worker secret | 48 random bytes, generated and piped straight into `wrangler secret put` (never displayed) |
| `TURNSTILE_ALLOWED_HOSTNAMES` | `wrangler.jsonc` var | Comma-separated; required in production |
| Turnstile **site key** | frontend (public) | Safe to publish |

Local development (`.dev.vars`) uses Cloudflare's test secret `1x0000000000000000000000000000000AA`, which
accepts any token and reports hostname `example.com`, plus a random local signing key.

## Tests

- `tests/unit/test_tokens.py`: valid, expired (and leeway), wrong key, modified payload or signature,
  `alg=none`, wrong issuer or audience, malformed, missing claims, PyJWT interoperability.
- `tests/unit/test_auth.py`: siteverify checks (success, failure, hostname, action), session issuance,
  fail-closed on timeout, input validation, `/api/chat` with valid, missing, invalid, foreign-key and
  expired tokens, and secrets kept out of logs.
- Local runtime: test token gives a session, chat answers, missing or modified token gives `unauthorized`,
  expired token gives `session_expired`.
- Production (2026-11-26): chat without a token or with a forged token gives `401`; a fake Turnstile token
  gives `403 turnstile_failed`, which proves the real secret is accepted (a wrong secret gives `500` with
  `invalid-input-secret` in the logs). A full success with a real Turnstile token is verified in Phase 12
  with the frontend widget.
