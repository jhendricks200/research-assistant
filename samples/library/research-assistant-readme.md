---
title: 'Research Assistant: README'
source_type: article
status: published
topics: [RAG, Evaluation]
tags: [hybrid search, reciprocal rank fusion, evaluation]
entities: [ChromaDB, SQLite FTS5]
---
# Research Assistant

A local question-answering assistant for a private library of markdown documents. Point it at a folder and ask questions in plain English. Every answer cites the passages it used with numbered markers, and you can click through to each source. When the library doesn't cover a question, the assistant says so instead of guessing.

I built it for a personal library of about 34,000 documents (148,727 passages). This repository holds the engine, a sample library made of my own engineering write-ups (READMEs, design docs and decision records from the projects on my site), and the evaluation harness I used to decide which retrieval changes to keep. Clone it and you can ask it about my work.

## How a question is answered

1. **Rewrite.** Claude Haiku turns the question into a standalone version, resolving "it" and "that" from the conversation, plus two alternate phrasings that expand acronyms and swap in synonyms. The original wording is kept as well, so 3 or 4 queries go out.
2. **Search two ways.** Each query runs against a vector index (ChromaDB with all-MiniLM-L6-v2, cosine similarity) and a keyword index (SQLite FTS5 with BM25 ranking and stemming). Each index returns its top 20 passages. Vector hits below 0.2 similarity are dropped.
3. **Fuse.** All the ranked lists are merged with reciprocal rank fusion (k = 60). A passage that ranks well for several phrasings, or in both indexes, rises to the top.
4. **Balance sources.** If one source type dominates the library, it can crowd everything else out. The final 8 passages can include at most 3 of the dominant type, and the types you care most about get a 1.5x boost in the fused score. Both settings live in `.env`.
5. **Answer.** Claude Sonnet gets the 8 passages as numbered excerpts. It is told to answer only what they support, cite with markers like [1][3], say plainly what is missing when coverage is partial, and decline when the passages are unrelated to the question.

Optional topic filters apply to both indexes. Conversation history keeps the last 10 exchanges.

## Results

I measured everything on my own library before adopting it, using hand-written questions where I knew which document held the answer and which facts a correct answer had to contain. I tuned on a first set of 30 questions. Then I wrote a held-out set of 15 questions, 13 answerable and 2 that the library could not answer, and scored them without changing any settings.

On the held-out set:

| Configuration | Right source in the 8 passages | Right source ranked first | Answers with the required facts |
|---|---|---|---|
| Vector search only (before) | 6 of 13 | 2 of 13 | 9 of 13 |
| Vector + keyword + source balancing (shipped) | 10 of 13 | 5 of 13 | 13 of 13 |

Every answer cited its sources, and both unanswerable questions were declined in both configurations. On the tuning set the same change moved the right source into the top 8 on 21 of 26 questions instead of 17, and moved answers with the required facts from 12 of 26 to 23 of 26.

I also tested two heavier changes and did not adopt them, because neither beat the simpler configuration once both question sets were counted:

| Variant tested (held-out, 13 answerable) | Source in 8 | Ranked first | Cost |
|---|---|---|---|
| + cross-encoder reranker (bge-reranker-base, top 40 reranked to 8) | 11 | 7 | about 2 seconds more per question |
| Stronger embedding model (bge-base-en-v1.5) + keyword + balancing | 10 | 8 | 90-minute re-embed, 2.3 GB more disk |

Across all 39 answerable questions, the shipped configuration found the right source 31 times, the reranker version 32 times, and the stronger embedder version 30 times.

One finding worth knowing: the default embedder only reads the first 256 tokens of each passage, and 81% of passages in my library were longer than that. Smaller chunks are the next experiment, since they are cheaper than a bigger model.

## Run it

You need Python 3.11 or newer and an Anthropic API key.

```bash
git clone <this repository> research-assistant
cd research-assistant
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # then put your key in .env
```

The default `DOCS_PATH` is `samples/library`: 15 technical write-ups from my projects (Agent Rooms, the transit delay predictor, Shiori, the lead qualification pipeline, the LLM source monitor, an earlier RAG chatbot and this assistant). Index it and ask away:

```bash
.venv/bin/python main.py ingest      # embeds the documents and builds the keyword index
.venv/bin/python main.py chat        # terminal chat
./start-web.sh                       # web UI at http://127.0.0.1:8787
```

Try "Why did Agent Rooms attach to Discord and GitHub instead of building its own platform?" or "What does the transit app refuse to show until its data passes quality checks?"

To use your own documents, set `DOCS_PATH=library` in `.env`, import a folder of markdown or text files and ingest it:

```bash
.venv/bin/python import_folder.py ~/path/to/notes
```

Other commands are `main.py query "text"` (raw search results), `main.py stats`, `main.py watch` (re-index files as they change) and `main.py keywords` (rebuild the keyword index).

## Run the tests

The offline tests index a tiny fixture library (12 made-up notes about brewing coffee, in `tests/fixtures/`) and check the retrieval mechanics without calling any API:

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
```

The evaluation harness scores retrieval and answers against `eval/questions.jsonl`: 12 questions about the sample library, the kind a reviewer might ask about the projects, including one it should decline. Rewrites are made once with Haiku and cached, so comparing retrieval variants is free. A full run costs about 24 API calls and is capped at 30.

```bash
.venv/bin/python eval/run_eval.py rewrite
.venv/bin/python eval/run_eval.py retrieve baseline
.venv/bin/python eval/run_eval.py retrieve hybrid_balance
.venv/bin/python eval/run_eval.py answer hybrid_balance
```

On the bundled 15-document sample, the shipped configuration found the right source for 10 of 11 answerable questions, and all 11 answers contained the required facts with citations. Keyword search alone scored 11 of 11 there. Source balancing is meant for libraries dominated by one source type, and this small sample has none, so expect it to matter only on larger collections.

The reranker and alternate-embedder variants need `requirements-eval.txt`, about 1 GB including torch. Run `eval/embed_bge.py` before the `bge_*` variants.

## Adding sources

Every document is a markdown file in the library folder with YAML frontmatter:

```yaml
---
title: Example
source_type: article        # article, analysis, note, report or reference
status: published
topics: [Retrieval]
tags: [BM25, ranking]
entities: [SQLite]
---
```

Missing `topics`, `tags`, `entities`, `status` or `source_type` fields are filled by Claude Haiku during ingest, and the result is written back to the file. Filenames must be unique, because chunks are keyed by filename. To pull from another system, write an importer that produces files in this shape, the way `import_folder.py` does.

## Layout

| File | Role |
|---|---|
| `main.py` | CLI: ingest, watch, query, stats, chat, keywords |
| `pipeline.py` | Per-file flow: auto-tag, parse, chunk, normalize, embed. Skips unchanged files using a content hash. |
| `parser.py` | Frontmatter and section-aware chunking (about 300 tokens with 50 overlap) |
| `autotag.py` | Fills missing metadata with Claude Haiku |
| `normalizer.py` | Synonym normalization before embedding |
| `embedder.py` | Vector store, keyword index, fusion and source balancing. Both indexes are updated by the same two write functions. |
| `query_rewriter.py` | Multi-query rewriting with Claude Haiku |
| `chat.py` | Prompt, context building and the terminal chat |
| `server.py`, `web/` | FastAPI backend that streams answers, and a single-page web UI with a sources rail |
| `watcher.py` | Re-indexes files as they are saved |
| `eval/` | Evaluation harness, sample question set, optional reranker and embedder experiments |
| `samples/library/` | The sample library: project write-ups |
| `tests/` | Offline tests and the coffee fixture library |
