"""
Pipeline orchestration: parse → autotag → normalize → chunk → embed.

Each .md file in the library is processed independently.
"""

import hashlib
import json
import logging
from pathlib import Path

import autotag
import embedder
import normalizer
import parser
import config

logger = logging.getLogger(__name__)

# path -> sha256 of the file as last embedded. A full ingest used to delete
# and re-embed every file on every run (days of work at 30,000+ files); now a file is
# processed only when its bytes changed since it was last embedded.
MANIFEST_PATH = Path(config.CHROMA_PATH) / "ingest_manifest.json"


def _load_manifest() -> dict:
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_manifest(manifest: dict) -> None:
    tmp = MANIFEST_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest), encoding="utf-8")
    tmp.replace(MANIFEST_PATH)


def _file_hash(filepath: Path) -> str:
    return hashlib.sha256(filepath.read_bytes()).hexdigest()


def _already_embedded(filepath: Path) -> bool:
    """Chunks for this file exist in ChromaDB (used once, to seed the
    manifest from what earlier runs embedded)."""
    res = embedder._get_collection().get(where={"source": filepath.name},
                                         limit=1)
    return bool(res["ids"])


def run_file(filepath: Path) -> dict:
    """
    Process a single .md file end-to-end.

    Returns a stats dict:
        {"file": name, "chunks_added": int, "tagged": bool, "skipped": bool}
    """
    if not filepath.exists():
        logger.warning("File not found: %s", filepath)
        return {"file": filepath.name, "chunks_added": 0, "tagged": False, "skipped": True}

    if filepath.suffix.lower() != ".md":
        return {"file": filepath.name, "chunks_added": 0, "tagged": False, "skipped": True}

    logger.info("Processing: %s", filepath.name)

    # 1. Autotag (fills missing frontmatter, writes back to file)
    tagged = autotag._needs_tagging(parser.extract_frontmatter(filepath)[0])
    autotag.autotag_file(filepath)

    # 2. Re-read after autotag (file may have been updated)
    fm, body = parser.extract_frontmatter(filepath)

    # 3. Normalize body text before embedding
    body_normalized = normalizer.normalize_text(body)

    # 4. Chunk
    chunks = parser.chunk_file(filepath, fm, body_normalized)
    if not chunks:
        logger.warning("No chunks produced for %s", filepath.name)
        return {"file": filepath.name, "chunks_added": 0, "tagged": tagged, "skipped": False}

    # 5. Delete stale chunks then re-embed (ensures edits and header renames take effect)
    embedder.delete_file(str(filepath))
    added = embedder.add_chunks(chunks, filepath=str(filepath))
    logger.info("  → %d chunks added (file: %s)", added, filepath.name)

    return {"file": filepath.name, "chunks_added": added, "tagged": tagged, "skipped": False}


def run_all(library_path: Path | None = None) -> list[dict]:
    """
    Process all .md files in the library.

    Returns a list of per-file stat dicts.
    """
    library = library_path or config.DOCS_PATH
    if not library.exists():
        raise FileNotFoundError(f"Library not found: {library}")

    # Fail fast if embedding model is unavailable (downloads ~80 MB on first run)
    embedder.prewarm()

    md_files = sorted(library.rglob("*.md"))
    logger.info("Found %d .md files in %s", len(md_files), library)

    manifest = _load_manifest()
    seeding = not manifest
    unchanged = 0
    results = []
    for n, filepath in enumerate(md_files, 1):
        key = str(filepath)
        digest = _file_hash(filepath)
        if manifest.get(key) == digest or (
                seeding and _already_embedded(filepath)):
            manifest[key] = digest
            unchanged += 1
            results.append({"file": filepath.name, "chunks_added": 0,
                            "tagged": False, "skipped": True})
            continue
        result = run_file(filepath)
        results.append(result)
        if filepath.exists():
            # Hash after autotag, which may have rewritten the frontmatter.
            manifest[key] = _file_hash(filepath)
        if n % 200 == 0:
            _save_manifest(manifest)
    _save_manifest(manifest)
    logger.info("Skipped %d unchanged files", unchanged)

    total_added = sum(r["chunks_added"] for r in results)
    total_files = len([r for r in results if not r["skipped"]])
    logger.info("Ingestion complete: %d files, %d chunks added", total_files, total_added)

    return results
