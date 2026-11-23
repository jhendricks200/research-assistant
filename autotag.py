"""
Auto-tagging for library documents.

Sends articles missing frontmatter fields to Claude Haiku and writes
the result back into the file. Only fills fields that are absent or empty.
"""

import json
import logging
from pathlib import Path

import anthropic

import config
import normalizer
import parser

logger = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


# ── Prompt ─────────────────────────────────────────────────────────────────

_SYSTEM = """\
You label documents for a personal research library.
Given a document title and excerpt, return a JSON object with these fields:

- topics: list of 1-4 broad topics (e.g. ["Retrieval", "Evaluation"])
- tags: list of 3-8 specific keyword tags (e.g. ["BM25", "reciprocal rank fusion", "ChromaDB"])
- entities: list of named things the document is about (tools, libraries, products, organizations)
- status: one of "published", "draft", or "archived"
- source_type: one of "article", "analysis", "note", "report", "reference"

Return ONLY valid JSON. No explanation, no markdown fences."""


def _build_prompt(title: str, excerpt: str) -> str:
    return f"Title: {title}\n\nExcerpt:\n{excerpt[:1200]}"


# ── Core logic ─────────────────────────────────────────────────────────────

def _needs_tagging(frontmatter: dict) -> bool:
    """Return True if any autotag field is missing or empty."""
    for field in config.AUTOTAG_FIELDS:
        val = frontmatter.get(field)
        if val is None or val == "" or val == [] or val == {}:
            return True
    return False


def _call_haiku(title: str, excerpt: str) -> dict:
    """Call Claude Haiku and return parsed JSON tags."""
    client = _get_client()
    response = client.messages.create(
        model=config.AUTOTAG_MODEL,
        max_tokens=512,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _build_prompt(title, excerpt)}],
        **config.HAIKU_PARAMS,
    )
    raw = config.text_of(response).strip()

    # Strip markdown fences if model adds them anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


def autotag_file(filepath: Path) -> dict:
    """
    Read a .md file, fill any missing frontmatter fields via Haiku,
    write the result back, and return the updated frontmatter dict.

    If all fields are already present, returns the existing frontmatter
    without calling the API.
    """
    frontmatter, body = parser.extract_frontmatter(filepath)

    if not _needs_tagging(frontmatter):
        return frontmatter

    title = str(frontmatter.get("title", filepath.stem))
    logger.info("Auto-tagging: %s", filepath.name)

    try:
        tags = _call_haiku(title, body)
    except (json.JSONDecodeError, anthropic.APIError) as exc:
        logger.warning("Autotag failed for %s: %s", filepath.name, exc)
        return frontmatter

    # Normalize topics and tags
    if "topics" in tags and isinstance(tags["topics"], list):
        tags["topics"] = normalizer.normalize_topics(tags["topics"])
    if "tags" in tags and isinstance(tags["tags"], list):
        tags["tags"] = normalizer.normalize_tags(tags["tags"])
    if "entities" in tags and isinstance(tags["entities"], list):
        tags["entities"] = normalizer.normalize_tags(tags["entities"])

    # Only fill missing fields - never overwrite existing values
    for field in config.AUTOTAG_FIELDS:
        existing = frontmatter.get(field)
        if (existing is None or existing == "" or existing == []) and field in tags:
            frontmatter[field] = tags[field]

    parser.write_frontmatter(filepath, frontmatter, body)
    logger.info("Wrote frontmatter: %s", filepath.name)
    return frontmatter
