"""
Project-wide configuration. Loads .env from the project folder and exposes constants.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env", override=True)

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
assert ANTHROPIC_API_KEY, "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."

# ── Paths ──────────────────────────────────────────────────────────────────

# Folder of markdown documents to index. Relative paths resolve from the project folder.
DOCS_PATH = Path(os.environ.get("DOCS_PATH", "samples/library"))
if not DOCS_PATH.is_absolute():
    DOCS_PATH = PROJECT_ROOT / DOCS_PATH
CHROMA_PATH = os.environ.get("CHROMA_PATH", str(PROJECT_ROOT / "chroma_db"))

# ── ChromaDB ───────────────────────────────────────────────────────────────

COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "documents")

# ── Models ─────────────────────────────────────────────────────────────────

# Haiku does the small jobs (auto-tagging, query rewrites, passage context);
# Sonnet writes the answers.
AUTOTAG_MODEL = os.environ.get("AUTOTAG_MODEL", "claude-haiku-5-5")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "claude-sonnet-5-5")
# Sonnet 5.5 always thinks before answering; effort sets how much (low, medium, high).
CHAT_EFFORT = os.environ.get("CHAT_EFFORT", "medium")
CHAT_MAX_TOKENS = 8000  # covers thinking plus the answer

# Haiku's jobs are short and mechanical, so they run without extended thinking.
HAIKU_PARAMS = {"thinking": {"type": "disabled"}}
CHAT_PARAMS = {"output_config": {"effort": CHAT_EFFORT}}


def text_of(response) -> str:
    """The text of a Messages API response. Newer models can put a thinking block first."""
    return "".join(b.text for b in response.content if getattr(b, "type", "") == "text")

# ── Contextual retrieval (see README, "Contextual retrieval") ─────────────
# When on, Haiku writes a short note placing each passage within its document,
# and that note is embedded and keyword-indexed together with the passage.
CONTEXTUAL_CHUNKS = os.environ.get("CONTEXTUAL_CHUNKS", "false").strip().lower() in ("1", "true", "yes", "on")
CONTEXT_WORKERS = int(os.environ.get("CONTEXT_WORKERS", "8"))  # parallel Haiku calls per document

# Passage size in tokens. MiniLM reads only the first 256 tokens of what it
# embeds, so with contextual retrieval on, smaller passages keep the end of
# each passage inside that window.
CHUNK_SIZE_TOKENS = int(os.environ.get("CHUNK_SIZE_TOKENS", "300"))

# ── Frontmatter fields that autotag fills when missing ────────────────────

AUTOTAG_FIELDS = {"topics", "tags", "entities", "status", "source_type"}

# ── Source balancing (see README, "Results") ──────────────────────────────
# One very large source type can crowd every other type out of the passages the
# model sees. Cap it, and give a small boost to the types you care most about.
CAPPED_SOURCE_TYPE = os.environ.get("CAPPED_SOURCE_TYPE", "report")
CAPPED_SOURCE_MAX = int(os.environ.get("CAPPED_SOURCE_MAX", "3"))
BOOSTED_SOURCE_TYPES = set(filter(None, os.environ.get("BOOSTED_SOURCE_TYPES", "article,analysis").split(",")))
BOOST_FACTOR = float(os.environ.get("BOOST_FACTOR", "1.5"))
