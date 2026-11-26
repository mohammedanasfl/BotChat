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
| Live Gemini test | `uv run --env-file .env pytest tests/live` |
| Deploy (Phase 4+) | `uv run pywrangler deploy` |

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

Secrets (added in later phases, never committed): `GEMINI_API_KEY`, `SESSION_SIGNING_KEY`,
`TURNSTILE_SECRET_KEY`.
