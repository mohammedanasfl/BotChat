# Abinaya Garments AI Chatbot

An embeddable, RAG-grounded, streaming AI chatbot for the
[Abinaya Garment Shop website](https://abinayagarment.dentcare-demo.workers.dev/).

| App | Path | Runtime | Status |
|---|---|---|---|
| Public API + RAG | [`backend/cloudflare-worker`](backend/cloudflare-worker) | Cloudflare Python Worker + Vectorize + Gemini | Phase 1 (foundation) |
| Knowledge indexer (operator CLI) | [`backend/cloudflare-worker/indexer`](backend/cloudflare-worker/indexer) | CPython, offline | Skeleton (Phase 2) |
| Chat widget + playground | `frontend/` | React + TypeScript + Vite on Cloudflare Pages | Phase 10+ |

## Documentation

- [Architecture](docs/architecture.md): approved Phase 0 design, risks and phase plan
- [API contract](docs/api-contract.md): public endpoints, SSE events, error codes

## Prerequisites

- Node.js ≥ 22.12 (`nvm use` reads [`.nvmrc`](.nvmrc))
- [uv](https://docs.astral.sh/uv/) ≥ 0.9.28
- Python 3.14 (uv installs it if missing)

## Quick start

```bash
cd backend/cloudflare-worker
npm install            # project-local wrangler
uv sync                # Python tooling + test deps
uv run pytest          # unit tests
uv run pywrangler dev  # local Workers runtime on http://localhost:8787
```

See [`backend/cloudflare-worker/README.md`](backend/cloudflare-worker/README.md) for details.
