# Deployment

## Public API (Cloudflare Python Worker)

| Item | Value |
|---|---|
| Worker | `abinaya-chat-api` |
| URL | https://abinaya-chat-api.dentcare-demo.workers.dev |
| Account | the same Cloudflare account as the website (`dentcare-demo.workers.dev`) |
| Bindings | `VECTORIZE` → `abinaya-kb` |
| Secrets | `GEMINI_API_KEY` (Phase 4); `SESSION_SIGNING_KEY` and `TURNSTILE_SECRET_KEY` follow in Phase 6 |

```bash
cd backend/cloudflare-worker
nvm use
npx wrangler login                        # once per machine
npx wrangler secret put GEMINI_API_KEY    # paste the key when prompted; never commit it
uv run pywrangler deploy
```

Smoke test after deploying:

```bash
curl -i https://abinaya-chat-api.dentcare-demo.workers.dev/api/health          # 200 {"status":"ok"}
curl -i https://abinaya-chat-api.dentcare-demo.workers.dev/api/health/ready    # 200 {"status":"ready"}
curl -i -X POST https://abinaya-chat-api.dentcare-demo.workers.dev/api/dev/search   # 404 (dev only)
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
