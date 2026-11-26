"""Sync chunk embeddings to the Cloudflare Vectorize index via the Wrangler CLI.

Wrangler uses your `wrangler login` session, so no extra API token is needed.
Requires Node >= 22 on PATH (run `nvm use` first).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from indexer import CACHE_DIR, PROJECT_ROOT
from indexer.chunker import Chunk

INDEX_NAME = "abinaya-kb"


def build_records(chunks: list[Chunk], vectors: dict[str, list[float]]) -> list[dict]:
    """One Vectorize record per chunk; metadata holds what the Worker shows the model."""
    return [
        {
            "id": c.chunk_id,
            "values": vectors[c.content_sha256],
            "metadata": {"document": c.document, "heading": c.heading_path, "text": c.text},
        }
        for c in chunks
    ]


def stale_ids(existing: set[str], records: list[dict]) -> list[str]:
    """Ids in the index that no longer correspond to a chunk."""
    return sorted(existing - {r["id"] for r in records})


def _wrangler(*args: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed command, no shell, args are ours
        ["npx", "--no-install", "wrangler", "vectorize", *args],  # noqa: S607
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"wrangler vectorize {args[0]} failed:\n{result.stderr or result.stdout}"
        )
    return result.stdout


def list_ids() -> set[str]:
    ids: set[str] = set()
    cursor: str | None = None
    while True:
        args = ["list-vectors", INDEX_NAME, "--json", "--count", "1000"]
        if cursor:
            args += ["--cursor", cursor]
        page = json.loads(_wrangler(*args))
        ids |= {v["id"] for v in page.get("vectors", [])}
        cursor = page.get("nextCursor")
        if not page.get("isTruncated") or not cursor:
            return ids


def upsert(records: list[dict]) -> None:
    path: Path = CACHE_DIR / "vectors.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    _wrangler("upsert", INDEX_NAME, "--file", str(path))


def delete(ids: list[str]) -> None:
    if ids:
        _wrangler("delete-vectors", INDEX_NAME, "--ids", *ids)
