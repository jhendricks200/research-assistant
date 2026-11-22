"""
Synonym normalization for tags, topics and body text.

Maps variant spellings to one canonical form so the vector store does not
treat "LLM", "large language model" and "large language models" as separate
concepts. Applied to body text before embedding and to auto-generated tags.
Edit _SYNONYMS for your own corpus; keys are lowercase variants.
"""

import re

_SYNONYMS: dict[str, str] = {
    "large language model": "LLM",
    "large language models": "LLM",
    "llms": "LLM",
    "retrieval augmented generation": "RAG",
    "retrieval-augmented generation": "RAG",
    "vector database": "vector store",
    "vector databases": "vector store",
    "vector db": "vector store",
}


def _normalize_token(token: str) -> str:
    """Return canonical form for a single tag/topic token, or the original if no match."""
    return _SYNONYMS.get(token.lower().strip(), token.strip())


def normalize_tags(tags: list[str]) -> list[str]:
    """Normalize and dedupe a tag list, preserving order."""
    seen, out = set(), []
    for t in tags:
        c = _normalize_token(str(t))
        if c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def normalize_topics(topics: list[str]) -> list[str]:
    return normalize_tags(topics)


_BODY_RE = None


def normalize_text(text: str) -> str:
    """Replace synonym phrases in body text with their canonical form (whole words, case-insensitive)."""
    global _BODY_RE
    if not _SYNONYMS:
        return text
    if _BODY_RE is None:
        keys = sorted(_SYNONYMS, key=len, reverse=True)
        _BODY_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in keys) + r")\b", re.IGNORECASE)
    return _BODY_RE.sub(lambda m: _SYNONYMS[m.group(0).lower()], text)
