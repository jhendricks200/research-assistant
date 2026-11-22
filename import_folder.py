"""
Generic importer: copy a folder of markdown or text files into the library.

    python import_folder.py <source_folder> [--source-type article] [--overwrite] [--skip-ingest]

Each file is written to DOCS_PATH with a small YAML frontmatter stub (title,
source_type, status). Fields left empty (topics, tags, entities) are filled by
autotag.py during ingest. Write your own importer for any other source by
producing markdown files with the same frontmatter; see README, "Adding sources".
Filenames must be unique across the library, because chunks are keyed by filename.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

import config
import parser as md_parser


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "doc"


def import_folder(src: Path, source_type: str, overwrite: bool) -> int:
    config.DOCS_PATH.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(src.rglob("*")):
        if f.suffix.lower() not in (".md", ".markdown", ".txt") or not f.is_file():
            continue
        out = config.DOCS_PATH / f"{slug(f.stem)}.md"
        if out.exists() and not overwrite:
            continue
        fm, body = md_parser.extract_frontmatter(f)
        fm.setdefault("title", f.stem.replace("-", " ").replace("_", " ").strip())
        fm.setdefault("source_type", source_type)
        fm.setdefault("status", "published")
        out.write_text(f"---\n{yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)}---\n{body.lstrip()}", encoding="utf-8")
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source", type=Path)
    ap.add_argument("--source-type", default="article")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--skip-ingest", action="store_true")
    a = ap.parse_args()
    n = import_folder(a.source, a.source_type, a.overwrite)
    print(f"Imported {n} files into {config.DOCS_PATH}")
    if n and not a.skip_ingest:
        subprocess.run([sys.executable, str(config.PROJECT_ROOT / "main.py"), "ingest"], check=True)


if __name__ == "__main__":
    main()
