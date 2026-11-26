"""Section-based chunking for small, well-structured business documents.

Each H2/H3 section is one chunk: one topic per chunk gives sharp embeddings and lets retrieval
return several *different* facts instead of fragments of one. A section longer than `max_chars`
is split at paragraph boundaries. No overlap is needed because every chunk is embedded together
with its heading path ("Products › Classic Polo T-Shirt"), which carries the context.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from indexer.loader import Document

MAX_CHARS = 1000
SEPARATOR = " › "

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str  # "products-005" (Vectorize ids must be <= 64 bytes)
    document: str  # "products.md"
    heading_path: str  # "Products › Classic Polo T-Shirt"
    text: str  # section body, shown to the model as reference data

    @property
    def embedding_text(self) -> str:
        return f"{self.heading_path}\n\n{self.text}"

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.embedding_text.encode("utf-8")).hexdigest()


def chunk_documents(documents: list[Document], max_chars: int = MAX_CHARS) -> list[Chunk]:
    return [chunk for doc in documents for chunk in chunk_document(doc, max_chars)]


def chunk_document(document: Document, max_chars: int = MAX_CHARS) -> list[Chunk]:
    chunks = []
    for headings, body in _sections(document.text):
        path = SEPARATOR.join([document.title, *headings])
        for text in _split(body, max_chars):
            chunk_id = f"{document.stem}-{len(chunks) + 1:03d}"
            chunks.append(Chunk(chunk_id, document.name, path, text))
    return chunks


def _sections(text: str) -> list[tuple[list[str], str]]:
    """(headings below the H1, body) for every section that has body text."""
    sections, stack, body = [], [], []

    def flush() -> None:
        content = "\n".join(body).strip()
        if content:
            sections.append(([heading for _, heading in stack], content))
        body.clear()

    for line in text.split("\n"):
        match = _HEADING.match(line)
        if not match:
            body.append(line)
            continue
        flush()
        level = len(match.group(1))
        stack = [(lvl, h) for lvl, h in stack if lvl < level and level > 1]
        if level > 1:
            stack.append((level, match.group(2)))
    flush()
    return sections


def _split(body: str, max_chars: int) -> list[str]:
    """Greedily pack paragraphs into pieces of at most max_chars (a single longer
    paragraph is kept whole rather than cut mid-sentence)."""
    if len(body) <= max_chars:
        return [body]
    pieces, current = [], ""
    for paragraph in re.split(r"\n\s*\n", body):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if current and len(candidate) > max_chars:
            pieces.append(current)
            current = paragraph
        else:
            current = candidate
    pieces.append(current)
    return pieces
