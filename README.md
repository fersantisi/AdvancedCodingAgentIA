# Coding Agent Avanzado

A coding agent built **from scratch** — a hand-written harness that connects an LLM to
tools and to a small fleet of specialized **subagents**, with persistent memory, a **RAG**
knowledge base, a permission policy layer, loop/insufficient-evidence detection, context
compaction and **Langfuse** observability. No orchestration frameworks: the only LLM SDK is
the OpenAI client; everything else (subagent orchestration, RAG, tracing) is hand-written.

This is the **TP Final ("Coding Agent Avanzado")**, built on top of the in-class TP. The
base agent (two-loop harness, tools, plan mode, supervision, guardrails, retries, logging)
is unchanged and documented below; the advanced layer adds multi-agent delegation, shared
state, memory, RAG, policies, observability and plugin auto-discovery.

## Use case and success criterion

The agent is specialized for the **PHP / Laravel ecosystem**. The concrete objective is to
analyze the Laravel API repository
[**AlbertoPizzi-lightit/HealthApi-AlbertoPizzi**](https://github.com/AlbertoPizzi-lightit/HealthApi-AlbertoPizzi)
(Laravel 12 / PHP 8.4, a modular DDD-style API with Blade + Docker) and produce an
**architecture / dependencies / risks / commands** report grounded in the official Laravel
documentation (the RAG corpus).

**Success criterion:** given the target repo, the orchestrator delegates exploration and
research to its subagents, the researcher grounds Laravel concepts in `rag_search` results
with explicit `[source: ...]` citations, and the agent returns a coherent four-section
report — while every turn, LLM call, tool call and retrieval is traced in Langfuse. See
[`examples/run_3_rag_analysis.md`](examples/run_3_rag_analysis.md).

## Architecture

```
coding_agent/
├── agent/                  # Agent core (knows nothing about OpenAI, Tavily, Langfuse or the terminal)
│   ├── harness.py          #   AgentHarness — the INNER tool-execution loop (+ tracing, loop detection, compaction)
│   ├── subagent.py         #   SubAgentSpec + default_specs() (5 subagents) + SubAgentRunner (delegation)
│   ├── memory.py           #   ProjectMemory — persistent .agent/memory.json
│   ├── loop_detector.py    #   Detects repeated (tool-call, result) pairs → nudge / abort
│   ├── compaction.py       #   ContextCompactor — summarizes old history when it grows
│   ├── conversation.py     #   ConversationHistory — full session message history
│   ├── planner.py          #   Plan Mode (plan → approve / modify / reject)
│   ├── supervisor.py       #   Supervision mode (human-in-the-loop [Y/n])
│   ├── io.py               #   AgentIO protocol — UI contract (dependency inversion)
│   └── prompts.py          #   System prompt + source-labeling + insufficient-evidence rules
├── llm/                    # LLM provider abstraction
│   ├── base.py             #   LLMClient ABC — the only contract the agent sees
│   ├── openai_client.py    #   OpenAI implementation (only module importing `openai`)
│   ├── retry.py            #   RetryingLLMClient — backoff on transient failures
│   └── factory.py          #   create_llm_client(settings, tracer) — composes retry + tracing
├── models/                 # Provider-neutral frozen dataclasses
│   ├── messages.py         #   Role, Message
│   ├── tool_call.py        #   ToolCall, ToolResult, ToolSpec, AssistantTurn, Usage
│   └── task_state.py       #   TaskState — shared state across subagents
├── rag/                    # Retrieval-augmented generation (hand-written)
│   ├── chunking.py         #   Paragraph-aware overlapping chunker (1500 chars / 200 overlap)
│   ├── embeddings.py       #   EmbeddingsProvider ABC + OpenAIEmbeddings (REST via httpx) + Null
│   ├── store.py            #   VectorStore — JSON persistence + pure-Python cosine search
│   └── ingest.py           #   CLI: build rag_index.json from a docs directory
├── tools/                  # Tool system
│   ├── base.py             #   Tool ABC + ToolRegistry
│   ├── read_file.py write_file.py list_files.py run_command.py
│   ├── rag_search.py remember.py ask_user.py delegate.py
│   ├── discovery.py        #   Plugin auto-discovery (pkgutil + importlib)
│   ├── plugins/            #   Auto-discovered plugins (sample: count_lines.py)
│   └── web_search/         #   SearchProvider ABC + TavilyProvider + the tool
├── observability/          # Tracing seam
│   ├── base.py             #   Tracer ABC + NullTracer (no external deps)
│   ├── tracing_client.py   #   TracingLLMClient — times calls, records tokens/cost/errors
│   ├── pricing.py          #   estimate_cost_usd from a small price table
│   ├── factory.py          #   create_tracer(settings)
│   └── langfuse_tracer.py  #   LangfuseTracer (only module importing `langfuse`, lazily)
├── config/
│   ├── settings.py         #   Settings from env / .env
│   ├── policies.py         #   AgentPolicies from agent.config.json (workspace, permissions, commands, plugins)
│   ├── guardrails.py       #   Legacy Guardrails from guardrails.json (still supported)
│   └── logging_config.py   #   File + console logging
└── cli/
    ├── main.py             #   Entry point, composition root (build_app / build_registry), OUTER loop
    └── console.py          #   ConsoleIO — all terminal input/output
```

**Design principles.** Every module has one responsibility; dependencies point inward
(`agent/` depends only on abstractions in `llm/base`, `tools/base`, `agent/io`,
`observability/base`, `models` and `config`, never on OpenAI, Tavily, Langfuse or the
terminal); `tools/` never imports `agent/` (delegation uses a Protocol). Only
`llm/openai_client.py` imports `openai`; only `observability/langfuse_tracer.py` imports
`langfuse` (and lazily, so it stays an optional dependency). All wiring happens in one
composition root (`cli/main.py::build_app`) via constructor injection — which is also what
makes the whole core testable with fakes.

## Multi-agent orchestration

The top-level agent (`agent_name="main"`) is an **orchestrator**. It has a `delegate` tool
(`tools/delegate.py`) that hands a sub-task to one of five specialized **subagents**
(`agent/subagent.py`):

| Subagent | Responsibility | Tools it may use |
|---|---|---|
| `explorer` | Understand repo structure, architecture, dependencies, conventions | `read_file`, `list_files`, `run_command` |
| `researcher` | Find info in the RAG index (first) and the web (fallback), with sources | `rag_search`, `web_search`, `read_file` |
| `implementer` | Propose/apply focused code changes | `read_file`, `list_files`, `write_file`, `run_command` |
| `tester` | Validate by running tests / build / lint | `run_command`, `read_file`, `list_files` |
| `reviewer` | Review the diff against the original request | `read_file`, `list_files`, `run_command` |

Each delegation runs as a **fresh `AgentHarness`** with a *restricted* tool registry
(`ToolRegistry.subset(...)`), its own conversation history, and a mission prompt — but it
**shares** the task state, policies, supervisor and tracer with the orchestrator. Subagents
cannot delegate further (no `delegate` in their subsets), which bounds the recursion.

## Shared task state

`models/task_state.py::TaskState` is the shared scratchpad all agents read and write:

```
request          : the user's original request
progress         : list of progress notes
subagent_reports : [{agent, task, summary, success}]
sources          : [{origin, reference, detail}]  origin ∈ {repo, memory, rag, web, inference}
files_modified   : files write_file touched
observations     : free-form notes
```

It is rendered into each subagent's prompt (so a subagent sees what others found), and shown
by `/state` (human view) and `/state json` (raw). The harness records modified files and
failed tool calls automatically; `rag_search` and `web_search` record their sources with the
right origin label.

## Persistent project memory

`agent/memory.py::ProjectMemory` persists across sessions in `.agent/memory.json`, organized
into categories: `architecture, key_files, dependencies, commands, conventions, decisions,
bugs`, plus rolling `session_summaries`. The `remember` tool lets the agent store a durable
fact; memory is injected into the system prompt at startup; and on `exit` a ≤5-line **session
summary** is generated and saved. `/memory` prints the current memory. This is what lets a
later session answer from `[memory]` without re-exploring — see
[`examples/run_4_memory.md`](examples/run_4_memory.md).

## RAG (retrieval-augmented generation)

Entirely hand-written (no vector-DB framework):

- **Corpus:** [`docs_corpus/laravel/`](docs_corpus/laravel/) — 27 official Laravel 12 docs
  (routing, controllers, middleware, Eloquent, migrations, validation, Blade, Sanctum,
  artisan, testing, deployment, …). See its README for attribution and selection.
- **Chunking** (`rag/chunking.py`): paragraph-aware, `max_chars=1500`, `overlap=200`.
- **Embeddings** (`rag/embeddings.py`): OpenAI `text-embedding-3-small` over plain REST via
  `httpx`, behind the `EmbeddingsProvider` ABC (deliberately not the `openai` SDK).
- **Storage** (`rag/store.py`): a single JSON file (`rag_index.json`) with a pure-Python
  cosine scan — instant at this corpus size.
- **Retrieval** (`tools/rag_search.py`): returns top fragments labeled
  `[source: <file>#chunkN | relevance: X]`. The researcher's mission encodes **RAG-first,
  web-fallback**.

Build the index (needs `OPENAI_API_KEY`):

```bash
python -m coding_agent.rag.ingest docs_corpus/laravel        # writes rag_index.json
```

## Policies (agent.config.json)

`config/policies.py::AgentPolicies` loads `agent.config.json` and validates **every** tool
call before it runs:

```json
{
  "workspace": ".",
  "permissions": {
    "read":  { "deny": [".env", "**/*.pem", "secrets/**"] },
    "write": { "deny": [".env", ".github/**", "**/*.pem", "secrets/**", "agent.config.json"] }
  },
  "commands": {
    "deny": ["rm -rf", "git push", "sudo", "shutdown", "..."],
    "require_approval": ["npm install", "pip install", "composer install", "git commit"]
  },
  "plugins": { "enabled": ["count_lines"] }
}
```

- `workspace` — all path arguments must resolve inside it (paths are `.resolve()`d first, so
  `../` escapes are caught).
- `permissions.read.deny` / `write.deny` — glob patterns (`**` crosses separators) the agent
  may never read / modify.
- `commands.deny` — forbidden command substrings; `commands.require_approval` — commands that
  **always** prompt, even with `/supervise off`.
- `plugins.enabled` — optional allowlist for auto-discovered plugin tools (see below).

The legacy `guardrails.json` (`config/guardrails.py`) still works alongside policies.

## Loop detection & insufficient evidence

- `agent/loop_detector.py` counts identical `(tool call, result)` repetitions within a turn:
  it **nudges** the agent to change strategy at the 2nd and **aborts** the turn with a
  structured "what I tried / what's missing" message at the 4th.
- `INSUFFICIENT_EVIDENCE_INSTRUCTION` (`agent/prompts.py`) plus the `ask_user` tool tell the
  agent: when the request is ambiguous, docs are missing or an error is undiagnosed, **don't
  guess** — ask or stop and explain what's needed.

Both fire in [`examples/run_5_loop_or_help.md`](examples/run_5_loop_or_help.md).

## Context compaction

`agent/compaction.py::ContextCompactor` summarizes older history via a tool-free LLM call
once it exceeds `COMPACT_AFTER_MESSAGES` (default 60), always preserving the system prompt
and the recent tail and never splitting a tool call from its results.

## Observability (Langfuse)

`observability/` is a provider-agnostic tracing seam. `Tracer` (ABC) has `NullTracer` (no-op)
and `LangfuseTracer` backends; `TracingLLMClient` wraps the LLM client so **every** call
(including retries) is timed and recorded with token `Usage` and an estimated `cost_usd`.

Mapping to Langfuse: turn → **trace** (named after the agent), LLM call → **generation**
(model, tokens, cost, latency, error level), tool call → **span**, RAG retrieval →
`rag_retrieval` **span** with the sources. Every tracer method swallows backend errors
(observability must never break the agent loop). Enable with:

```bash
OBSERVABILITY_PROVIDER=langfuse           # + the LANGFUSE_* keys below
```

A full run is captured in [`examples/run_3_rag_analysis.md`](examples/run_3_rag_analysis.md);
screenshot instructions and trace IDs are in
[`examples/screenshots/README.md`](examples/screenshots/README.md).

## Plugin auto-discovery (optional extra)

`tools/discovery.py::discover_tools()` scans `tools/plugins/` with `pkgutil` + `importlib`
and instantiates every concrete no-arg `Tool` subclass it finds — so a new tool is added by
**dropping a file** in that package, with no change to the harness. The optional
`plugins.enabled` allowlist in `agent.config.json` filters which load. Sample plugin:
`tools/plugins/count_lines.py`.

## The harness: two independent nested loops

**Outer loop** (`cli/main.py::run_conversation_loop`) — the conversation:

```
while True:
    read user input (">> ")
    exit/quit -> save session summary, flush tracer, leave;   /commands -> toggle modes / inspect
    final_text = harness.run_turn(user_input)
    print final_text
```

**Inner loop** (`agent/harness.py::run_turn`) — one agent turn:

```
append user message to history; (maybe compact history)
if plan mode: negotiate plan (may abort the turn)
loop:
    turn = llm.complete(history, tool_specs)           # traced
    if no tool calls: return turn.text                 # turn finished
    for each tool call:
        policies.validate(call) / guardrails.validate(call)   # blocked -> error result
        loop_detector.observe(call)                    # repeated -> nudge / abort
        supervisor.approve(call)                       # denied  -> error result
        result = tool.execute(arguments)               # failure -> error result
        append tool result to history
```

Every failure inside the inner loop becomes an **error tool result fed back to the LLM**, so
the model adapts instead of the program crashing. `MAX_TOOL_ITERATIONS` (default 30) caps it.

## Tool system

Every tool implements one interface (`tools/base.py`):

```python
class Tool(ABC):
    name: str; description: str; parameters: dict; read_only: bool
    def execute(self, arguments: dict) -> str   # raises ToolError on failure
```

| Tool | Read-only | Notes |
|---|---|---|
| `read_file` | yes | UTF-8 read, clear errors, output capped |
| `write_file` | no | Overwrites; creates parent directories |
| `list_files` | yes | Non-recursive; directories marked `/` |
| `run_command` | no | Shell; returns exit code + stdout + stderr; timeout |
| `web_search` | yes | Tavily behind a `SearchProvider` abstraction |
| `rag_search` | yes | Cosine search over the Laravel docs index, with sources |
| `remember` | no | Stores a durable fact in project memory |
| `ask_user` | yes | Asks the user a clarifying question |
| `delegate` | no | Orchestrator-only: hand a sub-task to a subagent |
| `count_lines` | yes | Sample auto-discovered plugin |

**Adding a tool:** subclass `Tool` and add one line in `cli/main.py::build_registry` — or
just drop a plugin file in `tools/plugins/`.

## Installation

Requires Python 3.12+ (uses `StrEnum`, modern typing). On this machine use `python3.13`
(`py -3.13` on Windows).

```bash
pip install -r requirements.txt      # openai, httpx, python-dotenv, pytest, langfuse (optional)
cp .env.example .env                 # then edit .env and add your keys
```

## Configuration

`.env` (see `.env.example`):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | **yes** | — | LLM + embeddings access |
| `TAVILY_API_KEY` | no | — | Enables `web_search` |
| `LLM_PROVIDER` / `OPENAI_MODEL` | no | `openai` / `gpt-4o-mini` | Provider / model |
| `EMBEDDINGS_MODEL` | no | `text-embedding-3-small` | RAG embeddings |
| `RAG_STORE_PATH` | no | `rag_index.json` | Vector store file |
| `AGENT_MEMORY_FILE` | no | `.agent/memory.json` | Persistent memory |
| `COMMAND_TIMEOUT_SECONDS` / `MAX_TOOL_ITERATIONS` / `LLM_MAX_RETRIES` | no | 60 / 30 / 3 | Limits |
| `COMPACT_AFTER_MESSAGES` | no | `60` | History compaction threshold |
| `OBSERVABILITY_PROVIDER` | no | `none` | `none` or `langfuse` |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | for langfuse | — | Langfuse credentials |
| `LANGFUSE_HOST` | no | `https://cloud.langfuse.com` | EU; use `https://us.cloud.langfuse.com` for US (`LANGFUSE_BASE_URL` accepted as an alias) |

## Running

```bash
python -m coding_agent.rag.ingest docs_corpus/laravel   # build the RAG index (once)
python -m coding_agent.cli.main                          # normal
python -m coding_agent.cli.main --verbose                # INFO logs on the console too
python -m coding_agent.cli.main --config agent.config.json --guardrails guardrails.json
```

In-chat commands: `/plan on|off`, `/supervise on|off`, `/state` (`/state json`), `/memory`,
`/status`, `/tools`, `/help`, and `exit` / `quit`.

## Modes

- **Plan Mode** (`/plan on`, default off): an extra **tool-free** LLM call produces a numbered
  plan; you `[a]pprove / [m]odify / [r]eject` before anything runs.
- **Supervision** (`/supervise on|off`, default **on**): every **mutating** tool
  (`write_file`, `run_command` — the ones with `read_only = False`) asks `[Y/n]` first;
  read-only tools (including `remember`, which only touches the agent's own memory file, and
  `delegate`, whose inner tool calls are policed individually) never ask.
  `commands.require_approval` in the policy always asks, even with supervision off.

## Error handling

| Failure | Behaviour |
|---|---|
| LLM network / rate-limit / 5xx | Retried with exponential backoff; then a readable CLI error — conversation intact |
| Tool failure (missing file, permission denied, …) | `ToolError` → error result fed back to the LLM |
| Policy / guardrail violation | Error result explaining the block; agent keeps running |
| Repeated identical tool call | Loop detector nudges, then aborts with a structured explanation |
| Command timeout / non-zero exit | Timeout → error result; non-zero exit is reported data |
| Observability backend error | Swallowed and logged; never breaks the turn |
| `Ctrl+C` mid-turn | Cancels the turn, not the program |

## Tests

```bash
python -m pytest tests/ -q     # 161 tests, no network or API key needed
```

The core is tested end-to-end with scripted fakes (`tests/conftest.py`:
`FakeLLMClient`, `FakeIO`, `FakeTracer`, `FakeEmbeddings`, `make_harness`): multi-tool turns,
error feedback, history persistence, supervision, plan mode, guardrails + policies, retries,
subagent delegation, task state, memory, RAG, loop detection, compaction, observability, the
Langfuse tracer (with an injected fake client — no network), and plugin discovery.

## Example runs

Real transcripts are in [`examples/`](examples/):

1. [`run_1_bugfix.md`](examples/run_1_bugfix.md) — base agent fixes a bug (supervision on).
2. [`run_2_explore_repo.md`](examples/run_2_explore_repo.md) — base agent explores a repo (plan mode).
3. [`run_3_rag_analysis.md`](examples/run_3_rag_analysis.md) — **multi-agent RAG analysis** of
   the HealthApi Laravel repo, with delegation, `rag_search` sources and Langfuse traces.
4. [`run_4_memory.md`](examples/run_4_memory.md) — a **second session using memory** saved by run 3.
5. [`run_5_loop_or_help.md`](examples/run_5_loop_or_help.md) — the agent **changes strategy**
   (loop detector) and **asks for help** (`ask_user`) instead of guessing.

[`examples/retrospective.md`](examples/retrospective.md) is the base-TP retrospective;
the reflection below covers the advanced layer.

## Requirement checklist (TP Final deliverables)

| Deliverable / requirement (PDF) | Implementation |
|---|---|
| No orchestration frameworks; only raw LLM API + small libs | `agent/`, `rag/`, `observability/` hand-written; deps: `openai`, `httpx`, `python-dotenv`, `langfuse` |
| Multi-agent architecture (≥5 subagents) | `agent/subagent.py` (explorer, researcher, implementer, tester, reviewer) + `tools/delegate.py` |
| Shared state across agents | `models/task_state.py::TaskState`; `/state` |
| Persistent memory | `agent/memory.py` + `remember` tool + `.agent/memory.json`; `/memory` |
| RAG (corpus, embeddings, store, retrieval, ingest) | `rag/` + `tools/rag_search.py` + `docs_corpus/laravel/` |
| Permission policies (config file) | `config/policies.py` + `agent.config.json` |
| Loop / insufficient-evidence detection | `agent/loop_detector.py` + `tools/ask_user.py` + prompt rules |
| Context management | `agent/compaction.py` |
| Observability (tokens, cost, latency, traces) | `observability/` + `LangfuseTracer` |
| Plugin auto-discovery (optional extra) | `tools/discovery.py` + `tools/plugins/` |
| Two nested loops / interactive chat / history / base tools / plan / supervision / guardrails / retries / logging | Base TP — see sections above and the base checklist |
| Approved use case + evidence runs | HealthApi Laravel analysis; `examples/run_3..5` + Langfuse |
| Documentation + tests | this README, `docs_corpus/laravel/README.md`, 161 tests |

## Reflection

**What worked.** The abstraction seams from the base TP paid off directly: subagents are just
`AgentHarness` instances with a restricted `ToolRegistry.subset()`, RAG and observability
plugged in behind ABCs with zero changes to the core loop, and the Langfuse backend slotted
into the existing `Tracer` seam. In the real runs the RAG-first researcher cited its sources
correctly, and the orchestrator delegated sensibly (explorer → researcher).

**What failed / was detected.** Against the target repo the model repeatedly assumed the
classic `app/`-style Laravel layout, but HealthApi uses a DDD `src/<Context>/{App,Domain}`
structure — so several first-guess paths 404'd. This is exactly where the guardrails earned
their place: in run 5 the **loop detector** caught the implementer re-reading a non-existent
path and nudged it to list the directory and find the real file, and the
**insufficient-evidence rule + `ask_user`** stopped it from fabricating a fix when no error
details were available. `gpt-4o-mini` also produced somewhat generic reports, and once
returned malformed tool-call JSON (auto-retried by `RetryingLLMClient`).

**Improvements.** Feed the actual directory tree into the explorer's first prompt to avoid
the layout-guessing loop; expand the RAG corpus with the target's specific packages (Sanctum,
spatie/permission, Scramble); and add cross-turn source dedup in `TaskState`.
```
