"""
Contextual retrieval: a short note that places each passage within its document.

A passage cut from a longer document often loses the facts that make it
findable. "Revenue grew 3% over the previous quarter" does not say whose
revenue or which quarter. Following Anthropic's Contextual Retrieval method
(https://www.anthropic.com/engineering/contextual-retrieval), Claude Haiku reads
the whole document and writes 50 to 100 tokens of context for each passage.
That context is embedded and keyword-indexed together with the passage. The
passage text Claude sees when answering, and the reader sees in the sources
rail, stays unchanged.

Notes are cached in <CHROMA_PATH>/context_cache.sqlite, keyed by model,
document and passage, so re-ingesting an unchanged passage costs nothing.
The document goes first in each request with a cache_control marker, so for
long documents the API bills the repeated document at the cached rate.
"""

import hashlib
import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

import config

logger = logging.getLogger(__name__)

CACHE_PATH = Path(config.CHROMA_PATH) / "context_cache.sqlite"

# Haiku's price doubles past 100K input tokens; documents longer than this are
# cut to a window around the passage (about 75K tokens).
MAX_DOC_CHARS = 300_000

# Anthropic's published prompt, with the document first so it can be cached.
_DOC_TEMPLATE = "<document>\n{document}\n</document>"
_CHUNK_TEMPLATE = """\
Here is the chunk we want to situate within the whole document
<chunk>
{chunk}
</chunk>
Please give a short succinct context to situate this chunk within the overall \
document for the purposes of improving search retrieval of the chunk. Answer only \
with the succinct context and nothing else."""

_client: anthropic.Anthropic | None = None
_lock = threading.Lock()


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


# ── Cache ──────────────────────────────────────────────────────────────────

def _key(document: str, chunk: str) -> str:
    raw = f"{config.AUTOTAG_MODEL}\0{document}\0{chunk}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_connect() -> sqlite3.Connection:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_PATH, timeout=30, check_same_thread=False)
    conn.execute("create table if not exists context (key text primary key, context text not null)")
    return conn


def _cache_get(conn: sqlite3.Connection, keys: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(keys), 500):
        part = keys[i:i + 500]
        q = f"select key, context from context where key in ({','.join('?' * len(part))})"
        out.update(conn.execute(q, part).fetchall())
    return out


def _cache_put(conn: sqlite3.Connection, key: str, context: str) -> None:
    with _lock, conn:
        conn.execute("insert or replace into context values (?, ?)", (key, context))


# ── Haiku call ─────────────────────────────────────────────────────────────

def _document_window(document: str, chunk: str) -> str:
    if len(document) <= MAX_DOC_CHARS:
        return document
    at = max(document.find(chunk[:200]), 0)
    start = max(0, min(at - MAX_DOC_CHARS // 2, len(document) - MAX_DOC_CHARS))
    return document[start:start + MAX_DOC_CHARS]


def _generate(document: str, chunk: str) -> str:
    response = _get_client().messages.create(
        model=config.AUTOTAG_MODEL,
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": _DOC_TEMPLATE.format(document=_document_window(document, chunk)),
                 "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": _CHUNK_TEMPLATE.format(chunk=chunk)},
            ],
        }],
        **config.HAIKU_PARAMS,
    )
    return " ".join(config.text_of(response).split())


# ── Public API ─────────────────────────────────────────────────────────────

def add_context(chunks: list[dict], document: str) -> int:
    """
    Set chunk["context"] on every chunk, from the cache or from Haiku.

    Returns how many chunks are left without context because a call failed.
    Those chunks are still indexed, and the next ingest of the file retries them.
    """
    if not chunks:
        return 0
    conn = _cache_connect()
    try:
        keys = [_key(document, c["text"]) for c in chunks]
        cached = _cache_get(conn, keys)
        todo = [(c, k) for c, k in zip(chunks, keys) if k not in cached]
        for c, k in zip(chunks, keys):
            if k in cached:
                c["context"] = cached[k]

        def work(item) -> bool:
            chunk, key = item
            try:
                context = _generate(document, chunk["text"])
            except anthropic.APIError as exc:
                logger.warning("Context generation failed (%s); passage indexed without it", exc)
                chunk["context"] = ""
                return False
            chunk["context"] = context
            _cache_put(conn, key, context)
            return True

        failed = 0
        if todo:
            # The first call writes the document to the prompt cache; the rest can read it.
            failed += not work(todo[0])
            if len(todo) > 1:
                with ThreadPoolExecutor(max_workers=max(1, config.CONTEXT_WORKERS)) as pool:
                    failed += sum(not ok for ok in pool.map(work, todo[1:]))
        return failed
    finally:
        conn.close()
