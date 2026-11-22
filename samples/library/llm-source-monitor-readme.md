---
title: 'LLM source monitor: README'
source_type: article
status: published
topics: [LLM pipelines]
tags: [scheduling, summarization, model routing]
entities: [RSS, Anthropic]
---
# LLM Source Monitor

A scheduled pipeline that collects recent posts from a curated list of sources (RSS feeds, X accounts and Telegram channels), groups them by topic ("beat"), and uses an LLM to write a structured digest for each beat. It finishes with a cross-beat pass and keeps a markdown wiki of the named entities that show up across runs.

It is built to run unattended: every model call is streamed and retried, model choice lives in a config file rather than code, and missing credentials for one platform skip that platform instead of failing the run.

## How it works

```
config/sources.yaml ──► collect.py ──► (optional clean hook) ──► pipeline/synthesize.py ──► digests/<timestamp>.txt
   RSS / X / Telegram     fetch last 48h,                          one LLM call per beat,              │
                          normalize to one                         plus one cross-beat call            ▼
                          Post schema                                                       pipeline/entities.py
                                                                                            wiki/entities/*.md
                                  every model call goes through pipeline/llm.py
                                  (routing from config/models.yaml)
```

1. **Collect** (`collect.py`). Reads `config/sources.yaml` and fetches posts from the last 48 hours. RSS uses feedparser; X uses the API v2 recent-search endpoint with app-only auth; Telegram uses a Telethon user session. Every post is normalized to one schema (id, platform, source, beat, text, url, timestamp, language hint, note). Each item gets a stable id per source, and posts are sorted newest first.
2. **Clean** (optional hook). If a `pipeline/clean.py` module with a `clean(posts)` function exists, `run.py` uses it; otherwise posts pass through unchanged. No cleaning module ships in this repo, so cross-source duplicates are not removed.
3. **Synthesize** (`pipeline/synthesize.py`). Posts are mapped to canonical beats through an alias table. For each beat with posts, one LLM call produces a fixed-format briefing: synthesis, potential angles, coverage gaps, a watch list, and one short paragraph per configured "dimension" of that beat. When two or more beats have content, a final call looks for signals that cut across beats.
4. **Entity wiki** (`pipeline/entities.py`). One call extracts named entities (people, companies, products, models, projects) as JSON. New entities get a markdown page; existing pages get one batched call that merges the new context into the running summary and appends a dated appearance. Re-running the same timestamp does not duplicate entries.
5. **LLM adapter** (`pipeline/llm.py`). A small provider-agnostic `complete(stage, ...)` function. Provider, model, token budget and extra parameters per stage come from `config/models.yaml`, so moving a stage between Anthropic and OpenAI is a config edit. Connections disable keep-alive pooling and stream every response, with three attempts and backoff per call; this avoids long hangs on sequential calls and false timeouts on large outputs.

## Setup

Requires Python 3.9 or newer.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then add your keys
```

Only the API key for the provider(s) named in `config/models.yaml` is required. The sample configuration routes every stage to Anthropic, so `ANTHROPIC_API_KEY` is enough. X and Telegram keys are optional; without them those platforms are skipped with a log message.

## Configuring sources

Edit `config/sources.yaml`. Top-level keys are beats; each entry is a source:

```yaml
ai_research:
  - handle: arxiv_cs_ai
    platform: rss
    url: https://rss.arxiv.org/rss/cs.AI
    lang: en
    note: New arXiv papers in Artificial Intelligence
    active: true
```

`platform` is `rss`, `x` or `telegram`. For X and Telegram, `handle` is the account or channel name and no `url` is needed. Set `active: false` to pause a source.

To add or rename a beat, update `BEATS`, `BEAT_ALIASES` and (optionally) `BEAT_DIMENSIONS` in `pipeline/synthesize.py`.

High-volume feeds (arXiv lists, for example) can put hundreds of posts into one beat's prompt. Trim or pause feeds if a beat grows beyond your model's context or budget.

## Running

```bash
python collect.py --no-snapshot   # collection only: prints a per-beat count table, no LLM calls
python run.py --now               # full pipeline once
python run.py                     # in-process scheduler: Mon/Wed/Fri at 06:00
```

Outputs:

- `digests/YYYY-MM-DD_HH-MM.txt`, one digest per run
- `wiki/entities/*.md`, one page per tracked entity
- `logs/pipeline.log`

### Scheduling with launchd (macOS)

`scripts/scheduled_run.sh` runs the pipeline once using the project virtualenv. `scripts/com.example.llm-source-monitor.plist` is an example launchd job that calls it daily at 09:00; replace the placeholder path, copy it to `~/Library/LaunchAgents/`, and load it with `launchctl load`. On Linux, call the same script from cron.

## Digest format (illustrative)

The structure below is what each run writes. The bracketed text is placeholder, not real output.

```
=== SOURCE MONITOR DIGEST ===
Run: YYYY-MM-DD HH:MM UTC
Sources monitored: [N] Telegram channels, [N] X accounts, [N] RSS feeds
Posts fetched: [N] Telegram posts, [N] X posts, [N] RSS items
Posts ingested: [N]

---

## AI RESEARCH
SYNTHESIS
[2 to 4 paragraphs on what moved in this beat]

POTENTIAL ANGLES
- [one-sentence angle]

COVERAGE GAPS
- [what is not being covered, and why it matters]

WATCH LIST
- [entity or indicator to track, with a one-line reason]

## Dimensions
**New models and benchmarks**
[1 to 3 sentences, or "No significant developments this cycle."]
...

---

## AI INDUSTRY
...

---

## CROSS-BEAT SIGNALS
- [header line]: [2 to 3 sentences]

---
End of digest.
```

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The tests run offline and make no API calls: they cover config loading, beat routing, prompt construction, digest assembly, the adapter's retry and error paths, entity page creation and merging, and RSS parsing against a local feed file.

## License

MIT. See [LICENSE](LICENSE).
