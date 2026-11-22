"""
Research Assistant: CLI entry point.

Commands:
  ingest [--all]              Ingest all .md files in the library
  watch                       Start file watcher (blocking)
  query <text> [--topic TOPIC]  Semantic search, print top results
  stats                       ChromaDB collection stats
  chat [--topic TOPIC]          Interactive RAG chat session
"""

import argparse
import logging
import sys
from pathlib import Path

import config  # noqa: F401 - loads .env as a side effect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def cmd_ingest(args: argparse.Namespace) -> None:
    import pipeline

    library = config.DOCS_PATH
    print(f"Ingesting library: {library}")
    results = pipeline.run_all(library)

    import embedder
    if not embedder.KEYWORD_INDEX_PATH.exists():
        n = embedder.build_keyword_index()
        print(f"Built keyword index: {n} chunks")

    total_files = len([r for r in results if not r["skipped"]])
    total_added = sum(r["chunks_added"] for r in results)
    total_tagged = len([r for r in results if r.get("tagged")])

    print(f"\n{'─' * 50}")
    print(f"Files processed : {total_files}")
    print(f"Chunks added    : {total_added}")
    print(f"Auto-tagged     : {total_tagged}")
    print(f"{'─' * 50}")

    for r in results:
        if not r["skipped"]:
            tag_flag = " [tagged]" if r.get("tagged") else ""
            print(f"  {r['file']}: {r['chunks_added']} chunks{tag_flag}")


def cmd_keywords(_args: argparse.Namespace) -> None:
    import embedder
    print(f"Keyword index rebuilt: {embedder.build_keyword_index()} chunks")


def cmd_watch(_args: argparse.Namespace) -> None:
    import watcher

    watcher.watch()


def cmd_query(args: argparse.Namespace) -> None:
    import embedder

    filters = embedder.topic_filter(args.topic) if args.topic else None

    results = embedder.search(args.text, n_results=args.n, filters=filters)

    if not results:
        print("No results. Have you run `python main.py ingest` yet?")
        return

    print(f"\nTop {len(results)} results for: \"{args.text}\"\n{'─' * 55}")
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        title = meta.get("title") or Path(meta.get("source", "?")).stem
        topic = meta.get("topics", "")
        section = meta.get("section", "")
        sim = round(1 - r["distance"], 3)
        preview = r["text"][:200].replace("\n", " ")
        print(f"\n{i}. [{title}] (sim={sim})")
        if topic:
            print(f"   Topic: {topic}  |  Section: {section}")
        print(f"   {preview}...")


def cmd_stats(_args: argparse.Namespace) -> None:
    import embedder

    stats = embedder.collection_stats()
    print(f"\nCollection : {stats['collection']}")
    print(f"Total chunks: {stats['total_chunks']}")

    if stats["topics"]:
        print("\nChunks by topic:")
        for topic, count in stats["topics"].items():
            print(f"  {topic:<35} {count}")
    else:
        print("(no chunks yet - run `python main.py ingest`)")


def cmd_chat(args: argparse.Namespace) -> None:
    import chat
    import embedder

    filters = embedder.topic_filter(args.topic) if args.topic else None

    chat.interactive(filters=filters, debug=args.debug)


# ── Argument parser ────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="Research Assistant: library ingest, watch, and RAG chat",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest all .md files in the library")
    p_ingest.set_defaults(func=cmd_ingest)

    # keywords
    p_kw = sub.add_parser("keywords", help="Rebuild the BM25 keyword index from the vector store")
    p_kw.set_defaults(func=cmd_keywords)

    # watch
    p_watch = sub.add_parser("watch", help="Start file watcher (blocking)")
    p_watch.set_defaults(func=cmd_watch)

    # query
    p_query = sub.add_parser("query", help="Semantic search the knowledge base")
    p_query.add_argument("text", help="Search query")
    p_query.add_argument("--topic", default="", help="Filter by topic (optional)")
    p_query.add_argument("--n", type=int, default=5, help="Number of results (default 5)")
    p_query.set_defaults(func=cmd_query)

    # stats
    p_stats = sub.add_parser("stats", help="Show ChromaDB collection stats")
    p_stats.set_defaults(func=cmd_stats)

    # chat
    p_chat = sub.add_parser("chat", help="Interactive RAG chat session")
    p_chat.add_argument("--topic", default="", help="Filter context by topic (optional)")
    p_chat.add_argument("--debug", action="store_true", help="Print query rewrites and retrieval scores")
    p_chat.set_defaults(func=cmd_chat)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
