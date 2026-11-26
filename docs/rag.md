# RAG design: knowledge, chunking and embeddings

Phase 2 covers knowledge → chunks → embeddings. Phase 3 adds Vectorize; Phases 4–5 add query-time
retrieval and answer generation.

```
knowledge/*.md ─► loader (normalize) ─► chunker ─► Gemini embeddings ─► .cache/embeddings.json ─► (Phase 3) Vectorize
```

Everything here runs offline in `backend/cloudflare-worker/indexer/`; none of it is bundled into the Worker.

## Knowledge rules

- Only facts published on the Abinaya website (`Swethasekar5/Abinayagarment`, `develop` @ `a139584f7e04`).
  Each file starts with an HTML comment naming its sources; it is stripped before embedding.
- Values the website marks as sample or interim (phone, WhatsApp number, business stats) are excluded,
  and a unit test guards against them.
- **Each fact lives in exactly one file.** Duplicates waste retrieval slots: before de-duplication the
  question "Are you open on Sunday?" returned three chunks that all said the same thing.
  `faqs.md` holds only the website's own FAQs (ordering, MOQ, customisation, payment).

## Chunking: one section = one chunk

The documents are small and organised by topic, so the section structure is the right chunk boundary:

- Each H2/H3 section becomes one chunk, which gives one topic per chunk. Retrieval can then return several
  *different* facts instead of fragments of the same one.
- The embedded text is `"{Title} › {Section}\n\n{body}"`. The heading carries the context, so short
  sections such as "Pricing › Invoices: Abinaya provides GST invoices." still embed meaningfully, and no
  overlap between chunks is needed.
- Only a section longer than 1,000 characters would be split, at paragraph boundaries, keeping its heading.
  Today no section needs it: **34 chunks, 30–968 characters, average 285.**
- Chunk id is `{file}-{nnn}` (Vectorize allows ids up to 64 bytes). The content hash is SHA-256 of the
  embedded text.

## Embeddings

| Setting | Value (single source: `src/config/embedding.py`) |
|---|---|
| Model / dimensions | `gemini-embedding-001`, 768 (Vectorize max is 1,536) |
| Task types | `RETRIEVAL_DOCUMENT` for chunks, `RETRIEVAL_QUERY` for visitor questions |
| Similarity | cosine (truncated Gemini vectors are not unit-length) |
| Requests | 50 texts per call; up to 3 attempts on 429/5xx; every vector must have 768 values |
| Cache | `.cache/embeddings.json` (git-ignored): `{content_sha256: vector}`, discarded if the model or dimensions change. Only new or changed chunks are embedded. |

## Query embedding from the Worker (verified 2026-11-26)

The Worker cannot use the Python SDK, so it calls REST. Google's docs show two body shapes. Tested against
the SDK, **only top-level fields work**: the nested `embedContentConfig` shape is silently ignored and
returns 3,072 dimensions.

```http
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent
x-goog-api-key: <GEMINI_API_KEY>

{"model": "models/gemini-embedding-001",
 "content": {"parts": [{"text": "<visitor question>"}]},
 "taskType": "RETRIEVAL_QUERY",
 "outputDimensionality": 768}
```

The Worker must reject any vector whose length is not 768.

## Vectorize index (Phase 3)

| Setting | Value |
|---|---|
| Index | `abinaya-kb`: 768 dimensions, cosine metric, one index for dev and prod (the Worker only reads it) |
| Record | `id` = chunk id, `values` = embedding, `metadata` = `{document, heading, text}`, so one query returns ready-to-use text |
| Sync | `python -m indexer sync` upserts all chunks from the cache (no Gemini calls), then deletes ids that no longer exist |
| Auth | your `wrangler login` session; no extra API token |
| Plan | created on the Workers **Free** plan without errors (2026-11-26) |

Notes from the first deployment:

- Mutations are eventually consistent. `list-vectors` showed all 34 ids before every vector was queryable;
  full search worked about 10 seconds later.
- When querying with `wrangler vectorize query --vector`, pass each value as `--vector=<x>`. Separate
  arguments such as `-0.018` are read as flags.
- Vectorize scores match the local cosine calculation within ±0.0002, so local evaluation is valid.

## Retrieval quality and score cutoff

`python -m indexer eval` runs `knowledge/eval_questions.json`: 16 realistic questions (expected sections
named by heading) plus 4 off-topic ones, including a prompt-injection attempt.

| Metric | Result |
|---|---|
| Right section ranked first (hit@1) | 81% (13/16) |
| Right section in top 3 (hit@3) | **100%** |
| Lowest score of a correct match | 0.619 |
| Highest score of an off-topic question | 0.596 |

Decisions:

- `SEARCH_TOP_K = 4`: every correct section appears within the top 3. The rank-2/3 cases are still
  useful context; for example, "polo price" returns the polo product first and the pricing policy second.
- `SEARCH_MIN_SCORE = 0.60`: drops off-topic questions (their best match is ≤ 0.596) while keeping every
  correct match (≥ 0.619). The margin is small, so the cutoff only removes weak matches. The answer prompt
  (Phase 5) is the real defence against off-topic and injection questions.
- After editing knowledge files, re-run `embed`, `eval` and `sync`. Re-check the cutoff if the scores move.

## Commands

```bash
cd backend/cloudflare-worker
uv run python -m indexer chunks                   # chunk report, no API calls
uv run --env-file .env python -m indexer embed    # embed new/changed chunks
uv run --env-file .env python -m indexer eval     # retrieval quality report
uv run python -m indexer sync                     # upload to Vectorize (nvm use; wrangler login)
uv run --env-file .env pytest tests/live          # live relevance check
```
