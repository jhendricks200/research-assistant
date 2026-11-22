#!/bin/sh
# Start the web UI at http://127.0.0.1:8787
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port "${PORT:-8787}"
