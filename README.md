# Coding Agent

A coding agent built **from scratch** — a hand-written harness that connects an LLM to
tools (file system, terminal, web search) so it can solve software tasks autonomously
through an interactive chat. No orchestration frameworks: the only external SDK is the
OpenAI client used to call the model.

```
>> Fix the failing test in sample_project/
Assistant: I read the code, found an off-by-one bug in stats.py, fixed it and the
4 tests now pass.
```

## Architecture

```
coding_agent/
├── agent/                  # Agent core (knows nothing about OpenAI or the terminal)
│   ├── harness.py          #   AgentHarness — the INNER tool-execution loop
│   ├── conversation.py     #   ConversationHistory — full session message history
│   ├── planner.py          #   Plan Mode (plan → approve / modify / reject)
│   ├── supervisor.py       #   Supervision mode (human-in-the-loop [Y/n])
│   ├── io.py               #   AgentIO protocol — UI contract (dependency inversion)
│   └── prompts.py          #   System + planning prompts
├── llm/                    # LLM provider abstraction
│   ├── base.py             #   LLMClient ABC — the only contract the agent sees
│   ├── openai_client.py    #   OpenAI implementation (only module importing `openai`)
│   ├── retry.py            #   RetryingLLMClient — backoff on transient failures
│   └── factory.py          #   create_llm_client(settings)
├── models/                 # Provider-neutral dataclasses
│   ├── messages.py         #   Role, Message
│   └── tool_call.py        #   ToolCall, ToolResult, ToolSpec, AssistantTurn
├── tools/                  # Tool system
│   ├── base.py             #   Tool ABC + ToolRegistry
│   ├── read_file.py  write_file.py  list_files.py  run_command.py
│   └── web_search/         #   SearchProvider ABC + TavilyProvider + the tool
├── config/
│   ├── settings.py         #   Settings from env / .env
│   ├── guardrails.py       #   Guardrails loaded from guardrails.json
│   └── logging_config.py   #   File + console logging
└── cli/
    ├── main.py             #   Entry point, composition root, OUTER loop
    └── console.py          #   ConsoleIO — all terminal input/output
```

Design principles: every module has one responsibility; dependencies point inward
(`agent/` depends on abstractions in `llm/base`, `tools/base` and `agent/io`, never on
OpenAI, Tavily or the terminal); all wiring happens in one composition root
(`cli/main.py::build_harness`) via constructor injection, which is also what makes the
whole core testable with fakes.

## The harness: two independent nested loops

**Outer loop** (`cli/main.py::run_conversation_loop`) — the conversation:

```
while True:
    read user input (">> ")
    exit/quit  -> leave;   /commands -> toggle modes
    final_text = harness.run_turn(user_input)
    print final_text
```

**Inner loop** (`agent/harness.py::run_turn`) — one agent turn:

```
append user message to history
if plan mode: negotiate plan (may abort the turn)
loop:
    turn = llm.complete(history, tool_specs)
    if no tool calls:  return turn.text            # turn finished
    for each tool call:
        guardrails.validate(call)                  # blocked -> error result
        supervisor.approve(call)                   # denied  -> error result
        result = tool.execute(arguments)           # failure -> error result
        append tool result to history
```

The loops share nothing but the `run_turn()` call. Every failure inside the inner loop
(unknown tool, guardrail block, user denial, tool exception) becomes an **error tool
result fed back to the LLM**, so the model can adapt instead of the program crashing.
A `MAX_TOOL_ITERATIONS` cap (default 30) prevents runaway loops.

**Conversation memory:** `ConversationHistory` keeps every message (user, assistant,
tool results) from program start to exit, so follow-up questions and corrections keep
full context across turns.

## Tool system

Every tool implements one interface (`tools/base.py`):

```python
class Tool(ABC):
    name: str                  # e.g. "read_file"
    description: str           # shown to the LLM
    parameters: dict           # JSON Schema of the arguments
    read_only: bool            # read-only tools skip supervision
    def execute(self, arguments: dict) -> str   # raises ToolError on failure
```

| Tool | Read-only | Notes |
|---|---|---|
| `read_file` | yes | UTF-8 read, clear errors, output capped with truncation notice |
| `write_file` | no | Overwrites; creates parent directories |
| `list_files` | yes | Non-recursive; directories marked with `/` |
| `run_command` | no | System shell; returns **exit code + stdout + stderr**; timeout |
| `web_search` | yes | Tavily behind a `SearchProvider` abstraction |

**Adding a tool:** subclass `Tool`, then add one line in
`cli/main.py::build_registry`. Nothing else changes.

**Swapping the search provider:** implement `SearchProvider.search()` and inject it
into `WebSearchTool` — Tavily is just the default. Without a `TAVILY_API_KEY`, a
`NullSearchProvider` makes `web_search` fail gracefully with a "not configured" message.

**Swapping the LLM:** implement `LLMClient.complete()` for the new provider and add a
branch in `llm/factory.py`. The harness never knows which provider is running.

## Installation

Requires Python 3.12+ (uses `StrEnum`, modern typing).

```bash
git clone <repo>
cd CodingAgent
pip install -r requirements.txt
cp .env.example .env        # then edit .env and add your keys
```

## Configuration

`.env` (see `.env.example`):

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | **yes** | — | LLM access |
| `TAVILY_API_KEY` | no | — | Enables `web_search` |
| `LLM_PROVIDER` | no | `openai` | Provider selection |
| `OPENAI_MODEL` | no | `gpt-4o-mini` | Model to use |
| `COMMAND_TIMEOUT_SECONDS` | no | `60` | `run_command` timeout |
| `MAX_TOOL_ITERATIONS` | no | `30` | Inner-loop safety cap |
| `LLM_MAX_RETRIES` | no | `3` | Retries on transient LLM failures |
| `AGENT_LOG_FILE` | no | `agent.log` | Log destination |

## Running

```bash
python -m coding_agent.cli.main            # normal
python -m coding_agent.cli.main --verbose  # INFO logs on the console too
python -m coding_agent.cli.main --guardrails my_rules.json
```

```
Coding Agent — model: gpt-4o-mini
plan mode: off | supervision: on | /help for commands | exit/quit to leave
>> explain this repository
  -> list_files {}
  <- coding_agent/ | tests/ | README.md ...
  -> read_file {"path": "README.md"}
  <- # Coding Agent ...
  (inner loop iterations: 3)

Assistant:
This repository implements a coding agent... 
>> 
```

In-chat commands: `/plan on|off`, `/supervise on|off`, `/status`, `/tools`, `/help`,
and `exit` / `quit` (the only ways the program ends).

## Plan Mode

`/plan on`. Before executing anything, the agent makes an extra **tool-free** LLM call
to produce a numbered plan and shows it:

```
Proposed plan:
1. Read sample_project/stats.py
2. Run the tests to see the failure
3. Fix the bug and re-run the tests
Plan: [a]pprove / [m]odify / [r]eject:
```

- **approve** → the plan is added to the conversation and execution starts.
- **modify** → you describe changes, the plan is regenerated, and you are asked again.
- **reject** → nothing is executed; the rejection is recorded in the history.

With plan mode off, the agent executes directly.

## Supervision (human in the loop)

`/supervise on|off` (default **on**). When enabled, every **mutating** tool call
(`write_file`, `run_command`) asks first:

```
Approve run_command: pytest -q? [Y/n]
```

Read-only tools (`read_file`, `list_files`, `web_search`) never ask. A denial is sent
to the LLM as "Denied by the user. Do not retry the same action." so it can adapt.
The mechanism is generic: any future tool with `read_only = False` is supervised
automatically.

## Guardrails

`guardrails.json` is loaded at startup and **every** tool call is validated before
execution (`config/guardrails.py`):

```json
{
  "allowed_directories": ["."],
  "blocked_directories": [".git"],
  "blocked_files": [".env"],
  "blocked_commands": ["rm -rf", "git push", "sudo", "shutdown", "..."]
}
```

- Path arguments are fully resolved first, so `workspace/../secrets` cannot escape.
- `allowed_directories` — if non-empty, every path must be inside one of them.
- `blocked_files` — names (block every `.env`) or specific paths.
- `blocked_commands` — case- and whitespace-insensitive substring match.

A violation becomes an error tool-result explaining the block; the agent keeps running.

## Error handling

| Failure | Behaviour |
|---|---|
| LLM network / rate-limit / 5xx | Retried with exponential backoff; then a readable CLI error — conversation intact |
| Tool failure (missing file, permission denied, ...) | `ToolError` → error result fed back to the LLM |
| Command timeout / non-zero exit | Timeout → error result; non-zero exit is reported data, not a failure |
| Unknown tool / malformed arguments | Error result naming the available tools |
| `Ctrl+C` mid-turn | Cancels the turn, not the program |

## Logging

`config/logging_config.py`: everything (DEBUG+) goes to `agent.log`; the console only
shows warnings (or INFO with `--verbose`). Every LLM call, tool call, guardrail
decision and supervision answer is logged.

## Tests

```bash
python -m pytest tests/ -q     # 54 tests, no network or API key needed
```

The agent core is tested end-to-end with a scripted `FakeLLMClient` and `FakeIO`
(`tests/conftest.py`): multi-tool turns, error feedback, history persistence,
supervision approve/deny, plan approve/modify/reject, guardrail integration, retry
policy, plus unit tests for every tool.

## Example runs

Two real transcripts (with iteration counts) are in [`examples/`](examples/):

1. [`run_1_bugfix.md`](examples/run_1_bugfix.md) — the agent finds and fixes a bug in a
   small project and re-runs its tests.
2. [`run_2_explore_repo.md`](examples/run_2_explore_repo.md) — the agent explores this
   repository and explains it, using plan mode.

[`examples/retrospective.md`](examples/retrospective.md) answers: how many loop
iterations each run took, what went well, what went wrong, and what we would improve.

## Requirement checklist

| Assignment requirement | Implementation |
|---|---|
| Harness with LLM + tools, no frameworks | `agent/harness.py`; only the `openai` SDK + `httpx` |
| Two nested independent loops | outer: `cli/main.py::run_conversation_loop`; inner: `agent/harness.py::run_turn` |
| Interactive chat, program only exits on `exit`/`quit` | `cli/main.py` |
| History kept between turns | `agent/conversation.py` |
| `read_file` | `tools/read_file.py` |
| `write_file` (overwrite) | `tools/write_file.py` |
| `list_files` | `tools/list_files.py` |
| `run_command` (stdout + stderr + exit code) | `tools/run_command.py` |
| `web_search` (Tavily, replaceable provider) | `tools/web_search/` |
| Common tool interface | `tools/base.py` |
| LLM provider abstraction | `llm/base.py`, `llm/factory.py` |
| Plan mode (approve / modify / reject) | `agent/planner.py` |
| Supervision, read-only tools exempt | `agent/supervisor.py` |
| Guardrails config file (optional extra) | `guardrails.json` + `config/guardrails.py` |
| Error handling | see table above |
| Logging | `config/logging_config.py` |
| Unit tests | `tests/` (54 tests) |
| Two example runs + retrospective | `examples/` |
