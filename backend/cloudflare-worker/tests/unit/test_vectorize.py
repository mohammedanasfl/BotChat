import json

from indexer import KNOWLEDGE_DIR
from indexer.chunker import Chunk, chunk_documents
from indexer.evaluate import Result, rank_chunks, summarize
from indexer.loader import load_documents
from indexer.vectorize import build_records, stale_ids

A = Chunk("company-001", "company.md", "Company › Hours", "Mon-Sat.")
B = Chunk("pricing-001", "pricing.md", "Pricing › Invoices", "GST invoices.")
VECTORS = {A.content_sha256: [1.0, 0.0], B.content_sha256: [0.0, 1.0]}


def test_records_carry_text_for_the_worker():
    (record, _) = build_records([A, B], VECTORS)
    assert record == {
        "id": "company-001",
        "values": [1.0, 0.0],
        "metadata": {"document": "company.md", "heading": "Company › Hours", "text": "Mon-Sat."},
    }
    assert len(json.dumps(record["metadata"]).encode()) < 10 * 1024  # Vectorize metadata limit


def test_stale_ids_are_index_ids_without_a_chunk():
    records = build_records([A], VECTORS)
    assert stale_ids({"company-001", "faqs-009", "old-1"}, records) == ["faqs-009", "old-1"]
    assert stale_ids(set(), records) == []


def test_ranking_and_summary():
    ranked = rank_chunks([0.9, 0.1], [A, B], VECTORS)
    assert [c.chunk_id for _, c in ranked] == ["company-001", "pricing-001"]
    results = [
        Result("hours?", ["Company › Hours"], ranked),
        Result("invoice?", ["Pricing › Invoices"], ranked),  # found at rank 2
        Result("laptops?", [], rank_chunks([0.5, 0.5], [A, B], VECTORS)),
    ]
    stats = summarize(results)
    assert stats["hit_at_1"] == 0.5
    assert stats["hit_at_3"] == 1.0
    assert round(stats["max_off_topic_score"], 3) == 0.707


def test_eval_questions_reference_real_sections():
    headings = {c.heading_path for c in chunk_documents(load_documents(KNOWLEDGE_DIR))}
    cases = json.loads((KNOWLEDGE_DIR / "eval_questions.json").read_text())
    for case in cases:
        assert set(case["expected"]) <= headings, case["question"]
    assert any(not c["expected"] for c in cases)  # includes off-topic questions
