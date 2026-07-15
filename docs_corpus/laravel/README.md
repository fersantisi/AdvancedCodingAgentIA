# Laravel documentation corpus (RAG source)

This directory is the **RAG knowledge base** for the agent. It holds a curated
subset of the **official Laravel documentation**, used by the `researcher`
subagent through the `rag_search` tool to answer questions grounded in Laravel
conventions while analyzing the target repository.

## Source and attribution

- **Origin:** <https://github.com/laravel/docs>, branch **`12.x`**
  (commit `f2dc517`).
- **License:** the Laravel documentation is released under
  [MIT](https://github.com/laravel/docs/blob/12.x/license.md);
  copyright © Taylor Otwell. These files are unmodified copies of the upstream
  Markdown, redistributed here for offline retrieval only.
- **Why `12.x`:** the target repository
  (`HealthApi-AlbertoPizzi`) declares `"laravel/framework": "^12.0"` and
  `"php": "^8.4"` in its `composer.json`, so the docs branch is matched to the
  version under analysis.

## What was selected (27 files)

Chosen to cover the questions the use case asks (architecture, dependencies,
risks, useful commands) for a **Laravel API** (PHP + Blade + Docker):

- **Foundations:** `installation`, `structure`, `lifecycle`, `container`,
  `providers`, `configuration`
- **HTTP layer:** `routing`, `middleware`, `controllers`, `requests`,
  `responses`, `validation`
- **Persistence:** `eloquent`, `eloquent-relationships`, `migrations`,
  `seeding`, `database`, `queries`
- **Security / auth:** `authentication`, `authorization`, `sanctum`
  (API token auth)
- **Views / tooling:** `blade`, `artisan`, `testing`, `deployment`, `errors`,
  `logging`

The full upstream set (~100 files) was trimmed to keep the index focused and
the embedding cost low; the excluded pages (billing, broadcasting, Dusk,
Horizon, etc.) are not relevant to analyzing this API.

## How it is indexed

Built with the project's own ingestion pipeline (no external framework):

```bash
python -m coding_agent.rag.ingest docs_corpus/laravel   # writes rag_index.json
```

- **Chunking** (`coding_agent/rag/chunking.py`): paragraph-aware, overlapping.
  `max_chars = 1500`, `overlap = 200`. Paragraphs under the limit stay whole;
  oversized ones are hard-split with the overlap preserved so context isn't lost
  at boundaries.
- **Embeddings** (`coding_agent/rag/embeddings.py`): OpenAI
  `text-embedding-3-small`, called over plain REST via `httpx` (deliberately not
  the `openai` SDK), behind the `EmbeddingsProvider` ABC.
- **Storage** (`coding_agent/rag/store.py`): a single JSON file (`rag_index.json`,
  gitignored — rebuild it with the command above) with a pure-Python cosine
  similarity scan. Linear search is instant at this corpus size.
- **Retrieval** (`coding_agent/tools/rag_search.py`): returns the top matching
  fragments labeled `[source: <file>#chunkN | relevance: X]`; RAG is tried first
  and web search is the fallback (see the researcher subagent's mission and
  `SOURCE_LABELING_INSTRUCTION`).
