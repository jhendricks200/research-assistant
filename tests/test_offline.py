"""
Offline tests: index the fixture library and check retrieval mechanics.
No API calls. The fixture documents carry full frontmatter, so auto-tagging is skipped.

    python -m pytest tests -q
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "library"
_TMP = tempfile.mkdtemp(prefix="ra-test-")
os.environ.update(
    ANTHROPIC_API_KEY=os.environ.get("ANTHROPIC_API_KEY") or "offline-test-placeholder",
    DOCS_PATH=str(FIXTURES),
    CHROMA_PATH=_TMP,
    COLLECTION_NAME="test_documents",
)
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

import embedder  # noqa: E402
import pipeline  # noqa: E402

embedder.KEYWORD_INDEX_PATH = Path(_TMP) / "keyword_index.sqlite"


@pytest.fixture(scope="module", autouse=True)
def indexed():
    results = pipeline.run_all(FIXTURES)
    assert not any(r.get("tagged") for r in results), "fixtures should not need auto-tagging"
    embedder.build_keyword_index()
    yield


def _sources(hits):
    return [h["metadata"]["source"] for h in hits]


def test_every_fixture_indexed():
    files = {p.name for p in FIXTURES.glob("*.md")}
    stored = {m["source"] for m in embedder.iter_metadatas()}
    assert stored == files


def test_vector_search_finds_the_right_document():
    hits = embedder.search_multi(["Why is my espresso shot sour and fast?"], keyword=False,
                                 report_cap=None, own_boost=1.0)
    assert "espresso-extraction.md" in _sources(hits)


def test_keyword_search_adds_exact_term_matches():
    hits = embedder.search_multi(["Swiss Water Process"], keyword=True)
    assert _sources(hits)[0] == "decaf-process.md"


def test_report_cap_limits_the_dominant_type():
    hits = embedder.search_multi(["equipment sales by quarter market report"], n_results=8)
    assert sum(h["metadata"]["source_type"] == embedder.CAPPED_TYPE for h in hits) <= embedder.REPORT_CAP
    uncapped = embedder.search_multi(["equipment sales by quarter market report"], n_results=8, report_cap=None)
    assert sum(h["metadata"]["source_type"] == embedder.CAPPED_TYPE for h in uncapped) == 4


def test_topic_filter_applies_to_keyword_hits():
    hits = embedder.search_multi(["grind finer"], filters=embedder.topic_filter("Espresso"))
    assert hits and all(embedder.matches_topic(h["metadata"]["topics"], "Espresso") for h in hits)


def test_keyword_index_stays_in_step_with_writes():
    import sqlite3
    count = lambda: sqlite3.connect(embedder.KEYWORD_INDEX_PATH).execute(
        "select count(*) from chunks where chunks match 'zqxwvmarker'").fetchone()[0]
    chunks = [{"text": "temporary zqxwvmarker passage", "metadata": {
        "source": "zz-temp.md", "section": "s", "chunk_index": 0, "source_type": "note", "topics": "Temp"}}]
    assert embedder.add_chunks(chunks, "zz-temp.md") == 1
    assert count() == 1
    assert embedder.delete_file("zz-temp.md") == 1
    assert count() == 0


def test_missing_keyword_index_falls_back_to_vector_only(tmp_path):
    saved = embedder.KEYWORD_INDEX_PATH
    embedder.KEYWORD_INDEX_PATH = tmp_path / "missing.sqlite"
    try:
        assert embedder.search_multi(["cold brew steeping time"])
    finally:
        embedder.KEYWORD_INDEX_PATH = saved
