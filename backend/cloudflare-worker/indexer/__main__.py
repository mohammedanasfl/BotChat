"""Offline knowledge indexer CLI (operator machine only; never deployed).

uv run python -m indexer chunks                  # show chunks, no API calls
uv run --env-file .env python -m indexer embed   # embed new/changed chunks
"""

from __future__ import annotations

import argparse
import json
import os

from config.embedding import DOCUMENT_TASK_TYPE, QUERY_TASK_TYPE
from indexer import CACHE_DIR, KNOWLEDGE_DIR
from indexer.cache import load_cache, save_cache
from indexer.chunker import Chunk, chunk_documents
from indexer.loader import load_documents

CACHE_FILE = CACHE_DIR / "embeddings.json"


def load_chunks() -> list[Chunk]:
    return chunk_documents(load_documents(KNOWLEDGE_DIR))


def cmd_chunks() -> None:
    chunks = load_chunks()
    for c in chunks:
        print(f"{c.chunk_id:<14} {len(c.text):>5}  {c.heading_path}")
    sizes = [len(c.text) for c in chunks]
    print(
        f"\n{len(chunks)} chunks · {min(sizes)}-{max(sizes)} chars · avg {sum(sizes) // len(sizes)}"
    )


def cmd_embed() -> None:
    from google import genai

    from indexer.embedder import embed_texts

    chunks = load_chunks()
    cached = load_cache(CACHE_FILE)
    missing = [c for c in chunks if c.content_sha256 not in cached]
    if missing:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        vectors = embed_texts(client, [c.embedding_text for c in missing], DOCUMENT_TASK_TYPE)
        cached.update({c.content_sha256: v for c, v in zip(missing, vectors, strict=True)})
    # Keep only vectors for current chunks.
    save_cache(CACHE_FILE, {c.content_sha256: cached[c.content_sha256] for c in chunks})
    print(f"{len(chunks)} chunks · {len(missing)} embedded · {len(chunks) - len(missing)} cached")


def cmd_sync() -> None:
    from indexer import vectorize

    chunks = load_chunks()
    vectors = load_cache(CACHE_FILE)
    missing = [c.chunk_id for c in chunks if c.content_sha256 not in vectors]
    if missing:
        raise SystemExit(f"Run `embed` first; no embedding for: {', '.join(missing)}")
    records = vectorize.build_records(chunks, vectors)
    vectorize.upsert(records)
    stale = vectorize.stale_ids(vectorize.list_ids(), records)
    vectorize.delete(stale)
    print(f"{vectorize.INDEX_NAME}: upserted {len(records)} · deleted {len(stale)} stale {stale}")


def cmd_eval() -> None:
    from google import genai

    from indexer.embedder import embed_texts
    from indexer.evaluate import Result, rank_chunks, summarize

    chunks = load_chunks()
    vectors = load_cache(CACHE_FILE)
    cases = json.loads((KNOWLEDGE_DIR / "eval_questions.json").read_text(encoding="utf-8"))
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    queries = embed_texts(client, [c["question"] for c in cases], QUERY_TASK_TYPE)

    results = [
        Result(c["question"], c["expected"], rank_chunks(q, chunks, vectors))
        for c, q in zip(cases, queries, strict=True)
    ]
    for r in results:
        verdict = "off-topic" if not r.expected else (f"rank {r.rank}" if r.rank else "MISS")
        score, best = r.ranked[0]
        print(f"{score:.3f} {verdict:<10} {r.question[:48]:<48} -> {best.heading_path}")
    stats = summarize(results)
    print(
        f"\nhit@1 {stats['hit_at_1']:.0%} · hit@3 {stats['hit_at_3']:.0%} · "
        f"lowest correct score {stats['min_correct_score']:.3f} · "
        f"highest off-topic score {stats['max_off_topic_score']:.3f}"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m indexer")
    parser.add_argument("command", choices=["chunks", "embed", "sync", "eval"])
    args = parser.parse_args(argv)
    {"chunks": cmd_chunks, "embed": cmd_embed, "sync": cmd_sync, "eval": cmd_eval}[args.command]()


if __name__ == "__main__":
    main()
