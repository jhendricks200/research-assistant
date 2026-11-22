"""
FastAPI server for the web chat UI.

Wraps the existing RAG stack (embedder + chat helpers) and serves a static
single-page frontend from ./web/.

Endpoints:
    GET  /                  → web/index.html
    GET  /static/*          → web/* (css, js, fonts, favicon)
    GET  /api/stats         → corpus counts
    GET  /api/topics         → distinct topics with counts
    POST /api/ask           → SSE stream of {sources, delta, done, error}

Reuses:
    embedder.search_multi / embedder.topic_filter / embedder.collection_stats / embedder.prewarm
    query_rewriter.rewrite
    chat._build_context / chat._SYSTEM
    config.ANTHROPIC_API_KEY / config.CHAT_MODEL

Terminal chat (`python main.py chat`) is untouched.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import chat as chat_module
import embedder
import query_rewriter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("research_assistant.server")

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DIR = PROJECT_ROOT / "web"

app = FastAPI(title="Research Assistant", version="1.0.0")

# Pre-warm ONNX model at startup so the first /api/ask doesn't stall.
@app.on_event("startup")
def _startup() -> None:
    try:
        embedder.prewarm()
    except SystemExit as exc:
        logger.error("Embedder prewarm failed: %s", exc)


# ── Static files ──────────────────────────────────────────────────────────

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
def index() -> FileResponse:
    index_html = WEB_DIR / "index.html"
    if not index_html.exists():
        raise HTTPException(status_code=404, detail="web/index.html not found")
    return FileResponse(
        index_html,
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    fav = WEB_DIR / "favicon.png"
    if not fav.exists():
        raise HTTPException(status_code=404)
    return FileResponse(fav)


# ── Cached stats / topics ──────────────────────────────────────────────────

_STATS_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_TOPIC_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_CACHE_TTL = 300  # 5 minutes


def _compute_stats() -> dict[str, Any]:
    """Total chunks, distinct articles, topics breakdown."""
    base = embedder.collection_stats()
    collection = embedder._get_collection()
    total = collection.count()
    articles = 0
    if total > 0:
        sources = {m.get("source") for m in embedder.iter_metadatas(collection) if m.get("source")}
        articles = len(sources)
    return {
        "chunks": base["total_chunks"],
        "articles": articles,
        "topics": base["topics"],
    }


def _get_stats() -> dict[str, Any]:
    now = time.time()
    if _STATS_CACHE["data"] is None or now - _STATS_CACHE["at"] > _CACHE_TTL:
        _STATS_CACHE["data"] = _compute_stats()
        _STATS_CACHE["at"] = now
    return _STATS_CACHE["data"]


@app.get("/api/stats")
def stats_endpoint() -> dict[str, Any]:
    return _get_stats()


@app.get("/api/topics")
def topics_endpoint() -> list[dict[str, Any]]:
    now = time.time()
    if _TOPIC_CACHE["data"] is None or now - _TOPIC_CACHE["at"] > _CACHE_TTL:
        topics = _get_stats()["topics"]
        _TOPIC_CACHE["data"] = [{"name": k, "count": v} for k, v in topics.items()]
        _TOPIC_CACHE["at"] = now
    return _TOPIC_CACHE["data"]


# ── Ask (SSE stream) ──────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    history: list[HistoryMessage] = Field(default_factory=list)
    topic: str | None = None


def _sse(event: str, data: Any) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


@app.post("/api/ask")
async def ask_endpoint(req: AskRequest) -> StreamingResponse:
    async def stream():
        # 1. Retrieve first so the rail populates before the answer streams.
        try:
            filters = (
                embedder.topic_filter(req.topic)
                if req.topic and req.topic != "All topics"
                else None
            )
            history_msgs = [m.model_dump() for m in req.history]
            queries = await asyncio.to_thread(
                query_rewriter.rewrite, req.question, history_msgs
            )
            results = await asyncio.to_thread(
                embedder.search_multi, queries, 8, filters
            )
        except Exception as exc:
            logger.exception("Retrieval failed")
            yield _sse("error", {"code": "retrieval", "message": str(exc)})
            return

        if not results:
            yield _sse(
                "error",
                {
                    "code": "empty",
                    "message": (
                        "Nothing in the corpus matched this question. "
                        "Try different terms, or check your topic filter."
                    ),
                },
            )
            return

        # Send sources first - rail updates immediately.
        yield _sse("sources", results)

        # 2. Build the grounded prompt using the existing chat helpers.
        context = chat_module._build_context(results)
        user_message = (
            f"Context excerpts:\n\n{context}\n\n---\n\nQuestion: {req.question}"
        )

        # Trim history (MAX_HISTORY pairs) and append new user turn.
        max_msgs = chat_module.MAX_HISTORY * 2
        history_msgs = history_msgs[-max_msgs:]
        history_msgs.append({"role": "user", "content": user_message})

        # 3. Stream Claude answer.
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def produce() -> None:
            try:
                with client.messages.stream(
                    model=config.CHAT_MODEL,
                    max_tokens=1500,
                    system=chat_module._SYSTEM,
                    messages=history_msgs,
                ) as s:
                    for delta in s.text_stream:
                        asyncio.run_coroutine_threadsafe(
                            queue.put(("delta", delta)), loop
                        )
                asyncio.run_coroutine_threadsafe(queue.put(("done", None)), loop)
            except anthropic.RateLimitError as exc:
                asyncio.run_coroutine_threadsafe(
                    queue.put(
                        (
                            "error",
                            {
                                "code": "rate_limit",
                                "message": (
                                    "Claude is rate-limiting requests. Wait a few "
                                    "seconds and ask again - your question isn't lost."
                                ),
                            },
                        )
                    ),
                    loop,
                )
            except anthropic.AuthenticationError:
                asyncio.run_coroutine_threadsafe(
                    queue.put(
                        (
                            "error",
                            {
                                "code": "auth",
                                "message": (
                                    "Anthropic rejected the API key. Check "
                                    "ANTHROPIC_API_KEY in your .env file."
                                ),
                            },
                        )
                    ),
                    loop,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Claude stream failed")
                asyncio.run_coroutine_threadsafe(
                    queue.put(
                        (
                            "error",
                            {
                                "code": "upstream",
                                "message": (
                                    "Claude is unavailable right now. Your question "
                                    "is saved - try again in a moment."
                                ),
                            },
                        )
                    ),
                    loop,
                )

        producer = asyncio.create_task(asyncio.to_thread(produce))

        try:
            while True:
                event, payload = await queue.get()
                if event == "done":
                    yield _sse("done", {})
                    return
                if event == "error":
                    yield _sse("error", payload)
                    return
                if event == "delta":
                    yield _sse("delta", payload)
        finally:
            producer.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
