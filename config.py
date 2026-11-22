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

AUTOTAG_MODEL = "claude-haiku-4-5-20251001"
CHAT_MODEL = "claude-sonnet-4-6"

# ── Frontmatter fields that autotag fills when missing ────────────────────

AUTOTAG_FIELDS = {"topics", "tags", "entities", "status", "source_type"}

# ── Source balancing (see README, "Results") ──────────────────────────────
# One very large source type can crowd every other type out of the passages the
# model sees. Cap it, and give a small boost to the types you care most about.
CAPPED_SOURCE_TYPE = os.environ.get("CAPPED_SOURCE_TYPE", "report")
CAPPED_SOURCE_MAX = int(os.environ.get("CAPPED_SOURCE_MAX", "3"))
BOOSTED_SOURCE_TYPES = set(filter(None, os.environ.get("BOOSTED_SOURCE_TYPES", "article,analysis").split(",")))
BOOST_FACTOR = float(os.environ.get("BOOST_FACTOR", "1.5"))
