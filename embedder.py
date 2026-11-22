"""
Vector and keyword storage for the document library.

Uses ChromaDB's built-in DefaultEmbeddingFunction (all-MiniLM-L6-v2 via
onnxruntime - no sentence-transformers dependency required).
"""

import hashlib
import logging
import re
import sqlite3
from pathlib import Path

import chromadb

import config

logger = logging.getLogger(__name__)

# Sentinel key for topic filters passed to search() / search_multi().
# ChromaDB stores topics as comma-separated strings; $contains only works on
# array metadata, not substrings - so we post-filter after retrieval.
TOPIC_FILTER_KEY = "_topic"

_ef = None   # lazy-initialized on first use


def _get_ef():
    """Lazy-init the ONNX embedding function. Fails fast with a clear message."""
    global _ef
    if _ef is None:
        try:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
            _ef = DefaultEmbeddingFunction()
        except Exception as exc:
            raise SystemExit(
                f"Embedding model unavailable - check network / disk space.\n"
                f"Model cache: ~/.cache/chroma/\nError: {exc}"
            ) from exc
    return _ef


def prewarm() -> None:
    """
    Download/load the ONNX model upfront so the first ingest doesn't stall.
    Call this at the start of run_all() and watch() so failures surface early.
    """
    logger.info("Pre-warming embedding model...")
    _get_ef()
    logger.info("Embedding model ready.")


# ── ChromaDB client ────────────────────────────────────────────────────────

def _get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=config.CHROMA_PATH)
    return client.get_or_create_collection(
        name=config.COLLECTION_NAME,
        embedding_function=_get_ef(),
        metadata={"hnsw:space": "cosine"},
    )


def _chunk_id(filepath: str, section: str, chunk_index: int) -> str:
    """Stable chunk ID based on file path + section + position."""
    raw = f"{filepath}::{section}::{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── Public API ─────────────────────────────────────────────────────────────

def add_chunks(chunks: list[dict], filepath: str = "") -> int:
    """
    Embed and upsert chunks. Returns count of newly added chunks.

    Uses stable IDs so re-ingesting the same file is idempotent.
    """
    if not chunks:
        return 0

    collection = _get_collection()

    ids = [
        _chunk_id(
            filepath or c["metadata"].get("source", ""),
            c["metadata"].get("section", ""),
            c["metadata"].get("chunk_index", i),
        )
        for i, c in enumerate(chunks)
    ]

    # Check which IDs already exist
    batch_size = 500
    existing: set[str] = set()
    for i in range(0, len(ids), batch_size):
        result = collection.get(ids=ids[i : i + batch_size])
        existing.update(result["ids"])

    new_chunks = [(c, cid) for c, cid in zip(chunks, ids) if cid not in existing]
    if not new_chunks:
        return 0

    texts = [c["text"] for c, _ in new_chunks]
    new_ids = [cid for _, cid in new_chunks]

    # Ensure all metadata values are str/int/float (ChromaDB requirement)
    metadatas = []
    for c, _ in new_chunks:
        meta = {}
        for k, v in c["metadata"].items():
            meta[k] = v if isinstance(v, (int, float)) else str(v)
        if c.get("context"):
            meta["context"] = c["context"]
        metadatas.append(meta)

    # With contextual retrieval the vector is built from context + passage, while
    # the stored document stays the bare passage that Claude and the reader see.
    contextual = any(m.get("context") for m in metadatas)

    for i in range(0, len(new_ids), batch_size):
        end = i + batch_size
        kwargs = {}
        if contextual:
            kwargs["embeddings"] = _get_ef()([_embed_text(t, m) for t, m in zip(texts[i:end], metadatas[i:end])])
        collection.add(
            ids=new_ids[i:end],
            documents=texts[i:end],
            metadatas=metadatas[i:end],
            **kwargs,
        )

    _kw_add(new_ids, texts, metadatas)

    logger.debug("Added %d new chunks (skipped %d existing)", len(new_ids), len(existing))
    return len(new_ids)


def _embed_text(text: str, meta: dict) -> str:
    """What the embedder reads for a passage: its context note, if any, then the passage."""
    context = meta.get("context") or ""
    return f"{context}\n\n{text}" if context else text


def matches_topic(topics_value: str, topic: str) -> bool:
    """True if comma-separated topics metadata includes topic (exact token)."""
    topic = (topic or "").strip()
    if not topic:
        return True
    for token in (topics_value or "").split(", "):
        if token.strip() == topic:
            return True
    return False


def topic_filter(topic: str) -> dict:
    """
    Filter dict for search() / search_multi() restricting to one topic.

    Topics are stored as comma-separated strings (e.g. "Retrieval, Evaluation").
    ChromaDB's metadata $contains expects array fields, not substring matches,
    so search applies this via post-filtering with over-fetch.
    """
    topic = (topic or "").strip()
    if not topic or topic == "All topics":
        return {}
    return {TOPIC_FILTER_KEY: topic}


def _parse_filters(filters: dict | None) -> tuple[dict | None, str | None]:
    """Split Chroma where-clause from optional topic post-filter."""
    if not filters:
        return None, None
    if TOPIC_FILTER_KEY in filters:
        topic = str(filters[TOPIC_FILTER_KEY]).strip()
        chroma = {k: v for k, v in filters.items() if k != TOPIC_FILTER_KEY}
        return (chroma or None), (topic or None)
    return filters, None


def _filter_by_topic(hits: list[dict], topic: str) -> list[dict]:
    return [h for h in hits if matches_topic(h["metadata"].get("topics", ""), topic)]


def delete_file(filepath: str) -> int:
    """
    Remove all chunks whose metadata.source matches the filename.
    Returns count deleted.
    """
    filename = Path(filepath).name
    collection = _get_collection()

    result = collection.get(where={"source": filename})
    ids_to_delete = result["ids"]
    if ids_to_delete:
        collection.delete(ids=ids_to_delete)
        _kw_delete(ids_to_delete)
        logger.info("Deleted %d chunks for %s", len(ids_to_delete), filename)
    return len(ids_to_delete)


# ── Keyword index (SQLite FTS5 / BM25) ─────────────────────────────────────
#
# A second index over the same chunks, kept in step by add_chunks() and
# delete_file(), so every ingest path (main.py ingest, the watcher, the
# importers) updates it without changes of its own. MiniLM misses exact names,
# numbers and acronyms; BM25 catches them, and search_multi() fuses both.
# If the index file is missing or unreadable, search falls back to vector-only
# and writes are skipped with a warning. Build or rebuild it with:
#   python -c "import embedder; embedder.build_keyword_index()"

KEYWORD_INDEX_PATH = Path(config.CHROMA_PATH) / "keyword_index.sqlite"

_KW_STOP = set("""a an and are as at be been but by can could did do does for from had has have how i if in into is it its
of on or our so than that the their them then there these they this to too was we were what when where which who whom
why will with would you your about any also just more most not only other some such tell me us after before over""".split())


def _kw_connect(readonly: bool) -> sqlite3.Connection | None:
    if not KEYWORD_INDEX_PATH.exists():
        return None
    try:
        if readonly:
            conn = sqlite3.connect(f"file:{KEYWORD_INDEX_PATH}?mode=ro", uri=True, timeout=10)
        else:
            conn = sqlite3.connect(KEYWORD_INDEX_PATH, timeout=30)
        conn.execute("select 1 from chunks limit 1")
        return conn
    except sqlite3.Error as exc:
        logger.warning("Keyword index unreadable (%s); using vector-only search", exc)
        return None


def _kw_body(text: str, meta: dict) -> str:
    return f"{meta.get('title') or ''}\n{meta.get('context') or ''}\n{text}"


def _kw_add(ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
    conn = _kw_connect(readonly=False)
    if conn is None:
        return
    try:
        with conn:
            conn.executemany("delete from chunks where cid = ?", [(i,) for i in ids])
            conn.executemany(
                "insert into chunks values (?,?,?,?)",
                [(i, m.get("source", ""), m.get("source_type", ""), _kw_body(t, m))
                 for i, t, m in zip(ids, texts, metadatas)],
            )
    except sqlite3.Error as exc:
        logger.warning("Keyword index add failed (%s); rebuild with build_keyword_index()", exc)
    finally:
        conn.close()


def _kw_delete(ids: list[str]) -> None:
    conn = _kw_connect(readonly=False)
    if conn is None:
        return
    try:
        with conn:
            conn.executemany("delete from chunks where cid = ?", [(i,) for i in ids])
    except sqlite3.Error as exc:
        logger.warning("Keyword index delete failed (%s); rebuild with build_keyword_index()", exc)
    finally:
        conn.close()


def build_keyword_index() -> int:
    """(Re)build the keyword index from every chunk in the collection. Returns chunk count."""
    collection = _get_collection()
    tmp = KEYWORD_INDEX_PATH.with_suffix(".sqlite.tmp")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    conn.execute(
        "create virtual table chunks using fts5("
        "cid unindexed, source unindexed, stype unindexed, body, tokenize='porter unicode61')"
    )
    total, page, n = collection.count(), 5000, 0
    for off in range(0, total, page):
        got = collection.get(limit=page, offset=off, include=["documents", "metadatas"])
        conn.executemany(
            "insert into chunks values (?,?,?,?)",
            [(i, m.get("source", ""), m.get("source_type", ""), _kw_body(d, m))
             for i, d, m in zip(got["ids"], got["documents"], got["metadatas"])],
        )
        n += len(got["ids"])
    conn.commit()
    conn.close()
    tmp.replace(KEYWORD_INDEX_PATH)
    logger.info("Keyword index built: %d chunks", n)
    return n


def _kw_search(conn: sqlite3.Connection, query: str, n: int) -> list[str]:
    toks = [t for t in re.findall(r"[A-Za-z0-9]+", query.lower()) if len(t) >= 3 and t not in _KW_STOP]
    if not toks:
        return []
    expr = " OR ".join(f'"{t}"' for t in dict.fromkeys(toks))
    rows = conn.execute(
        "select cid from chunks where chunks match ? order by bm25(chunks) limit ?", (expr, n)
    ).fetchall()
    return [r[0] for r in rows]


def _meta_matches_where(meta: dict, where: dict | None) -> bool:
    """Apply a plain-equality Chroma where-clause to keyword hits. Operator clauses reject the hit."""
    if not where:
        return True
    for k, v in where.items():
        if k.startswith("$") or isinstance(v, dict) or meta.get(k) != v:
            return False
    return True


def _query_collection(
    collection: chromadb.Collection,
    query: str,
    n_results: int,
    chroma_where: dict | None,
) -> list[dict]:
    kwargs: dict = {
        "query_texts": [query],
        "n_results": min(n_results, collection.count()),
    }
    if chroma_where:
        kwargs["where"] = chroma_where

    results = collection.query(**kwargs)
    output = []
    for i in range(len(results["ids"][0])):
        output.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i],
        })
    return output


def search(
    query: str,
    n_results: int = 8,
    filters: dict | None = None,
) -> list[dict]:
    """
    Semantic search. Returns list of dicts with keys: id, text, metadata, distance.

    filters: optional ChromaDB `where` dict, and/or embedder.topic_filter(topic).
    """
    collection = _get_collection()
    total = collection.count()
    if total == 0:
        return []

    chroma_where, topic = _parse_filters(filters)
    if topic is None:
        return _query_collection(collection, query, n_results, chroma_where)

    # Topic filter: over-fetch from Chroma, then keep chunks tagged with the topic.
    fetch_n = min(max(n_results * 4, 32), total)
    while True:
        hits = _query_collection(collection, query, fetch_n, chroma_where)
        matched = _filter_by_topic(hits, topic)
        if len(matched) >= n_results or fetch_n >= total:
            return matched[:n_results]
        fetch_n = min(fetch_n * 2, total)


# ── Multi-query retrieval with Reciprocal Rank Fusion ──────────────────────
#
# MiniLM-L6 is a weak encoder. Running the user's question once against it
# produces narrow, high-variance recall. We fix this by:
#   1. Running N rewritten queries (from query_rewriter.rewrite()) in parallel
#   2. Pulling a larger candidate pool per query (retrieve_per_query=20)
#   3. Dropping low-similarity noise (similarity < min_similarity)
#   4. Merging results across queries via Reciprocal Rank Fusion - each chunk's
#      fused score is sum(1 / (RRF_K + rank_i)) across the queries where it
#      appeared. RRF is rank-based so it's robust to score-scale mismatch.
#   5. Returning the top n_results after fusion
#
# Chunks that appear in multiple queries' top results get boosted, which is
# exactly the signal we want: a chunk that matches multiple phrasings of the
# same question is more likely to be genuinely relevant.

RRF_K = 60  # standard constant for reciprocal rank fusion

# Source balancing: in a corpus where one source type dominates (in the original
# deployment, news reports were ~94% of chunks), that type crowds everything else
# out of the final passages. Cap it and boost the types you care most about.
# Values come from config.py / .env.
CAPPED_TYPE = config.CAPPED_SOURCE_TYPE
REPORT_CAP = config.CAPPED_SOURCE_MAX     # at most this many CAPPED_TYPE chunks in the results
OWN_BOOST = config.BOOST_FACTOR           # fused-score multiplier for BOOSTED types
OWN_TYPES = config.BOOSTED_SOURCE_TYPES


def search_multi(
    queries: list[str],
    n_results: int = 8,
    filters: dict | None = None,
    retrieve_per_query: int = 20,
    min_similarity: float = 0.2,
    keyword: bool = True,
    report_cap: int | None = REPORT_CAP,
    own_boost: float = OWN_BOOST,
) -> list[dict]:
    """
    Run multiple retrieval queries and fuse results with Reciprocal Rank Fusion.

    Args:
        queries: List of query strings (typically produced by query_rewriter.rewrite).
        n_results: How many final results to return after fusion.
        filters: Optional ChromaDB `where` filter applied to every query.
        retrieve_per_query: Candidate pool size per query before fusion (default 20).
        min_similarity: Drop chunks with cosine similarity below this (default 0.2).
                        Cosine distance in Chroma is 1 - similarity; we convert.

    Returns:
        List of result dicts (text, metadata, distance, fused_score), sorted by
        fused_score descending. Empty list if no queries or all results filtered.
    """
    if not queries:
        return []

    collection = _get_collection()
    if collection.count() == 0:
        return []

    chroma_where, topic = _parse_filters(filters)
    search_filters = chroma_where if topic is None else filters

    # Candidate pool keyed by chunk id so we can accumulate RRF scores
    fused: dict[str, dict] = {}
    kw_conn = _kw_connect(readonly=True) if keyword else None
    kw_cache: dict = {}

    for query in queries:
        q = (query or "").strip()
        if not q:
            continue

        hits = search(q, n_results=retrieve_per_query, filters=search_filters)
        for rank, hit in enumerate(hits, start=1):
            similarity = 1.0 - hit["distance"]
            if similarity < min_similarity:
                continue

            chunk_id = hit["id"]
            rrf_contribution = 1.0 / (RRF_K + rank)

            if chunk_id in fused:
                fused[chunk_id]["fused_score"] += rrf_contribution
                # Keep the best (lowest) distance across queries for display
                if hit["distance"] < fused[chunk_id]["distance"]:
                    fused[chunk_id]["distance"] = hit["distance"]
            else:
                fused[chunk_id] = {
                    "id": chunk_id,
                    "text": hit["text"],
                    "metadata": hit["metadata"],
                    "distance": hit["distance"],
                    "fused_score": rrf_contribution,
                }

        # Keyword (BM25) hits for the same query, fused on rank like the vector hits.
        if kw_conn is not None:
            try:
                kw_ids = _kw_search(kw_conn, q, retrieve_per_query * (4 if (topic or chroma_where) else 1))
            except sqlite3.Error as exc:
                logger.warning("Keyword search failed (%s); vector-only for this query", exc)
                kw_ids = []
            if kw_ids and (topic or chroma_where):
                metas = _metas_for(collection, kw_ids, kw_cache)
                kw_ids = [
                    cid for cid in kw_ids
                    if cid in metas
                    and (topic is None or matches_topic(metas[cid][1].get("topics", ""), topic))
                    and _meta_matches_where(metas[cid][1], chroma_where)
                ]
            for rank, chunk_id in enumerate(kw_ids[:retrieve_per_query], start=1):
                rrf_contribution = 1.0 / (RRF_K + rank)
                if chunk_id in fused:
                    fused[chunk_id]["fused_score"] += rrf_contribution
                else:
                    fused[chunk_id] = {"id": chunk_id, "fused_score": rrf_contribution, "distance": 1.0}

    if kw_conn is not None:
        kw_conn.close()

    # Fill text/metadata for chunks that only came from keyword search.
    missing = [cid for cid, v in fused.items() if "metadata" not in v]
    if missing:
        metas = _metas_for(collection, missing, kw_cache)
        for cid in missing:
            if cid in metas:
                fused[cid]["text"], fused[cid]["metadata"] = metas[cid]
            else:
                del fused[cid]  # stale keyword entry for a chunk no longer in Chroma

    if own_boost != 1.0:
        for v in fused.values():
            if v["metadata"].get("source_type") in OWN_TYPES:
                v["fused_score"] *= own_boost

    # Sort by fused score descending and return the top N
    ranked = sorted(fused.values(), key=lambda h: h["fused_score"], reverse=True)
    if report_cap is None:
        return ranked[:n_results]

    out, n_reports = [], 0
    for h in ranked:
        if h["metadata"].get("source_type") == CAPPED_TYPE:
            if n_reports >= report_cap:
                continue
            n_reports += 1
        out.append(h)
        if len(out) == n_results:
            break
    return out


def _metas_for(collection: chromadb.Collection, ids: list[str], cache: dict) -> dict:
    """Fetch (text, metadata) for chunk ids from Chroma, memoised per search."""
    need = [i for i in ids if i not in cache]
    if need:
        got = collection.get(ids=need, include=["documents", "metadatas"])
        for cid, doc, meta in zip(got["ids"], got["documents"], got["metadatas"]):
            cache[cid] = (doc, meta)
    return {i: cache[i] for i in ids if i in cache}


def iter_metadatas(collection: chromadb.Collection | None = None, page: int = 5000):
    """Yield every chunk's metadata in pages (one big get() exceeds SQLite's variable limit)."""
    collection = collection or _get_collection()
    total = collection.count()
    for off in range(0, total, page):
        yield from collection.get(limit=page, offset=off, include=["metadatas"])["metadatas"]


def collection_stats() -> dict:
    """Return basic stats: total chunks and a breakdown by topics."""
    collection = _get_collection()
    total = collection.count()

    topics_breakdown: dict[str, int] = {}
    if total > 0:
        for meta in iter_metadatas(collection):
            for topic in (meta.get("topics") or "").split(", "):
                topic = topic.strip()
                if topic:
                    topics_breakdown[topic] = topics_breakdown.get(topic, 0) + 1

    return {
        "collection": config.COLLECTION_NAME,
        "total_chunks": total,
        "topics": dict(sorted(topics_breakdown.items(), key=lambda x: -x[1])),
    }
