# abinaya-chat-api: Cloudflare Python Worker

Public chat API for the Abinaya Garments chatbot. See [docs/architecture.md](../../docs/architecture.md)
and [docs/api-contract.md](../../docs/api-contract.md).

## Layout

```text
src/                 # bundled into the Worker (src/ is the import root)
  main.py            # runtime adapter: Cloudflare Request -> dispatch() -> Cloudflare Response
  app.py             # pure dispatch + top-level error handling
  routes/            # route table (__init__.py) and handlers
  core/              # errors, JsonResult, request context, structured logging
  config/            # settings.py (typed env parsing), embedding.py (shared with indexer)
indexer/             # offline knowledge indexer CLI (never bundled), see docs/rag.md
knowledge/           # verified business knowledge (markdown)
tests/unit/          # pytest on CPython, no runtime imports
```

**Rule:** only `main.py` (and later the binding/HTTP adapters) may import `workers` / `js`.
Everything else must run under plain `pytest`.

## Setup

```bash
nvm use                       # Node >= 22.12 (see /.nvmrc)
npm install                   # project-local wrangler
uv sync                       # Python tooling (needs uv >= 0.13.4 for pywrangler)
cp .dev.vars.example .dev.vars
```

## Commands

| Task | Command |
|---|---|
| Unit tests | `uv run pytest` |
| Lint / format | `uv run ruff check . && uv run ruff format --check .` |
| Local Workers runtime | `uv run pywrangler dev` → http://localhost:8787 |
| Health check | `curl -i http://localhost:8787/api/health` |
| Chunk report | `uv run python -m indexer chunks` |
| Embed knowledge | `uv run --env-file .env python -m indexer embed` |
| Retrieval eval | `uv run --env-file .env python -m indexer eval` |
| Upload to Vectorize | `uv run python -m indexer sync` (after `npx wrangler login`) |
| Live Gemini test | `uv run --env-file .env pytest tests/live` |
| Deploy | `uv run pywrangler deploy` (see docs/deployment.md) |
| Local session + chat | `curl -X POST localhost:8787/api/session -d '{"turnstile_token":"test"}'`, then `curl -X POST localhost:8787/api/chat -H 'Authorization: Bearer <token>' -d '{"message":"Open on Sunday?"}'` |

## Configuration

Production values live in `vars` in [`wrangler.jsonc`](wrangler.jsonc). Locally, `.dev.vars`
overrides them (and will hold secrets). Every value is parsed and validated in
[`src/config/settings.py`](src/config/settings.py); an invalid value returns a generic
`500 internal_error` to clients and logs a `config_error` event.

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `production` | `development` or `production` |
| `ALLOWED_ORIGINS` | none | Comma-separated exact origins; https required in production |
| `MAX_BODY_BYTES` | 32768 | |
| `MAX_MESSAGE_CHARS` | 1000 | |
| `MAX_HISTORY_MESSAGES` | 10 | |
| `SESSION_TTL_SECONDS` | 900 | |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | |
| `GEMINI_MAX_OUTPUT_TOKENS` | 1024 | Includes thinking tokens |
| `SEARCH_TOP_K` | 4 | |
| `SEARCH_MIN_SCORE` | 0.60 | Calibrated with `indexer eval` (docs/rag.md) |
| `RATE_LIMIT_SESSION_IP` / `RATE_LIMIT_CHAT_IP` / `RATE_LIMIT_CHAT_SESSION` | 5 / 20 / 8 | Requests per 60 s (docs/security.md) |

Bindings: `VECTORIZE` → `abinaya-kb` (`remote: true` so local dev uses the real index); `RATE_LIMITER`
→ `RateLimiter` Durable Object (`src/durable/rate_limiter.py`).

Secrets (never committed; `.dev.vars` locally, `wrangler secret put` in production): `GEMINI_API_KEY`,
`TURNSTILE_SECRET_KEY`, `SESSION_SIGNING_KEY`. See docs/authentication.md.
