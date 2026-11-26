# Deployment

## Frontend (widget + playground)

| Item | Value |
|---|---|
| Hosting | Cloudflare static assets: "Pages", which Cloudflare now runs as part of Workers. New Pages projects deploy with `wrangler deploy` |
| URL | https://abinaya-chatbot.dentcare-demo.workers.dev (playground) · `/widget.js` (embed) |
| Config | `frontend/wrangler.jsonc` (assets only, no code); `frontend/_headers` (widget.js cached 5 min) |
| Build-time settings | `frontend/.env.production`: `VITE_API_URL`, `VITE_TURNSTILE_SITE_KEY` (public) |

```bash
cd frontend
npm run deploy      # tsc + vite build + wrangler deploy
```

**Turnstile site key:** `.env.production` still holds Cloudflare's *test* site key (`1x00000000000000000000AA`).
The production Worker correctly rejects test tokens (verified: the playground shows "We couldn't verify your
browser"). To go live, put the widget's real **site** key in `frontend/.env.production`, add
`abinaya-chatbot.dentcare-demo.workers.dev` to the widget's hostnames in the Cloudflare dashboard, and run
`npm run deploy`.

**Lesson learned:** run `wrangler pages project create` / `wrangler deploy` from the folder whose config you
mean to deploy. Running it from `backend/cloudflare-worker` created an accidental copy of the API Worker named
`abinaya-chatbot`, which was deleted straight away.


## Public API (Cloudflare Python Worker)

| Item | Value |
|---|---|
| Worker | `abinaya-chat-api` |
| URL | https://abinaya-chat-api.dentcare-demo.workers.dev |
| Account | the same Cloudflare account as the website (`dentcare-demo.workers.dev`) |
| Bindings | `VECTORIZE` → `abinaya-kb`; `RATE_LIMITER` → `RateLimiter` Durable Object (migration `v1`) |
| Secrets | `GEMINI_API_KEY`, `TURNSTILE_SECRET_KEY`, `SESSION_SIGNING_KEY` (see docs/authentication.md) |

```bash
cd backend/cloudflare-worker
nvm use
npx wrangler login                        # once per machine
npx wrangler secret put GEMINI_API_KEY         # paste when prompted; never commit
npx wrangler secret put TURNSTILE_SECRET_KEY   # the widget's SECRET key (~35 chars), not the site key
python3 -c "import secrets; print(secrets.token_urlsafe(48))" | npx wrangler secret put SESSION_SIGNING_KEY
uv run pywrangler deploy
```

Smoke test after deploying:

```bash
curl -i https://abinaya-chat-api.dentcare-demo.workers.dev/api/health          # 200 {"status":"ok"}
curl -i https://abinaya-chat-api.dentcare-demo.workers.dev/api/health/ready    # 200 {"status":"ready"}
curl -i -X POST https://abinaya-chat-api.dentcare-demo.workers.dev/api/chat -d '{"message":"hi"}'   # 401 (needs a session)
```

`/api/health/ready` returns `503 {"status":"not_ready"}` when the index is empty or has the wrong
dimensions, or when the Gemini key or models are unavailable. The reason is logged (`not_ready` event),
never returned to the client.

## Local development

`uv run pywrangler dev` runs the real Workers runtime on http://localhost:8787. Vectorize has no local
simulation, so the binding is `remote: true` and dev uses the real `abinaya-kb` index (read-only).
Secrets come from `.dev.vars` (copy `.dev.vars.example`).

## CPU time on the Workers Free plan (measured 2026-11-26)

Measured with `npx wrangler tail --format json` on the deployed Worker (15 requests):

| Route | CPU time | Wall time |
|---|---|---|
| `GET /api/health` | 8–19 ms | 9–19 ms |
| `GET /nope` (404) | 7–26 ms | 9–32 ms |
| `GET /api/health/ready` | 10–26 ms | 286–342 ms (waiting on Vectorize/Gemini doesn't count as CPU) |

Every request succeeded (`outcome=ok`), even though most exceeded the Free plan's documented 10 ms CPU
limit. Even the trivial 404 route costs 7–26 ms, so this is the Python (Pyodide) runtime's baseline, not
application logic.

Decision: stay on the Free plan as agreed, and watch for error 1102 (CPU exceeded), especially once
streaming is added in Phase 8. If requests start failing, Workers Paid ($5/month, 30 s CPU) is the fix,
and that is the user's call.

## Startup time

Cloudflare documents a 1-second startup budget. The figure Wrangler prints at deploy is noisy: identical code
measured 556 ms and 1,808 ms on back-to-back deploys (2026-11-26), and every deploy succeeded. An earlier
1,296 ms reading that I attributed to a module-level `import asyncio` was probably the same noise. Runtime-only
imports stay inside the functions that use them anyway, which keeps the module light.

## Verifying streaming

`pywrangler dev --remote` is not supported for Python Workers. Streaming is verified in the local Workers
runtime (`curl -N`) and end-to-end in the browser with a real Turnstile session (Phases 15–16).
