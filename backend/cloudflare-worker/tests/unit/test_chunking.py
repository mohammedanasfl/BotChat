import pytest

from indexer import KNOWLEDGE_DIR
from indexer.chunker import Chunk, chunk_document, chunk_documents
from indexer.loader import Document, load_documents, normalize


def doc(text: str) -> Document:
    return Document("products.md", "Products", normalize(text))


def test_normalize_strips_comments_and_editor_noise():
    raw = "<!-- source -->\r\n# T x  \r\n\r\n\r\n\r\nbody\n"
    assert normalize(raw) == "# T x\n\nbody\n"


def test_one_chunk_per_section_with_heading_path():
    chunks = chunk_document(
        doc("# Products\n\nIntro.\n\n## Polo\n\nPique.\n\n### Sizes\n\nS-XXL.\n")
    )
    assert [(c.chunk_id, c.heading_path, c.text) for c in chunks] == [
        ("products-001", "Products", "Intro."),
        ("products-002", "Products › Polo", "Pique."),
        ("products-003", "Products › Polo › Sizes", "S-XXL."),
    ]
    assert chunks[2].embedding_text == "Products › Polo › Sizes\n\nS-XXL."


def test_sibling_heading_resets_path_and_empty_sections_are_skipped():
    chunks = chunk_document(doc("# P\n\n## A\n\n### A1\n\nx\n\n## Empty\n\n## B\n\ny\n"))
    assert [c.heading_path for c in chunks] == ["Products › A › A1", "Products › B"]


def test_long_section_splits_at_paragraphs_and_keeps_heading():
    body = "\n\n".join(f"Paragraph {i}. " + "word " * 30 for i in range(10))
    chunks = chunk_document(doc(f"# P\n\n## Long\n\n{body}"), max_chars=400)
    assert len(chunks) > 1
    assert all(len(c.text) <= 400 for c in chunks)
    assert all(c.heading_path == "Products › Long" for c in chunks)
    assert " ".join(c.text for c in chunks).split() == body.split()  # nothing lost or duplicated


def test_hash_changes_with_text_or_heading_but_not_id():
    base = Chunk("p-001", "p.md", "Products › Polo", "Pique.")
    assert base.content_sha256 == Chunk("p-009", "p.md", "Products › Polo", "Pique.").content_sha256
    assert base.content_sha256 != Chunk("p-001", "p.md", "Products › Polo", "Pique!").content_sha256
    assert (
        base.content_sha256 != Chunk("p-001", "p.md", "Products › Shirt", "Pique.").content_sha256
    )


def test_loader_requires_title(tmp_path):
    (tmp_path / "x.md").write_text("no title\n")
    with pytest.raises(ValueError, match="Title"):
        load_documents(tmp_path)


# --- the real knowledge base ------------------------------------------------------------

KB = chunk_documents(load_documents(KNOWLEDGE_DIR))


def test_knowledge_base_is_well_sized_and_unique():
    assert {c.document for c in KB} == {
        "company.md",
        "products.md",
        "services.md",
        "pricing.md",
        "policies.md",
        "faqs.md",
    }
    assert len({c.chunk_id for c in KB}) == len(KB)
    assert len({c.content_sha256 for c in KB}) == len(KB)  # no duplicate chunks
    assert all(len(c.text) <= 1000 for c in KB)  # every section fits in one chunk
    assert all("source:" not in c.text for c in KB)


def test_knowledge_base_excludes_unverified_values():
    text = " ".join(c.text for c in KB)
    for unverified in ("98765 43210", "9876543210", "95975 41703", "2.5L", "420+"):
        assert unverified not in text
