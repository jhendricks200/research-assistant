"""
YAML frontmatter extraction and section-level chunking for markdown files.

Splits article body by **Bold Headers** or ## Markdown headings,
then further splits long sections into ~300-token word-based chunks.
"""

import logging
import os
import re
from pathlib import Path

import yaml

import config

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────────────

WORDS_PER_TOKEN = 0.75  # conservative estimate
CHUNK_SIZE_TOKENS = config.CHUNK_SIZE_TOKENS
OVERLAP_TOKENS = 50

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Matches **Header** on its own line (Obsidian-style bold headers)
BOLD_HEADER_RE = re.compile(r"^\*\*(.+?)\*\*\s*$", re.MULTILINE)

# Matches ## Markdown headings
MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


# ── Frontmatter ────────────────────────────────────────────────────────────

def extract_frontmatter(filepath: Path) -> tuple[dict, str]:
    """
    Read a .md file and return (frontmatter_dict, body_text).

    If no frontmatter block is found, returns ({}, full_text).
    List values in frontmatter are preserved as lists.
    """
    text = filepath.read_text(encoding="utf-8", errors="replace")

    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text.strip()

    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        logger.warning("YAML parse error in %s: %s - treating as no frontmatter", filepath.name, exc)
        frontmatter = {}

    body = text[match.end():].strip()
    return frontmatter, body


def write_frontmatter(filepath: Path, frontmatter: dict, body: str) -> None:
    """
    Atomically write updated frontmatter back to a .md file, preserving body.

    Uses a temp file + os.replace() so a crash mid-write never corrupts the
    original file (os.replace is atomic on POSIX / macOS).
    """
    fm_yaml = yaml.dump(
        frontmatter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=True,
    ).rstrip()
    content = f"---\n{fm_yaml}\n---\n\n{body}\n"
    tmp = filepath.with_suffix(".md.tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, filepath)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ── Chunking helpers ───────────────────────────────────────────────────────

def _word_chunks(text: str) -> list[str]:
    """Split text into ~CHUNK_SIZE_TOKENS token chunks with overlap."""
    words = text.split()
    chunk_words = int(CHUNK_SIZE_TOKENS * WORDS_PER_TOKEN)
    overlap_words = int(OVERLAP_TOKENS * WORDS_PER_TOKEN)

    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_words
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap_words
    return chunks


def _extract_sections(body: str) -> list[tuple[str, str]]:
    """
    Split body into (heading, text) pairs.

    Priority: **Bold Headers** → ## Markdown headings → whole document.
    """
    # Try bold headers first (Obsidian style)
    bold_matches = list(BOLD_HEADER_RE.finditer(body))
    if bold_matches:
        sections = []
        for idx, m in enumerate(bold_matches):
            heading = m.group(1).strip()
            start = m.end()
            end = bold_matches[idx + 1].start() if idx + 1 < len(bold_matches) else len(body)
            section_text = body[start:end].strip()
            if section_text:
                sections.append((heading, section_text))
        # Capture preamble before first bold header
        preamble = body[: bold_matches[0].start()].strip()
        if preamble:
            sections.insert(0, ("(intro)", preamble))
        return sections

    # Fall back to ## Markdown headings
    md_matches = list(MD_HEADING_RE.finditer(body))
    if md_matches:
        sections = []
        for idx, m in enumerate(md_matches):
            heading = m.group(2).strip()
            start = m.end()
            end = md_matches[idx + 1].start() if idx + 1 < len(md_matches) else len(body)
            section_text = body[start:end].strip()
            if section_text:
                sections.append((heading, section_text))
        preamble = body[: md_matches[0].start()].strip()
        if preamble:
            sections.insert(0, ("(intro)", preamble))
        return sections

    # No headings found - treat as single section
    return [("(full document)", body.strip())]


# ── Public API ─────────────────────────────────────────────────────────────

def chunk_file(filepath: Path, frontmatter: dict, body: str) -> list[dict]:
    """
    Chunk a document body into embeddable pieces.

    Each chunk dict:
        {
            "text": str,
            "metadata": {
                "source": filename,
                "title": str,
                "topics": str,          # comma-joined list
                "tags": str,           # comma-joined list
                "entities": str,       # comma-joined list
                "published": str,
                "status": str,
                "source_type": str,
                "section": str,
                "chunk_index": int,
            }
        }
    """
    filename = filepath.name

    def _join(val) -> str:
        if isinstance(val, list):
            return ", ".join(str(v) for v in val)
        return str(val) if val is not None else ""

    base_meta = {
        "source": filename,
        "title": _join(frontmatter.get("title", filepath.stem)),
        "topics": _join(frontmatter.get("topics", "")),
        "tags": _join(frontmatter.get("tags", "")),
        "entities": _join(frontmatter.get("entities", "")),
        "published": _join(frontmatter.get("published", "")),
        "status": _join(frontmatter.get("status", "")),
        "source_type": _join(frontmatter.get("source_type", "")),
    }

    sections = _extract_sections(body)
    chunks = []
    chunk_index = 0

    for heading, section_text in sections:
        for word_chunk in _word_chunks(section_text):
            chunks.append({
                "text": word_chunk,
                "metadata": {
                    **base_meta,
                    "section": heading,
                    "chunk_index": chunk_index,
                },
            })
            chunk_index += 1

    return chunks
