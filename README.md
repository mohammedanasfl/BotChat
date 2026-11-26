# Abinaya Garments AI Chatbot

An embeddable, RAG-grounded, streaming AI chatbot for the
[Abinaya Garment Shop website](https://abinayagarment.dentcare-demo.workers.dev/).

```
Website ──<script widget.js>──► <abinaya-chat> (React in Shadow DOM) ──► Turnstile
                                        │  POST /api/session, POST /api/chat (SSE)
                                        ▼
                     Cloudflare Python Worker: auth · rate limits · RAG · streaming
                        │ embed query          │ search            │ stream answer
                        ▼                      ▼                   ▼
                 gemini-embedding-001   Vectorize abinaya-kb   gemini-3.5-flash-lite
```

## Live

| Part | URL |
|---|---|
| Chat API (Python Worker) | https://abinaya-chat-api.dentcare-demo.workers.dev (`/api/health`, `/api/health/ready`) |
| Widget + playground | https://abinaya-chatbot.dentcare-demo.workers.dev (`/widget.js`) |
| Website integration | PR [Swethasekar5/Abinayagarment#1](https://github.com/Swethasekar5/Abinayagarment/pull/1) into `develop` |

## Go-live checklist (remaining steps)

1. ~~**Turnstile site key**~~: done. The real site key is in `frontend/.env.production` and deployed. On the
   real website Turnstile accepts the hostname and shows its human check.
2. **Turnstile hostnames:** add `abinaya-chatbot.dentcare-demo.workers.dev` (the playground) to the widget in the
   Cloudflare dashboard. Until then the playground shows Turnstile error 110200 ("domain not authorized"). The
   website hostname is already authorized.
3. **Merge the website PR** ([#1](https://github.com/Swethasekar5/Abinayagarment/pull/1)); Cloudflare Builds
   deploys `develop`.
4. **Verify in a browser:** open the website, ask "Are you open on Sundays?", and watch the answer stream.
5. **Before real production traffic:** switch Gemini to a paid tier (free-tier prompts may be used by Google)
   and have the privacy wording in the PR reviewed.

## Repository

| Path | What |
|---|---|
| [`backend/cloudflare-worker/`](backend/cloudflare-worker) | Public API (Python Worker) + offline knowledge indexer (`indexer/`) + knowledge files (`knowledge/`) |
| [`frontend/`](frontend) | Embeddable widget (`widget.js`) and playground |
| [`docs/`](docs) | Design and operations docs (below) |

| Doc | Contents |
|---|---|
| [architecture.md](docs/architecture.md) | Approved design, compatibility research, **as-built changes** |
| [api-contract.md](docs/api-contract.md) | Endpoints, SSE events, error codes |
| [authentication.md](docs/authentication.md) | Turnstile → session JWT flow |
| [security.md](docs/security.md) | Every security control, rate limits, validation, logging |
| [rag.md](docs/rag.md) | Knowledge rules, chunking, embeddings, Vectorize, retrieval eval, prompt, test answers |
| [deployment.md](docs/deployment.md) | Deploying both apps, secrets, CPU / startup measurements |
| [testing.md](docs/testing.md) | All test layers and how to run them |

## Quick start (local)

```bash
nvm use                                    # Node >= 22.12
cd backend/cloudflare-worker
npm install && uv sync
cp .dev.vars.example .dev.vars             # add GEMINI_API_KEY; generate SESSION_SIGNING_KEY
npx wrangler login                         # Vectorize has no local simulation (remote binding)
uv run pytest                              # 148 backend unit tests
uv run pywrangler dev                      # API on http://localhost:8787

cd ../../frontend && npm install
npm test && npm run dev                    # widget on http://localhost:5173 (Turnstile test key)
```

## Updating the knowledge base

```bash
cd backend/cloudflare-worker
# edit knowledge/*.md (verified facts only; each fact in one file)
uv run python -m indexer chunks                   # check the chunks
uv run --env-file .env python -m indexer embed    # embeds only new or changed chunks
uv run --env-file .env python -m indexer eval     # retrieval quality must stay hit@3 = 100%
uv run python -m indexer sync                     # upload to Vectorize (no Worker redeploy needed)
```

## Environment variables

| App | Name | Kind | Purpose |
|---|---|---|---|
| Worker | `ALLOWED_ORIGINS`, `TURNSTILE_ALLOWED_HOSTNAMES` | var | Website + playground |
| Worker | `SEARCH_TOP_K`=4, `SEARCH_MIN_SCORE`=0.60 | var | Retrieval |
| Worker | `GEMINI_MODEL`, `GEMINI_MAX_OUTPUT_TOKENS`=1024 | var | Generation |
| Worker | `RATE_LIMIT_SESSION_IP`=5, `RATE_LIMIT_CHAT_IP`=20, `RATE_LIMIT_CHAT_SESSION`=8 | var | Per 60 s |
| Worker | `MAX_BODY_BYTES`, `MAX_MESSAGE_CHARS`, `MAX_HISTORY_MESSAGES`, `SESSION_TTL_SECONDS` | var | Limits |
| Worker | `GEMINI_API_KEY`, `TURNSTILE_SECRET_KEY`, `SESSION_SIGNING_KEY` | **secret** | `wrangler secret put` |
| Indexer | `GEMINI_API_KEY` | operator `.env` | Document embeddings |
| Widget | `VITE_API_URL`, `VITE_TURNSTILE_SITE_KEY` | build-time (public) | `frontend/.env.production` |

## Troubleshooting

| Symptom | Likely cause → fix |
|---|---|
| Widget says "We couldn't verify your browser" or "temporarily unavailable" right away | Console shows Turnstile `110200`: the page's hostname isn't in the Turnstile widget → add it in the dashboard |
| `/api/session` returns 500, logs `invalid-input-secret` | `TURNSTILE_SECRET_KEY` is the *site* key or wrong → `wrangler secret put TURNSTILE_SECRET_KEY` (~35 chars) |
| `/api/health/ready` returns 503 | Read the `not_ready` log (`npx wrangler tail abinaya-chat-api`): empty index, missing Gemini key, or model unavailable |
| Browser console shows a CORS error | The page's origin isn't in `ALLOWED_ORIGINS` (exact match, https) |
| 429 "sending messages quickly" | Rate limits per 60 s (see table above) |
| Bot answers "I don't have that information" for a real fact | The fact isn't in `knowledge/` or scores below 0.60 → add or rephrase it, re-run `embed`, `eval`, `sync` |
| Answers stop with no `complete` event | Gemini failed mid-stream (an `error` event is sent); check `stream_failed` logs and Gemini quota |
| Error 1102 in Worker logs | Free-plan CPU limit hit → consider Workers Paid ($5/month) |

## Known limitations

- **Free-plan CPU:** Python requests use 7–50 ms CPU against a documented 10 ms Free limit; all succeeded so far
  (measured), but heavy traffic may see error 1102.
- **Rate limiting:** Cloudflare's Rate Limiting binding never blocks on workers.dev (open Cloudflare issue), so
  exact limits run on a small Durable Object. Limits are per IP and per session; visitors sharing an IP share limits.
- **History is client-side** and can be forged; it's bounded and treated as untrusted by the prompt.
- **Knowledge gaps:** no prices, MOQ numbers, shipping times or return policy are published, so the bot says so.
  Sample phone, stats and the interim WhatsApp number are deliberately excluded.
- **Gemini free tier:** low, unpublished rate limits; prompts may be used to improve Google products.
- **Off-topic filtering** relies mainly on the prompt; the retrieval score gap between relevant (≥ 0.62) and
  off-topic (≤ 0.60) questions is small.

## Monthly cost (demo traffic)

| Service | Cost |
|---|---|
| Cloudflare Workers (API + static widget), Turnstile | $0 on the Free plan ($5/month Paid if CPU limits bite) |
| Vectorize (34 vectors × 768 dims) | $0: ~39k queries/month within the free allowance |
| Durable Objects (rate limiter) | $0 within the Free plan allowance |
| Gemini (free tier) | $0; paid tier ≈ $1–3/month at ~1,000 chats (gemini-3.5-flash-lite) |
| **Total** | **$0–$8/month** |
