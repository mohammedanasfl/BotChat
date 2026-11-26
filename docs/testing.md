# Testing

## Frontend (`frontend`)

| Layer | Command / method | What it covers |
|---|---|---|
| Unit (vitest + jsdom) | `npm test` | SSE parser, streaming client with mocked fetch, ApiError codes, session caching / early renewal / concurrency, error messages |
| Browser vs local Worker | `npm run dev` + `uv run pywrangler dev` | Turnstile (test key) → session → streamed answers, follow-up questions, host-page CSS isolation (`* { color: red !important }` had no effect), double include gives one element, mobile full-screen layout |
| Browser vs production | https://abinaya-chatbot.dentcare-demo.workers.dev | widget loads, Turnstile runs, cross-origin session request reaches the API (CORS ok); with the test site key the API answers 403 and the widget shows its error message |

## Backend (`backend/cloudflare-worker`)

| Layer | Command | What it covers |
|---|---|---|
| Unit (CPython, no network) | `uv run pytest` | 154 tests: settings, routing, errors, CORS, auth (JWT incl. PyJWT interop, Turnstile outcomes), rate limits (Durable Object counter), validation, retrieval, prompt building, Gemini stream parsing, follow-up questions, SSE event contract, disconnects, chunking, embeddings, Vectorize records |
| Live Gemini | `uv run --env-file .env pytest tests/live` | Real embeddings: a related text scores higher than an unrelated one |
| Retrieval quality | `uv run --env-file .env python -m indexer eval` | 20 labelled questions: hit@1 81%, hit@3 100%, score cutoff 0.60 |
| Runtime smoke (local) | `uv run pywrangler dev`, then `uv run python tests/runtime/smoke.py` | Real Workers runtime: health, ready, origin 403, 401, 413, session via test Turnstile key, 422, **streaming SSE event order**, grounded answer |
| Runtime smoke (production) | `uv run python tests/runtime/smoke.py https://abinaya-chat-api.dentcare-demo.workers.dev` | Health, ready, CORS for the website origin, origin 403, 401, 413, fake Turnstile token gives 403 (proves the real secret works) |
| Lint | `uv run ruff check . && uv run ruff format --check .` | Includes `F821` (undefined names), which matters because `main.py` only runs inside the Workers runtime |

### Verified manually during development

- **Rate limits in production:** 25 fast unauthenticated chats gave `401` ×20 then `429`; 7 sessions gave `403` ×5
  then `429` (docs/security.md).
- **Streaming:** `start` → 6 `token` events over ~160 ms → `complete` (local runtime); a visitor disconnect
  aborts Gemini and logs `client_disconnected`.
- **RAG answers:** 15-question set incl. unanswerable, off-topic, prompt-injection, follow-up and Tamil (docs/rag.md).
- **CPU / startup:** chat median 13 ms CPU, Durable Object calls 2 ms, startup ~550 ms (docs/deployment.md).

### Not testable from the command line

A production **session** needs a real Turnstile token, which only the browser widget can produce. The full
production flow (Turnstile → session → streaming chat) is verified in the browser in Phases 15–16.

## End-to-end failure matrix (Phase 17)

| Scenario | Result | Where verified |
|---|---|---|
| Widget loads on the real website | Mounted bottom-right; site CSS, fonts and links unchanged; uses the site's Fraunces font | Browser, real website (script injected as in the PR) |
| Turnstile on the real hostname | Widget runs Turnstile; session request reaches the API from the website origin (CORS ok) | Browser, real website |
| Valid Turnstile → session → streamed answer | `start` → `token`* → `complete`, grounded answer | Local runtime + browser (test keys); production pending the real site key |
| Invalid Turnstile token | `403 turnstile_failed` | Production |
| Expired session | `401 session_expired`, widget renews silently | Local runtime, unit tests |
| Missing or forged authorization | `401 unauthorized` | Production |
| Invalid origin | `403 forbidden_origin` | Production |
| Excessive requests | `429` + `Retry-After: 60` (IP and session limits) | Production (IP), local (session) |
| Empty knowledge index | `/ready` returns 503 `not_ready`, reason logged | Unit tests |
| Irrelevant questions | No chunks above 0.60; polite refusal | Local runtime (15-question set) |
| Gemini failure | Before streaming: JSON 503; during: `error` event | Unit tests (both paths) |
| Vectorize failure | Upstream error gives JSON 503 | Unit tests |
| Network disconnection | Gemini aborted via `request.signal`, `client_disconnected` logged | Local runtime |
| Large input | `413` before the body is read (production); message > 1,000 chars gives `422` | Production, unit tests |
| Prompt injection | Refused, stays in role, no prompt leak | Local runtime |
