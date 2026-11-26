# Architecture — Abinaya Garments AI Chatbot

> Approved Phase 0 report (2026-11-26). The API contract lives in [api-contract.md](api-contract.md).

## Context

We are building an embeddable, RAG-grounded, streaming AI chatbot for the Abinaya Garment Shop website
(`https://abinayagarment.dentcare-demo.workers.dev/`, source `github.com/Swethasekar5/Abinayagarment`, branch
`develop`). Visitors are anonymous; abuse protection = Cloudflare Turnstile + short-lived HMAC-SHA256 session tokens
+ rate limits.

**Architecture change agreed during Phase 0:** you asked for no separate container — vector search must live inside
the chatbot's own Python project. Native FAISS cannot run in a Cloudflare Python Worker (C++ library, no Pyodide /
WebAssembly build), so you chose **Cloudflare Vectorize** (managed vector index, queried from the Python Worker via a
binding). Consequences:
- The separate FastAPI + FAISS service, its Docker image and its hosting are **removed**.
- Two deployable apps remain: the **Python Worker** (public API + RAG) and the **React widget** (Cloudflare Pages).
- Knowledge processing (chunking + document embeddings) runs as an **offline operator CLI** inside the Worker
  project (`indexer/`), never deployed. It replaces `POST /admin/reindex`; its admin credential is a scoped Cloudflare
  API token (Vectorize Write) that exists only on the operator's machine.


---

## 1. Inspection results

### Chatbot repo — `/Users/anas/Documents/chatBot`
Empty, not a git repository. Phase 1 runs `git init` and creates the monorepo.

### Local toolchain
| Tool | Found | Required / action |
|---|---|---|
| Python | 3.14.7 default, 3.11 (Homebrew) | Worker runtime is **Python 3.14 (Pyodide)** → local 3.14 matches for unit tests and the indexer CLI |
| uv | 0.12.10 | ≥ 0.9.28 needed by `pywrangler` ✅ |
| Node / npm | **20.20.2** / 10.8.2 | ❌ Wrangler 4.16x needs **Node ≥ 22.12** → Phase 1: `nvm install 22` (also satisfies Vite 7) |
| Wrangler | not global | Project-local via `pywrangler` (Worker) and `npx wrangler` (Pages, Vectorize CLI) |
| Docker | 29.8.2 | No longer required |
| git / gh | 2.54 / 2.95 | ✅ |

### Existing website (`develop`, 10 commits ahead of `master`)
- Astro 5 static site deployed as a **Cloudflare Worker with static assets** (`wrangler.jsonc`, Cloudflare Builds
  from `develop`). No CSP header or meta → external `widget.js` and the Turnstile iframe load without changes.
- **Integration point (Phase 16):** `src/layouts/SiteLayout.astro` — add `<script is:inline src=… defer>` before
  `</body>`, as a PR to `develop`.
- **Business data available:** `src/data/products.json` (12 products: name, description, category, fabric, sizes,
  colours — **no prices**), `src/data/site.ts` (name, address, email, hours, reply time), page copy (who we are,
  why us, yarn→dispatch process, 160–280 GSM, who we supply), `privacy.astro`.
- **Marked NOT verified in the source itself:** `stats` (30 years, 2.5L pieces/month, 420+ partners, 22 states) —
  "SAMPLE figures for the design"; phone `+91 98765 43210` — "a sample value"; WhatsApp — "interim". Excluded from
  the knowledge base unless you confirm them during the Phase 2 review.
- No pricing, MOQ, payment, shipping, returns or lead-time information exists → `pricing.md` / `policies.md` stay
  minimal; the bot will say it doesn't have that information and point to verified contact channels.

---

## 2. Technology compatibility report

| Area | Verdict | Key facts (official docs, Nov 2026) |
|---|---|---|
| **Cloudflare Python Workers** | ✅ GA (2026-09-21) | `pywrangler` (uv-based), `wrangler.jsonc` with `compatibility_flags: ["python_workers"]`, Python 3.14 / Pyodide. `from workers import WorkerEntrypoint, Response, fetch`. Only `[project].dependencies` are bundled — dev/indexer groups are not. |
| **Outbound HTTPS** | ✅ | `workers.fetch`; upstream body is a JS `ReadableStream`, iterable with `async for chunk in resp.body`. |
| **SSE streaming from Python** | ✅ with a specific pattern | Return `Response(ts.readable, headers=…)` from a `TransformStream`; a background task writes SSE frames with `writer.write()` while reading Gemini's stream, kept alive with `wait_until`. Python async generators are **not** accepted directly. No wall-clock limit while the client stays connected. |
| **Client disconnect** | ✅ compat date ≥ 2026-11-17 | `request.signal` fires `abort` → we abort the Gemini fetch to stop token spend. |
| **Cloudflare Vectorize** | ✅ GA, ⚠️ Free-plan wording conflicts | Binding from Python verified by official `python-workers-examples/vectorize-rag` (`await self.env.VECTORIZE.query(vec, {"topK": 4, "returnMetadata": "all"})`, plain dicts). Max **1,536 dims** (so 768 ✅, 3072 ❌), metadata ≤ 10 KiB/vector, IDs ≤ 64 bytes, topK ≤ 50 with metadata, upsert ≤ 1,000/batch from Workers or 5,000 via REST. Mutations are async ("a few seconds"). Metrics set at creation (`--dimensions 768 --metric cosine`). **No local simulation** → dev uses `"remote": true` binding against a real (dev) index. Free allowance: 30M queried dims + 5M stored dims/month; queried dims = (queries + stored vectors) × dims → ~100 chunks × 768 ≈ **39k queries/month free**. Vectorize pricing page says Free tier included; Workers pricing page says "only available on the Workers paid plan" → verified empirically in Phase 3. |
| **Rate Limiting binding** | ✅ from Python (SDK test-verified) | `await env.LIMITER.limit({"key": k})` → `.success`. Period 10 s or 60 s; **approximate, per-location, eventually consistent**. |
| **Durable Objects (Python)** | ✅ | `class X(DurableObject)` with SQLite — option for a strict daily budget guard. |
| **Stdlib crypto** | ✅ | `hmac`, `hashlib`, `secrets`, `base64`, `json`, `time` available. No randomness at module top level (memory snapshot) — only in handlers. `time.time()` likely frozen during CPU execution (fine for second-level expiry). |
| **Workers limits** | ⚠️ Free-plan risk | Free: **10 ms CPU/request**, 50 subrequests, 100k req/day. Paid ($5/mo): 30 s CPU. I/O wait doesn't count. Per-chunk Python processing during streaming may exceed 10 ms → error 1102. Decision: start Free, measure. |
| **Turnstile** | ✅ | Siteverify `POST challenges.cloudflare.com/turnstile/v0/siteverify` (`secret`, `response`, `remoteip`, `idempotency_key`) → `success, hostname, action, challenge_ts, error-codes`. Tokens valid 300 s, single-use. Dummy test keys (`1x00000000000000000000AA` / `1x0000000000000000000000000000000AA`). ≤ 10 hostnames per widget (Free). |
| **Turnstile + Shadow DOM** | ⚠️ not officially supported | Turnstile looks up elements on `document`. **Workaround:** Turnstile container is a light-DOM child of our custom element, projected via `<slot>`. |
| **Gemini embeddings** | ✅ `gemini-embedding-001` (as agreed) | Not deprecated (earliest shutdown May 2028). `outputDimensionality=768`; `RETRIEVAL_DOCUMENT` (+`title`) for chunks, `RETRIEVAL_QUERY` for questions; 2,048 input tokens. Non-3072 outputs aren't unit-length — Vectorize `cosine` metric makes scores magnitude-independent. Docs disagree on REST field placement (`embedContentConfig` vs top-level) → confirmed with a live call in Phase 2. |
| **Gemini generation** | ✅ | **`gemini-3.5-flash-lite`** (stable, no shutdown date, $0.30/$2.50 per 1M tokens, thinking defaults to `minimal`). ⚠️ `gemini-2.5-flash` auto-retires Dec 1, 2026. REST `v1beta/models/{model}:streamGenerateContent?alt=sse`, header `x-goog-api-key`, `systemInstruction`, `maxOutputTokens` (**includes thinking tokens**), `thinkingConfig.thinkingLevel="minimal"`. Raw SSE framing not shown in current docs → defensive parser + recorded fixtures. |
| **google-genai SDK** (indexer only) | ✅ 3.6.1 | Python ≥ 3.11; `client.models.embed_content(..., config=EmbedContentConfig(task_type, output_dimensionality))`. |
| **Cloudflare Pages** | ✅ supported, de-emphasized | Cloudflare recommends Workers static assets for new projects, but Pages fully supports a Vite build. **Keeping Pages as agreed**; Workers static assets is the fallback. |
| **FAISS** | ❌ in Worker | No Pyodide build; replaced by Vectorize (decision above). |

---

## 3. Architecture

```
┌────────────────────────────── Visitor browser ──────────────────────────────┐
│ abinayagarment.dentcare-demo.workers.dev  (Astro static site)              │
│   <script src="https://<pages>/widget.js" data-api-url data-site-key defer>│
│     <abinaya-chat> custom element                                          │
│       ├─ Shadow DOM: React chat UI (isolated CSS)                          │
│       ├─ light-DOM <slot> child: Turnstile widget                          │
│       └─ fetch() POST + streaming SSE reader (EventSource can't POST)     │
└──────────────┬──────────────────────────────────────────▲─────────────────┘
   widget.js / │ playground (static)                      │ text/event-stream
┌──────────────▼───────────┐                              │
│ Cloudflare Pages         │        POST /api/session     │
│ frontend/ build          │        POST /api/chat        │
└──────────────────────────┘                              │
┌─────────────────────────────────────────────────────────┴─────────────────┐
│ Cloudflare Python Worker  (backend/cloudflare-worker/src)                 │
│  CORS/origin → body limit → Turnstile verify | JWT verify → rate limits   │
│  → validate → embed query → Vectorize query → prompt → Gemini stream → SSE│
│  Bindings: VECTORIZE (abinaya-kb), rate limiters (+ optional DO budget)   │
│  Secrets: TURNSTILE_SECRET_KEY, SESSION_SIGNING_KEY, GEMINI_API_KEY       │
└───┬──────────────────┬───────────────────────┬──────────────────┬─────────┘
    │ siteverify       │ embedContent          │ binding          │ streamGenerateContent?alt=sse
┌───▼──────────┐ ┌─────▼─────────────────┐ ┌───▼──────────────┐ ┌─▼──────────────────────┐
│ Turnstile    │ │ Gemini                │ │ Vectorize index  │ │ Gemini                 │
│ siteverify   │ │ gemini-embedding-001  │ │ 768 dims, cosine │ │ gemini-3.5-flash-lite  │
└──────────────┘ │ RETRIEVAL_QUERY, 768  │ │ chunk text+meta  │ └────────────────────────┘
                 └───────────────────────┘ └───▲──────────────┘
                                               │ REST upsert / delete (Vectorize Write token)
                           ┌───────────────────┴─────────────────────────────────────┐
                           │ Operator machine: indexer CLI (backend/cloudflare-worker/ │
                           │ indexer, CPython, not deployed)                           │
                           │ knowledge/*.md → normalize → chunk → embed (Gemini,       │
                           │ RETRIEVAL_DOCUMENT, 768) → upsert changed, delete stale   │
                           └───────────────────────────────────────────────────────────┘
```

**Key design choices**
1. **One backend project.** Runtime code in `src/` (bundled to the Worker); offline indexer in `indexer/` (same
   project, same uv environment, never bundled). Embedding settings come from **one shared module**
   (`src/config/embedding.py`) imported by both, so documents and queries always use the same model/dimensions.
2. **Mismatch guard:** each vector's metadata records `embedding_model` and `dimensions`; the Worker's readiness check
   compares `VECTORIZE.describe()` dimensions with its config and the query path rejects matches embedded with a
   different model — prevents silently mixing embedding configurations.
3. **No web framework in the Worker** — a plain `WorkerEntrypoint.fetch` with a small route table (lower cold start
   and CPU than FastAPI under Workers CPU limits).
4. **Pure core + thin runtime adapters.** Everything except `main.py` and the binding/HTTP adapters avoids importing
   `js`/`workers`, so token, validation, prompt, CORS, chunking and SSE logic run under plain pytest on CPython 3.14;
   runtime behaviour is tested against `pywrangler dev` and the deployed Worker.
5. **No application database.** Conversation history lives in the browser and is sent (bounded) with each request.
6. **Separate dev and prod indexes** (`abinaya-kb-dev`, `abinaya-kb`), because local dev uses remote bindings.

### Responsibilities
| Part | Owns | Never owns |
|---|---|---|
| Frontend widget | UI, Turnstile token, session token (memory + sessionStorage), history, SSE parsing, cancel | Secrets, business data |
| Worker (`src/`) | Origin/CORS, Turnstile, JWT issue/verify, rate limits, validation, query embedding, Vectorize query, prompt, Gemini streaming, SSE contract | Document embedding, index writes |
| Indexer CLI (`indexer/`) | Knowledge loading, normalization, chunking, metadata, document embeddings, upsert/delete, manifest | Anything visitor-facing |
| Vectorize | Persistent vector storage + similarity search | Business logic |

---

## 4. Request flows

### A. Initial visit
Website loads `widget.js` (deferred, from Pages) → registers `<abinaya-chat>` once (guarded against double include)
→ launcher rendered. The Turnstile script loads only when the visitor first opens the chat.

### B. Session creation
1. Visitor opens chat → Turnstile (Managed mode; most humans pass without interaction), `action="chat_session"`.
2. `POST /api/session {turnstile_token}`.
3. Worker: origin allowlist → per-IP session limit → siteverify (`remoteip` = `CF-Connecting-IP`, `idempotency_key`)
   → require `success`, `hostname ∈ TURNSTILE_ALLOWED_HOSTNAMES`, `action == "chat_session"`.
4. Worker issues JWT HS256 `{iss, aud, sub=session_id, jti, iat, exp=iat+900}` → `{session_token, expires_in, expires_at}`.
5. Widget stores it in memory + sessionStorage (survives page navigation; cleared with the tab).

### C. Chat message
1. `POST /api/chat`, `Authorization: Bearer <jwt>`, `{message, history, conversation_id}`.
2. Worker: origin → body ≤ 32 KB → JWT verify (alg pinned, signature, iss, aud, exp) → per-IP + per-session limits →
   schema validation.
3. Worker → Gemini `embedContent` (`gemini-embedding-001`, `RETRIEVAL_QUERY`, 768) for the search query (latest
   message; short follow-ups prepend the previous user message).
4. Worker → `VECTORIZE.query(vector, {topK: 4, returnMetadata: "all"})` → drop matches below `MIN_SCORE` or with a
   mismatched `embedding_model`.
5. Worker builds the prompt: `systemInstruction` (rules) + bounded history (`user`/`model`) + final user turn with
   `<reference_data>[1] (products.md › Polo T-Shirts) …</reference_data>` and `<visitor_question>…</visitor_question>`.
6. Worker calls Gemini streaming (`maxOutputTokens` cap, `thinkingLevel=minimal`, no automatic retries) and re-emits
   `start` → `token`* → `complete | error`. Visitor disconnect aborts the Gemini fetch.
7. Widget renders tokens incrementally; Stop button aborts the fetch.

### D. Session renewal
~60 s before `exp`, or on `401 session_expired`: `turnstile.reset()` → new (usually invisible) Turnstile token →
`POST /api/session` → retry once. No refresh-token endpoint — Turnstile stays the only way to obtain a session.

### E. Knowledge update (operator)
Edit `knowledge/*.md` → `uv run --group indexer python -m indexer reindex --env dev` → chunk, hash, embed **only
new/changed chunks**, upsert, delete stale ids, write `knowledge/index-manifest.json` → `python -m indexer query
"…"` to verify → repeat with `--env prod`. No redeploy of the Worker is needed for content changes.

---

## 6. Security design

- **Turnstile:** public site key in the widget; secret only in Worker secrets; every token verified via siteverify;
  `hostname` and `action` checked; idempotency key guards retries. Dev/test uses Cloudflare's dummy keys.
- **Session token = standard JWT (RFC 7519) signed with HS256** — not a custom format. Header
  `{"alg":"HS256","typ":"JWT","kid":"v1"}` (`kid` enables key rotation). Claims `iss`, `aud`, `sub` (session id),
  `jti`, `iat`, `exp`. Verification pins `alg=HS256` (rejects `none`/others), uses `hmac.compare_digest`, checks
  `iss`, `aud`, `exp`, `iat` with ≤ 30 s leeway. Implemented with stdlib (`hmac`, `hashlib`, `base64`, `json`) so the
  Worker stays dependency-free; tests cross-check against **PyJWT** (dev dependency) plus tamper cases.
- **Origin/CORS:** exact allowlist (`ALLOWED_ORIGINS`), no wildcard, preflight handled, disallowed `Origin` rejected.
  Documented as defense-in-depth, not authentication.
- **Index writes:** the Worker has a Vectorize binding but **no code path that writes** to it; writes happen only from
  the operator CLI with a scoped Cloudflare API token. No administrative secret exists in the Worker or frontend.
- **Rate limits (Phase 7):** Rate Limiting bindings — session creation per IP (e.g. 5/60 s), chat per IP (20/60 s),
  chat per session (8/60 s), readiness per IP. Since bindings are approximate and per-location, Phase 7 will propose
  a small Python Durable Object as a strict **daily budget guard** to cap Gemini spend.
- **Gemini protection:** limits above + message/history caps + `maxOutputTokens` + timeouts + no automatic retries.
- **Prompt-injection posture:** retrieved chunks and history are delimited and labelled untrusted; the system
  instruction forbids following embedded instructions, revealing prompts/credentials, or stating facts absent from
  reference data. Client-supplied history can be forged (no DB) — bounded and treated as untrusted; documented.
- **Logging:** request id, route, status, latency, token counts, rate-limit hits; never tokens, secrets, full message
  bodies or raw IPs.
- **Secrets:** `.dev.vars` / `.env` git-ignored, `*.example` committed, `wrangler secret put` in production. Separate
  Gemini API keys for Worker and indexer (independent revocation).
- **Gemini free tier:** prompts may be used by Google to improve products → widget shows a short privacy note;
  switch to paid before real production use.

---

## 7. RAG design

- **Knowledge files** (`backend/cloudflare-worker/knowledge/`): `company.md`, `products.md`, `services.md`,
  `pricing.md`, `policies.md`, `faqs.md` — drafted only from verified website content (sample stats/phone excluded),
  reviewed by you before indexing.
- **Chunking:** heading-aware Markdown splitting (H1/H2/H3); sections > ~1,000 chars split on paragraph boundaries
  with ~150-char overlap. Embedded text = `"{doc title} › {section path}\n\n{chunk}"`, `title` param set.
- **Chunk ids:** `{doc_stem}-{nnn}` + `content_sha256`; the manifest maps ids → hashes so unchanged chunks are never
  re-embedded and removed chunks are deleted from the index.
- **Embeddings:** `gemini-embedding-001`, 768 dims (configurable ≤ 1,536 — Vectorize's limit — in one shared module;
  changing it requires recreating the index + full reindex), `RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`.
- **Retrieval:** `TOP_K=4`, `MIN_SCORE` calibrated in Phase 3 from ~20 labelled realistic questions (incl.
  unanswerable ones).
- **Unknown answers:** if nothing passes `MIN_SCORE`, Gemini is still called with an empty reference block (so it can
  greet/decline politely); a pinned verified "contact" chunk from `company.md` is always included so the bot points
  to real contact channels instead of inventing them.
- **Empty index:** readiness reports not-ready; `/api/chat` returns `503 upstream_unavailable` before streaming.

---

## 8. Repository structure

Root is this folder. Changes vs. your suggested layout are marked ★ with reasons.

```text
chatBot/
├── backend/
│   └── cloudflare-worker/
│       ├── src/                       # bundled into the Worker
│       │   ├── main.py                # WorkerEntrypoint + route table (runtime-bound)
│       │   ├── routes/                # health.py, session.py, chat.py
│       │   ├── middleware/            # cors.py, auth.py, rate_limit.py, limits.py
│       │   ├── services/              # tokens.py (JWT), turnstile.py, embeddings.py (query), retrieval.py
│       │   │                          # (Vectorize), gemini_client.py, gemini_sse.py (parser), http.py
│       │   ├── prompts/               # system_prompt.py, builder.py
│       │   ├── core/                  # ★ errors.py, sse.py, validation.py — pure helpers
│       │   └── config/                # settings.py (env → typed dataclass), embedding.py (shared constants)
│       ├── indexer/                   # ★ replaces faiss-service: offline CLI, NOT bundled
│       │   ├── __main__.py            # chunks / reindex / query / eval commands
│       │   ├── loader.py, chunker.py, embedder.py, vectorize_api.py, manifest.py
│       ├── knowledge/                 # company.md … faqs.md, index-manifest.json, eval_questions.json
│       ├── tests/
│       │   ├── unit/                  # pytest on CPython 3.14 (no runtime imports)
│       │   └── runtime/               # HTTP tests vs `pywrangler dev` and the deployed URL
│       ├── pyproject.toml             # deps: none at runtime; groups: dev, indexer (google-genai, httpx)
│       ├── wrangler.jsonc             # ★ jsonc: format used by official Python Worker examples
│       ├── .dev.vars.example, .env.example
│       └── README.md
├── frontend/                          # Phase 10+ (React + TS + Vite; playground + IIFE widget builds)
├── docs/                              # architecture.md, api-contract.md, authentication.md, rag.md,
│                                      # deployment.md, testing.md
├── .gitignore
└── README.md
```
★ Removed: `backend/faiss-service/` (FastAPI, Dockerfile, `storage/`) — superseded by Vectorize + `indexer/`.

---

## 9. Dependencies & configuration

| Part | Dependencies |
|---|---|
| Worker runtime | **none** beyond stdlib + `workers` runtime module (keeps CPU/cold start low) |
| Dev group | `workers-py` (pywrangler), `workers-runtime-sdk` (types), `pytest`, `pytest-asyncio`, `httpx`, `PyJWT` (test cross-check), `ruff` |
| Indexer group | `google-genai>=3.6`, `httpx` |
| Frontend (Phase 10) | `react`, `react-dom`; dev: `typescript`, `vite`, `@vitejs/plugin-react`, `vitest`, `@testing-library/react`, `jsdom` (Turnstile via `api.js?render=explicit`, no wrapper lib) |

**Worker vars:** `ENVIRONMENT`, `ALLOWED_ORIGINS`, `TURNSTILE_ALLOWED_HOSTNAMES`, `TURNSTILE_ACTION`,
`SESSION_TTL_SECONDS=900`, `TOKEN_ISSUER`, `TOKEN_AUDIENCE`, `SEARCH_TOP_K=4`, `SEARCH_MIN_SCORE`,
`GEMINI_MODEL=gemini-3.5-flash-lite`, `GEMINI_MAX_OUTPUT_TOKENS=1024`, `MAX_MESSAGE_CHARS`, `MAX_HISTORY_MESSAGES`,
`MAX_BODY_BYTES`, upstream timeouts. **Secrets:** `TURNSTILE_SECRET_KEY`, `SESSION_SIGNING_KEY`, `GEMINI_API_KEY`.
**Bindings:** `VECTORIZE` (`abinaya-kb-dev` with `remote: true` in dev env, `abinaya-kb` in prod), rate limiters.

---

## 10. Risks & limitations

| # | Risk | Mitigation |
|---|---|---|
| 1 | **Free plan 10 ms CPU** may be exceeded by Python (error 1102) | No runtime deps; measure CPU (`wrangler tail` / dashboard) in Phases 4 and 8; Workers Paid ($5/mo) only with your approval |
| 2 | **Vectorize on Free plan** — Cloudflare docs contradict each other | Phase 3 first step: `wrangler vectorize create` on your account. If it requires Paid, I stop and ask (options: $5/mo Paid, or bundled NumPy search) |
| 3 | Vectorize max 1,536 dims | 768 dims (Gemini-recommended size) |
| 4 | No local Vectorize simulation | `remote: true` binding to a separate dev index; requires `wrangler login` (you run it) |
| 5 | Vectorize mutations are async (seconds) | Indexer waits for the mutation before verification queries |
| 6 | Node 20.20.2 < Wrangler's Node ≥ 22.12 | `nvm install 22` in Phase 1 |
| 7 | Turnstile doesn't support Shadow DOM | Light-DOM slotted container, verified on the real hostname in Phase 12/16 |
| 8 | Rate Limiting binding is approximate/per-location | Burst protection; strict daily budget via Durable Object (Phase 7 proposal) |
| 9 | Gemini free tier: low/unpublished limits; data used for product improvement; EEA/UK users require paid | Check limits in AI Studio; privacy note; paid tier before production |
| 10 | Gemini model churn (`gemini-2.5-flash` retires Dec 1 2026) | Model ID is config; stable `gemini-3.5-flash-lite` |
| 11 | `maxOutputTokens` includes thinking tokens | `thinkingLevel=minimal`; surface `max_tokens`; tune in Phase 8 |
| 12 | Raw Gemini SSE framing not in current docs; embed REST field placement ambiguous | Defensive parser + recorded fixtures; live call in Phase 2 |
| 13 | Extra latency: query embedding call before generation (~100–300 ms) | Accepted; measured in Phase 5 |
| 14 | Randomness at module top level breaks Python Worker deploy | IDs/nonces only inside handlers |
| 15 | Client-side history can be forged | Bounded, untrusted, system-prompt rules; documented |
| 16 | Missing business facts (prices, policies, MOQ) | Bot says "not available" + verified contact; you can add content later and reindex |
| 17 | Cloudflare account access (Worker, Vectorize, Turnstile, Pages); `wrangler login` is interactive | You run `wrangler login`; using the same account as `dentcare-demo.workers.dev` keeps hostnames simple |
| 18 | Website integration needs a PR to `Swethasekar5/Abinayagarment` `develop` | Push access or fork PR (Phase 16) |
| 19 | Pages is de-emphasized by Cloudflare | Still supported; Workers static assets is a drop-in fallback |
| 20 | Vendor lock-in to Cloudflare for vector search (vs portable FAISS) | Retrieval behind one `retrieval.py` interface; index rebuildable from markdown at any time |

---

## 11. Phase-by-phase execution plan

Every phase follows your loop: explain → approve → implement → test → show results → manual verification → commit suggestion.

| Phase | Scope | Deliverable / verification |
|---|---|---|
| **1** Foundation | `git init`, Node 22, monorepo, Worker project via pywrangler (uv), settings module, `.example` env files, `GET /api/health`, indexer package skeleton, docs from Phase 0 | `uv run pywrangler dev` → `curl :8787/api/health` 200; pytest green; `chore: initialize chatbot monorepo` |
| **2** Knowledge & embeddings | Draft 6 knowledge files from verified website content (you review), loader, normalizer, chunker, metadata, Gemini embedding client (768), `indexer chunks` | Chunk report; unit tests; one live embed call confirming dims; `feat: add business document chunking` + `feat: implement Gemini embeddings` |
| **3** Vectorize index | Verify Vectorize on your plan, create dev/prod indexes (768, cosine) + metadata index, `reindex` (incremental + stale delete + manifest), `query`, `eval`, calibrate `MIN_SCORE` | `indexer query "custom logo printing"` returns the expected chunks; eval hit-rate report; `feat: add Vectorize knowledge index` |
| **4** Worker foundation | Router, settings, CORS, error envelope, `http.py`, Gemini connectivity, query embedding, Vectorize binding retrieval, `/api/health/ready` | Tested in local workerd (remote binding) **and** first deploy to `*.workers.dev`; CPU-time measurement |
| **5** RAG integration | Context construction, system prompt, grounded non-streaming answer (internal), unknown-answer handling, sources | Realistic question set incl. unanswerable and injection prompts, results shown; `feat: integrate RAG with Cloudflare Worker` |
| **6** Authentication | Siteverify, hostname/action checks, JWT issue/verify, auth middleware | Valid/invalid/expired/modified/missing token tests; dummy Turnstile keys pass/fail; `feat: implement Turnstile session authentication` |
| **7** Rate limiting & security | Rate Limiting bindings, size/history/output limits, safe errors, usage logging, optional DO budget guard | Deployed burst test → 429 + `Retry-After`; oversize → 413/422 |
| **8** Streaming chat | `/api/chat` SSE via TransformStream, Gemini stream parser, cancellation via `request.signal`, timeouts | `curl -N` against the **deployed** Worker shows incremental tokens; disconnect aborts upstream; `feat: add SSE chat streaming` |
| **9** Backend tests & deploy | Full unit + runtime suites (auth, RAG, retrieval, rate limits, streaming, invalid/expired), prod index build, prod Worker deploy, smoke tests on all public endpoints | Test report + verified production URL |
| **10–15** Frontend | Foundation → UI → Turnstile/session → SSE integration → Web Component widget (IIFE, Shadow DOM, double-include guard) → Pages deploy | Playground + `widget.js` live on Pages |
| **16** Website integration | PR to `develop` adding the script tag; Turnstile hostnames + allowed origins verified | Widget works on the real site; site CSS unaffected; mobile check |
| **17** E2E & handover | Full scenario + failure matrix (invalid Turnstile, expired session, bad origin, bursts, empty index, Gemini/Vectorize failure, disconnect, large input, injection), final docs, cost notes | Complete deployed demo |

**Frontend starts only after Phase 9 is approved.**

### Estimated monthly cost (demo traffic)
Pages $0 · Turnstile $0 · Worker $0 (Free) or $5 (Paid, only if CPU or Vectorize requires it) · Vectorize $0 within
free allowance (~39k queries/month at ~100 chunks) · Gemini $0 (free tier) → **$0–$5/month**.

---

## 12. Decisions confirmed in Phase 0

| Decision | Choice |
|---|---|
| Knowledge source | Draft from verified website content (`develop` branch), excluding sample stats/phone; you review before indexing |
| Cloudflare plan | Start on Workers **Free**, measure real CPU; upgrade only with your approval |
| Vector search | **Cloudflare Vectorize** inside the single Worker project (no separate container/FAISS service); offline indexer CLI replaces `/admin/reindex` |
| Gemini tier | **Free tier** for the demo + widget privacy note; paid before production |
| Embedding model | `gemini-embedding-001`, 768 dims (as agreed; `gemini-embedding-2` noted as a future option requiring full reindex) |
| Generation model | `gemini-3.5-flash-lite` (configurable) |
| Frontend hosting | Cloudflare Pages (as agreed) |
| Session token format | JWT HS256 via stdlib, cross-tested with PyJWT |

## Verification of this phase
Phase 0 has no code. You verify it by reviewing this document. On approval, Phase 1's first commit includes it as
`docs/architecture.md` + `docs/api-contract.md` (`docs: add phase 0 architecture and API contract`), and Phase 1
begins (Node 22 install, repo init, Worker skeleton, health endpoint).
