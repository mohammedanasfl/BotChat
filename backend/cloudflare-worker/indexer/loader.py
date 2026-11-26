"""Load knowledge markdown files as normalized documents."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Document:
    name: str  # "products.md"
    title: str  # first H1, e.g. "Products"
    text: str  # normalized markdown, source comments removed

    @property
    def stem(self) -> str:
        return self.name.removesuffix(".md")


def normalize(text: str) -> str:
    """Same meaning -> same text, so unchanged content keeps its hash and is never re-embedded."""
    text = _COMMENT.sub("", text)  # source notes are for humans, not embeddings
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace(" ", " ")
    lines = [line.rstrip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def load_documents(directory: Path) -> list[Document]:
    paths = sorted(directory.glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"No markdown files in {directory}")
    documents = []
    for path in paths:
        text = normalize(path.read_text(encoding="utf-8"))
        match = _H1.search(text)
        if not match:
            raise ValueError(f"{path.name} needs a '# Title' heading")
        documents.append(Document(path.name, match.group(1), text))
    return documents
