"""
Offline tests for contextual retrieval. Haiku is replaced by a fake client,
so no API calls are made.

    python -m pytest tests -q
"""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
_TMP = tempfile.mkdtemp(prefix="ra-ctx-test-")
os.environ.setdefault("ANTHROPIC_API_KEY", "offline-test-placeholder")
os.environ.setdefault("CHROMA_PATH", _TMP)
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

import config  # noqa: E402
import contextualizer  # noqa: E402
import embedder  # noqa: E402

DOC = "# Q3 market report\n\nIntro.\n\nRevenue grew 3% over the previous quarter."
CHUNK = "Revenue grew 3% over the previous quarter."
NOTE = "From the Zanzibar Coffee Cooperative's third-quarter 2026 market report, on revenue."


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=f"  {NOTE}\n"),
        ])


@pytest.fixture
def fake(monkeypatch, tmp_path):
    messages = FakeMessages()
    monkeypatch.setattr(contextualizer, "_client", SimpleNamespace(messages=messages))
    monkeypatch.setattr(contextualizer, "CACHE_PATH", tmp_path / "context_cache.sqlite")
    return messages


def test_context_is_generated_once_then_cached(fake):
    chunks = [{"text": CHUNK, "metadata": {}}]
    assert contextualizer.add_context(chunks, DOC) == 0
    assert chunks[0]["context"] == NOTE

    # The document goes first, marked for prompt caching; the passage follows.
    content = fake.calls[0]["messages"][0]["content"]
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert DOC in content[0]["text"] and CHUNK in content[1]["text"]

    again = [{"text": CHUNK, "metadata": {}}]
    contextualizer.add_context(again, DOC)
    assert again[0]["context"] == NOTE
    assert len(fake.calls) == 1, "an unchanged passage should come from the cache"


def test_failed_call_is_reported_and_not_cached(fake, monkeypatch):
    import anthropic

    def boom(**kw):
        raise anthropic.APIConnectionError(request=None)

    monkeypatch.setattr(fake, "create", boom)
    chunks = [{"text": CHUNK, "metadata": {}}]
    assert contextualizer.add_context(chunks, DOC) == 1
    assert chunks[0]["context"] == ""


def test_long_documents_are_windowed_around_the_passage():
    doc = "x " * 400_000 + CHUNK + " y" * 400_000
    window = contextualizer._document_window(doc, CHUNK)
    assert len(window) == contextualizer.MAX_DOC_CHARS and CHUNK in window


def test_context_is_searchable_but_not_shown(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "COLLECTION_NAME", "test_contextual")
    monkeypatch.setattr(embedder, "KEYWORD_INDEX_PATH", tmp_path / "kw.sqlite")
    meta = {"source": "q3.md", "title": "Q3 market report", "topics": "Market", "source_type": "report",
            "section": "(intro)", "chunk_index": 0}
    embedder.add_chunks([{"text": CHUNK, "metadata": meta, "context": NOTE}], filepath="q3.md")
    embedder.build_keyword_index()

    # "Zanzibar" appears only in the context note; keyword and vector search both reach the passage.
    hits = embedder.search_multi(["Zanzibar cooperative revenue"], report_cap=None)
    assert hits and hits[0]["metadata"]["source"] == "q3.md"
    kw_only = embedder.search_multi(["Zanzibar"], report_cap=None, min_similarity=2.0)
    assert kw_only and kw_only[0]["id"] == hits[0]["id"]

    # The stored vector was built from context + passage.
    import numpy as np
    stored = embedder._get_collection().get(ids=[hits[0]["id"]], include=["embeddings"])["embeddings"][0]
    expected = embedder._get_ef()([f"{NOTE}\n\n{CHUNK}"])[0]
    assert np.allclose(stored, expected, atol=1e-5)

    # Claude and the reader still see the bare passage.
    assert hits[0]["text"] == CHUNK
    assert hits[0]["metadata"]["context"] == NOTE


def test_text_of_skips_thinking_blocks():
    resp = SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking="..."),
                                    SimpleNamespace(type="text", text="answer")])
    assert config.text_of(resp) == "answer"
