"""
Evaluation harness: measures retrieval and answers against a question file.

  python eval/run_eval.py rewrite                 # 1 Haiku call per question, cached in eval/rewrites*.json
  python eval/run_eval.py retrieve <variant>      # retrieval only, no API calls
  python eval/run_eval.py answer <variant>        # 1 Sonnet call per question, then grades
  python eval/run_eval.py report                  # print every saved summary

Question file: eval/questions.jsonl by default, or eval/questions_<QSET>.jsonl with QSET=<name>.
Each line: {"id", "type", "q", "gold": [source filenames], "facts": ["a|b", ...]}.
An empty gold list marks a question the library cannot answer; the model should decline it.

Variants (see VARIANTS): baseline, hybrid, balance, hybrid_balance (the shipped default),
and, with requirements-eval.txt installed, the rerank and bge variants.
To score contextual retrieval, ingest into a separate index with CONTEXTUAL_CHUNKS=true and
run the same commands with those settings; results are saved with a _ctx suffix.
The query rewrites are cached once and reused by every variant, so comparing variants costs nothing.
API calls are counted in eval/calls.json and capped by EVAL_CALL_CAP (default 30).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
sys.path.insert(0, str(ROOT))

import anthropic  # noqa: E402
import httpx  # noqa: E402

import chat as chat_module  # noqa: E402
import config  # noqa: E402
import embedder  # noqa: E402
import query_rewriter  # noqa: E402

QSET = os.environ.get("QSET", "")
QFILE = EVAL / (f"questions_{QSET}.jsonl" if QSET else "questions.jsonl")
RWFILE = EVAL / (f"rewrites_{QSET}.json" if QSET else "rewrites.json")
RUNS = EVAL / (f"runs_{QSET}" if QSET else "runs")
CALLS_FILE = EVAL / "calls.json"
CALL_CAP = int(os.environ.get("EVAL_CALL_CAP", "30"))
N_FINAL = 8
# Runs against a contextual index (CONTEXTUAL_CHUNKS=true) are saved as <variant>_ctx,
# so they sit next to the plain runs instead of overwriting them.
TAG = "_ctx" if config.CONTEXTUAL_CHUNKS else ""


# ── API client with a hard call counter ───────────────────────────────────

def _calls() -> int:
    return json.loads(CALLS_FILE.read_text())["calls"] if CALLS_FILE.exists() else 0


def _bump() -> None:
    n = _calls() + 1
    if n > CALL_CAP:
        raise SystemExit(f"API call cap {CALL_CAP} reached (raise EVAL_CALL_CAP to continue)")
    CALLS_FILE.write_text(json.dumps({"calls": n}))


def make_client() -> anthropic.Anthropic:
    # No keep-alive reuse and a bounded timeout: avoids long hangs on back-to-back calls.
    return anthropic.Anthropic(
        api_key=config.ANTHROPIC_API_KEY,
        max_retries=0,
        http_client=httpx.Client(
            limits=httpx.Limits(max_keepalive_connections=0),
            timeout=httpx.Timeout(60.0, connect=10.0),
        ),
    )


RETRYABLE = (anthropic.APIConnectionError, anthropic.APITimeoutError,
             anthropic.RateLimitError, anthropic.InternalServerError)


class _CountingMessages:
    def __init__(self, inner):
        self._inner = inner

    def create(self, **kw):
        for attempt in range(2):
            _bump()
            try:
                return self._inner.create(**kw)
            except RETRYABLE:
                if attempt == 1:
                    raise
                time.sleep(5)


class _CountingClient:
    def __init__(self, inner):
        self.messages = _CountingMessages(inner.messages)


def sonnet_answer(client, messages) -> str:
    for attempt in range(2):
        _bump()
        try:
            with client.messages.stream(model=config.CHAT_MODEL, max_tokens=config.CHAT_MAX_TOKENS,
                                        system=chat_module._SYSTEM, messages=messages,
                                        **config.CHAT_PARAMS) as s:
                return s.get_final_text()
        except RETRYABLE:
            if attempt == 1:
                raise
            time.sleep(5)


# ── Data ──────────────────────────────────────────────────────────────────

def questions() -> list[dict]:
    return [json.loads(l) for l in QFILE.read_text().splitlines() if l.strip()]


def rewrites() -> dict:
    return json.loads(RWFILE.read_text())


# ── Optional: reranker and alternative embedder (requirements-eval.txt) ───

_reranker = _bge = _bge_coll = None
BGE_COLLECTION = config.COLLECTION_NAME + "_bge_base"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _device() -> str:
    import torch
    if torch.backends.mps.is_available():
        return "mps"
    return "cuda" if torch.cuda.is_available() else "cpu"


def rerank_hits(query: str, hits: list[dict]) -> list[dict]:
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("BAAI/bge-reranker-base", max_length=512, device=_device())
    scores = _reranker.predict([(query, h["text"]) for h in hits], batch_size=16)
    for h, sc in zip(hits, scores):
        h["rerank_score"] = float(sc)
    return sorted(hits, key=lambda h: h["rerank_score"], reverse=True)


def bge_search(query: str, n_results: int = 8, filters=None) -> list[dict]:
    global _bge, _bge_coll
    if _bge is None:
        import chromadb
        from sentence_transformers import SentenceTransformer
        _bge = SentenceTransformer("BAAI/bge-base-en-v1.5", device=_device())
        _bge.max_seq_length = 512
        _bge_coll = chromadb.PersistentClient(path=config.CHROMA_PATH).get_collection(BGE_COLLECTION)
    v = _bge.encode([BGE_QUERY_PREFIX + query], normalize_embeddings=True).tolist()
    r = _bge_coll.query(query_embeddings=v, n_results=min(n_results, _bge_coll.count()),
                        include=["documents", "metadatas", "distances"])
    return [{"id": i, "text": d, "metadata": m, "distance": dist}
            for i, d, m, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0])]


# ── Retrieval variants ────────────────────────────────────────────────────

VARIANTS = {
    "baseline": dict(keyword=False, balance=False),
    "hybrid": dict(keyword=True, balance=False),
    "balance": dict(keyword=False, balance=True),
    "hybrid_balance": dict(keyword=True, balance=True),
    "rerank": dict(keyword=False, balance=False, rerank=True),
    "hybrid_balance_rerank": dict(keyword=True, balance=True, rerank=True),
    "bge": dict(keyword=False, balance=False, embed="bge"),
    "bge_hybrid_balance": dict(keyword=True, balance=True, embed="bge"),
}


def apply_cap(hits: list[dict], n: int) -> list[dict]:
    out, k = [], 0
    for h in hits:
        if h["metadata"].get("source_type") == embedder.CAPPED_TYPE:
            if k >= embedder.REPORT_CAP:
                continue
            k += 1
        out.append(h)
        if len(out) == n:
            break
    return out


def retrieve(queries: list[str], keyword=True, balance=True, rerank=False, embed="minilm") -> list[dict]:
    original_search = embedder.search
    if embed == "bge":
        embedder.search = bge_search
    try:
        hits = embedder.search_multi(
            queries,
            n_results=40 if rerank else N_FINAL,
            keyword=keyword,
            report_cap=None if (rerank or not balance) else embedder.REPORT_CAP,
            own_boost=embedder.OWN_BOOST if balance else 1.0,
        )
    finally:
        embedder.search = original_search
    if rerank and hits:
        hits = rerank_hits(queries[0], hits)
        hits = apply_cap(hits, N_FINAL) if balance else hits[:N_FINAL]
    return hits


def fact_ok(text: str, fact: str) -> bool:
    t = text.lower()
    return any(alt.strip().lower() in t for alt in fact.split("|"))


def score_retrieval(variant: str) -> None:
    RUNS.mkdir(exist_ok=True)
    qs, rw, rows, t0 = questions(), rewrites(), [], time.time()
    for q in qs:
        res = retrieve(rw[str(q["id"])], **VARIANTS[variant])
        sources = [r["metadata"].get("source") for r in res]
        rows.append({
            "id": q["id"], "type": q["type"], "gold": q["gold"], "sources": sources,
            "types": [r["metadata"].get("source_type") for r in res],
            "hit8": bool(q["gold"]) and any(s in q["gold"] for s in sources),
            "hit1": bool(q["gold"]) and bool(sources) and sources[0] in q["gold"],
            "support8": bool(q["gold"]) and all(fact_ok(" ".join(r["text"] for r in res), f) for f in q["facts"]),
            "results": [{"id": r["id"], "text": r["text"], "metadata": r["metadata"],
                         "distance": r.get("distance", 1.0)} for r in res],
        })
    summ = summarize(rows)
    summ["seconds"] = round(time.time() - t0, 1)
    (RUNS / f"{variant}{TAG}.retrieval.json").write_text(json.dumps(rows))
    (RUNS / f"{variant}{TAG}.retrieval.summary.json").write_text(json.dumps(summ, indent=1))
    print(variant + TAG, json.dumps(summ))


def summarize(rows: list[dict]) -> dict:
    ans = [r for r in rows if r["gold"]]
    by: dict = {}
    for r in ans:
        b = by.setdefault(r["type"], {"n": 0, "hit8": 0, "hit1": 0})
        b["n"] += 1
        b["hit8"] += r["hit8"]
        b["hit1"] += r["hit1"]
    return {
        "answerable": len(ans),
        "hit8": sum(r["hit8"] for r in ans),
        "hit1": sum(r["hit1"] for r in ans),
        "support8": sum(r["support8"] for r in ans),
        "by_type": dict(sorted(by.items())),
    }


# ── Answers ───────────────────────────────────────────────────────────────

DECLINE = re.compile(r"don.t have anything|nothing in my (corpus|library)|not in (my|the) (corpus|library)"
                     r"|(excerpts|context)[^.]{0,60}(don.t|do not|doesn.t|does not)[^.]{0,40}"
                     r"(cover|contain|address|include|mention)", re.I)
CITE = re.compile(r"\[\d+\]")


def answer(variant: str) -> None:
    rows = json.loads((RUNS / f"{variant}{TAG}.retrieval.json").read_text())
    qs = {q["id"]: q for q in questions()}
    client = make_client()
    path = RUNS / f"{variant}{TAG}.answers.jsonl"
    done = {json.loads(l)["id"] for l in path.read_text().splitlines()} if path.exists() else set()
    with path.open("a") as f:
        for r in rows:
            if r["id"] in done:
                continue
            q = qs[r["id"]]
            if r["results"]:
                ctx = chat_module._build_context(r["results"])
                msg = f"Context excerpts:\n\n{ctx}\n\n---\n\nQuestion: {q['q']}"
                text = sonnet_answer(client, [{"role": "user", "content": msg}])
            else:
                text = "(no passages retrieved; model not called)"
            f.write(json.dumps({"id": r["id"], "type": q["type"], "answer": text}) + "\n")
            f.flush()
    grade(variant)


def grade(variant: str) -> None:
    qs = {q["id"]: q for q in questions()}
    ans = [json.loads(l) for l in (RUNS / f"{variant}{TAG}.answers.jsonl").read_text().splitlines()]
    answerable = [a for a in ans if qs[a["id"]]["gold"]]
    off = [a for a in ans if not qs[a["id"]]["gold"]]
    summ = {
        "answerable": len(answerable),
        "facts_ok": sum(all(fact_ok(a["answer"], f) for f in qs[a["id"]]["facts"]) for a in answerable),
        "cited": sum(bool(CITE.search(a["answer"])) for a in answerable),
        "unanswerable": len(off),
        # Declined = the model said the library doesn't cover it, or nothing was retrieved at all
        # (the app then shows "nothing matched" without calling the model).
        "declined": sum(a["answer"].startswith("(no passages retrieved")
                        or (bool(DECLINE.search(a["answer"][:600])) and not CITE.search(a["answer"])) for a in off),
    }
    (RUNS / f"{variant}{TAG}.answers.summary.json").write_text(json.dumps(summ, indent=1))
    print(variant + TAG, "answers", json.dumps(summ))


def do_rewrite() -> None:
    cache = json.loads(RWFILE.read_text()) if RWFILE.exists() else {}
    query_rewriter._client = _CountingClient(make_client())
    for q in questions():
        if str(q["id"]) not in cache:
            cache[str(q["id"])] = query_rewriter.rewrite(q["q"])
            RWFILE.write_text(json.dumps(cache, indent=1))
    print(f"rewrites cached: {len(cache)}; API calls so far: {_calls()}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "rewrite":
        do_rewrite()
    elif cmd == "retrieve":
        score_retrieval(sys.argv[2])
    elif cmd == "answer":
        answer(sys.argv[2])
    elif cmd == "grade":
        grade(sys.argv[2])
    else:
        for p in sorted(RUNS.glob("*.summary.json")):
            print(p.name, p.read_text())
