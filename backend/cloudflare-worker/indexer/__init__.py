"""Offline knowledge indexer: markdown -> chunks -> Gemini embeddings -> Cloudflare Vectorize.

Lives outside `src/`, so it is never bundled into the Worker. It imports the Worker's shared
embedding configuration (`src/config/embedding.py`) so documents and queries are embedded with
exactly the same model and dimensions.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
CACHE_DIR = PROJECT_ROOT / ".cache"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
