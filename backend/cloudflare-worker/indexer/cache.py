"""Local embedding cache: {content_sha256: vector}, valid for one embedding configuration.

Only new or changed chunks are sent to Gemini. If the model or dimensions change, the whole
cache is discarded (old vectors are incompatible). Phase 3 uploads these vectors to Vectorize.
"""

from __future__ import annotations

import json
from pathlib import Path

from config.embedding import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL

CONFIG = {"model": EMBEDDING_MODEL, "dimensions": EMBEDDING_DIMENSIONS}


def load_cache(path: Path) -> dict[str, list[float]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["vectors"] if data.get("config") == CONFIG else {}


def save_cache(path: Path, vectors: dict[str, list[float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"config": CONFIG, "vectors": vectors}), encoding="utf-8")
