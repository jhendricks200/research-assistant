"""
RAG chat interface over the document library.

Retrieval pipeline:
  1. query_rewriter.rewrite() - Haiku turns the user's question into a standalone
     version plus alternate phrasings (expanded acronyms, synonym swaps, entity
     surfacing). Resolves pronouns/anaphora from conversation history.
  2. embedder.search_multi() - runs every rewritten query, fuses results via
     reciprocal rank fusion, drops low-similarity noise (sim < 0.2).
  3. Sonnet generates the answer with a relaxed grounding prompt: answer what
     the context supports, flag gaps explicitly, only refuse when context is
     completely unrelated.
"""

import logging
from pathlib import Path

import anthropic

import config
import embedder
import query_rewriter

logger = logging.getLogger(__name__)

MAX_HISTORY = 10  # conversation exchange pairs to keep (20 messages total)

_SYSTEM = """\
You are a research assistant for a private document library.
You answer questions using the retrieved excerpts below.

Rules:
1. Prefer the retrieved excerpts for any specific factual claim. If an excerpt directly supports a point, cite it.
2. Answer what the context supports. If the context only partially covers the question, answer the part it covers and explicitly flag what's missing (e.g., "The excerpts cover X but don't address Y - that would need more sources.").
3. Only refuse outright when the context is completely unrelated to the question. In that case say: "I don't have anything in my corpus on that - the retrieved excerpts cover [brief summary of what they're about instead]."
4. Cite sources with bracket markers that match the excerpt numbers, e.g. [1], [2], [3].
   - Place the marker at the end of the relevant clause or sentence.
   - Use multiple markers when a sentence draws on multiple excerpts: [1][3].
   - NEVER write parenthetical citations like (Source: "Title" - Topic, "Section").
   - NEVER name the article inline - the brackets do that work.
   - The reader sees a side rail with the full source for each numbered excerpt.
5. Be direct and analytical. Use bullet points when listing multiple items.
6. For follow-up questions, use conversation history for context but still cite retrieved excerpts for any new factual claims."""


def _build_context(results: list[dict]) -> str:
    parts = []
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        title = meta.get("title") or Path(meta.get("source", "unknown")).stem
        topic = meta.get("topics", "")
        section = meta.get("section", "")
        location = f'"{section}"' if section and section not in ("(intro)", "(full document)") else ""
        header = f"[{title} | {topic}{' | ' + location if location else ''}]"
        parts.append(f"--- Excerpt {i} {header} ---\n{r['text']}")
    return "\n\n".join(parts)


def ask(
    question: str,
    history: list[dict] | None = None,
    n_results: int = 8,
    filters: dict | None = None,
    debug: bool = False,
) -> tuple[str, list[dict]]:
    """
    Ask a question against the document library.

    Args:
        question: The user's question.
        history: Conversation history list of {"role", "content"} dicts.
        n_results: Number of chunks to pass to the LLM after fusion (default 8).
        filters: Optional ChromaDB where-filter (e.g. {"status": "published"}).
        debug: If True, print rewritten queries and retrieved chunk scores.

    Returns:
        (answer_text, updated_history)
    """
    if history is None:
        history = []

    # 1. Rewrite the question into retrieval-optimized variants (standalone +
    #    alternate phrasings). History is used for anaphora resolution.
    queries = query_rewriter.rewrite(question, history=history)
    if debug:
        print("\n[debug] Rewritten queries:")
        for i, q in enumerate(queries, 1):
            print(f"  {i}. {q}")

    # 2. Multi-query retrieval with RRF fusion + similarity threshold.
    results = embedder.search_multi(
        queries,
        n_results=n_results,
        filters=filters,
    )

    if debug:
        print(f"\n[debug] Fused {len(results)} chunks after RRF:")
        for i, r in enumerate(results, 1):
            meta = r["metadata"]
            title = meta.get("title") or Path(meta.get("source", "?")).stem
            sim = round(1 - r["distance"], 3)
            fused = round(r.get("fused_score", 0), 4)
            print(f"  {i}. sim={sim} fused={fused}  {title[:60]}")

    if not results:
        answer = (
            "I don't have any articles in the knowledge base yet. "
            "Run `python main.py ingest` first."
        )
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        return answer, history

    context = _build_context(results)
    user_message = f"Context excerpts:\n\n{context}\n\n---\n\nQuestion: {question}"

    history.append({"role": "user", "content": user_message})

    # Trim to last MAX_HISTORY exchange pairs
    max_msgs = MAX_HISTORY * 2
    if len(history) > max_msgs:
        history = history[-max_msgs:]

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.CHAT_MODEL,
        max_tokens=config.CHAT_MAX_TOKENS,
        system=_SYSTEM,
        messages=history,
        **config.CHAT_PARAMS,
    )
    answer = config.text_of(response)
    history.append({"role": "assistant", "content": answer})

    return answer, history


def interactive(filters: dict | None = None, debug: bool = False) -> None:
    """Run an interactive RAG chat session in the terminal."""
    print("Research Assistant")
    print("Type your question, or 'quit' to exit.")
    if debug:
        print("[debug mode on - rewrites and retrieval scores will be printed]")
    print("=" * 55)

    history: list[dict] = []

    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        print("\nSearching the library...")
        answer, history = ask(question, history, filters=filters, debug=debug)
        print(f"\nAssistant: {answer}")
