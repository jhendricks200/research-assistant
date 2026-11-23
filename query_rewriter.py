"""
query_rewriter.py - Turn a raw user question into retrieval-optimized queries.

MiniLM-L6 (the embedder backing ChromaDB) is a weak, shallow encoder: it often
misses when the user's vocabulary doesn't match the corpus ("LLM" vs "language
model", "what about it?" vs the named thing it refers to). This module uses Claude
Haiku to produce:

  1. A standalone version of the question (pronouns/anaphora resolved from
     conversation history).
  2. Two alternate phrasings that expand acronyms, swap synonyms, and surface
     named entities - giving multi-query retrieval a chance to hit chunks the
     raw question would have missed.

Returned as a list of 3 query strings, passed downstream to
`embedder.search_multi()` for RRF fusion.

Failure mode: if the Haiku call fails for any reason we fall back to
`[original_question]` so chat always makes progress.
"""

import json
import logging
import re

import anthropic

import config

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None

_MAX_HISTORY_CHARS = 2000  # truncate long histories before sending to Haiku
_N_VARIATIONS = 3          # standalone + 2 alternates

_SYSTEM = """\
You rewrite research questions into retrieval queries for a vector database \
of documents, notes and reference material.

Given a user question (and optionally recent conversation history), return a \
JSON object with this exact shape:

{
  "standalone": "<the question rewritten so it makes sense without history \
- resolve pronouns, fill in referents>",
  "variations": [
    "<alternate phrasing #1 - expand acronyms, swap synonyms>",
    "<alternate phrasing #2 - surface named entities / proper nouns>"
  ]
}

Rules:
- standalone MUST be a complete question, answerable without seeing prior turns.
- Each variation should retrieve DIFFERENT but related chunks - vary the \
vocabulary, not just word order.
- Expand well-known acronyms (RAG → retrieval-augmented generation; \
BM25 → keyword ranking).
- If the question uses an informal or shortened name for something, include \
the full name in at least one variation.
- Keep each query under 25 words.
- Return ONLY valid JSON. No markdown fences, no explanation."""


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _format_history(history: list[dict] | None) -> str:
    """Render recent history as a compact transcript for the rewriter prompt."""
    if not history:
        return ""
    lines = []
    for msg in history[-6:]:  # last 3 exchanges
        role = msg.get("role", "?")
        content = msg.get("content", "")
        # Strip the "Context excerpts:" prefix that chat.py prepends
        if "Question:" in content:
            content = content.rsplit("Question:", 1)[-1].strip()
        content = content.strip()
        if len(content) > 400:
            content = content[:400] + "…"
        lines.append(f"{role}: {content}")
    transcript = "\n".join(lines)
    if len(transcript) > _MAX_HISTORY_CHARS:
        transcript = transcript[-_MAX_HISTORY_CHARS:]
    return transcript


def _extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a Haiku response, tolerating stray wrapping."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to grabbing the first {...} blob
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None


def rewrite(
    question: str,
    history: list[dict] | None = None,
) -> list[str]:
    """
    Return a list of retrieval queries for the given question.

    The first entry is always a standalone version of the user's question.
    Additional entries are alternate phrasings to improve recall.

    If the Haiku call fails or returns malformed JSON, returns `[question]`.
    """
    question = question.strip()
    if not question:
        return []

    user_content_parts = []
    transcript = _format_history(history)
    if transcript:
        user_content_parts.append(f"Recent conversation:\n{transcript}")
    user_content_parts.append(f"Current question: {question}")
    user_content = "\n\n".join(user_content_parts)

    try:
        response = _get_client().messages.create(
            model=config.AUTOTAG_MODEL,
            max_tokens=400,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            **config.HAIKU_PARAMS,
        )
        raw = config.text_of(response)
    except Exception as exc:
        logger.warning("Query rewrite failed: %s - falling back to raw question", exc)
        return [question]

    data = _extract_json(raw)
    if not data or not isinstance(data, dict):
        logger.warning("Query rewrite returned unparseable JSON: %r", raw[:200])
        return [question]

    queries: list[str] = []
    standalone = (data.get("standalone") or "").strip()
    if standalone:
        queries.append(standalone)

    for var in data.get("variations") or []:
        if isinstance(var, str) and var.strip():
            queries.append(var.strip())

    # Dedupe case-insensitively, preserve order, cap at _N_VARIATIONS
    seen: set[str] = set()
    deduped: list[str] = []
    for q in queries:
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)
        if len(deduped) >= _N_VARIATIONS:
            break

    # Always include the original question as a safety net so we never lose
    # the user's exact phrasing - caller will dedupe at the fusion layer.
    if question.lower() not in seen:
        deduped.append(question)

    return deduped or [question]
