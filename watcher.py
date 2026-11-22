"""
Library file watcher.

Monitors DOCS_PATH for .md file changes and triggers the pipeline
automatically. Uses a 2-second stability debounce before processing

"""

import logging
import logging.handlers
import signal
import sys
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

import config
import embedder
import pipeline

# ── Logging ────────────────────────────────────────────────────────────────

_log_path = Path(__file__).resolve().parent / "watcher.log"

handler = logging.handlers.RotatingFileHandler(
    _log_path, maxBytes=5 * 1024 * 1024, backupCount=3
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[handler, logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 2.0


# ── Event handler ──────────────────────────────────────────────────────────

class LibraryHandler(FileSystemEventHandler):
    """Debounced handler for .md create/modify/delete events."""

    def __init__(self) -> None:
        super().__init__()
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _schedule(self, filepath: str, action: str) -> None:
        """Cancel any pending timer for this file and schedule a new one."""
        with self._lock:
            existing = self._timers.pop(filepath, None)
            if existing:
                existing.cancel()

            timer = threading.Timer(
                DEBOUNCE_SECONDS,
                self._dispatch,
                args=(filepath, action),
            )
            self._timers[filepath] = timer
            timer.start()

    def _dispatch(self, filepath: str, action: str) -> None:
        with self._lock:
            self._timers.pop(filepath, None)

        path = Path(filepath)
        if path.suffix.lower() != ".md":
            return

        try:
            if action == "delete":
                removed = embedder.delete_file(filepath)
                logger.info("Deleted %d chunks for %s", removed, path.name)
            else:
                result = pipeline.run_file(path)
                logger.info(
                    "Processed %s → %d chunks added",
                    result["file"],
                    result["chunks_added"],
                )
        except Exception:
            logger.exception("Error processing %s (action=%s) - skipping", path.name, action)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, "upsert")

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, "upsert")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._schedule(event.src_path, "delete")

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            # Old path → delete; new path → ingest
            self._schedule(event.src_path, "delete")
            self._schedule(event.dest_path, "upsert")


# ── Public entry point ─────────────────────────────────────────────────────

def watch(library_path: Path | None = None) -> None:
    """Start watching the library. Blocks until SIGINT/SIGTERM."""
    library = library_path or config.DOCS_PATH
    if not library.exists():
        logger.error("Library not found: %s", library)
        sys.exit(1)

    # Pre-warm ONNX model before starting observer - fail fast if unavailable
    embedder.prewarm()

    handler = LibraryHandler()
    observer = Observer()
    observer.schedule(handler, str(library), recursive=True)
    observer.start()
    logger.info("Watching library: %s", library)

    def _shutdown(signum, frame):
        logger.info("Shutting down watcher...")
        observer.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while observer.is_alive():
            time.sleep(1)
    finally:
        observer.join()
        logger.info("Watcher stopped.")
