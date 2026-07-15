# Retrospective (deliverable 3)

## How many loop iterations did the agent do in each case?

**Run 1 — bug fixing** (`run_1_bugfix.md`):
**6 inner-loop iterations** (6 LLM calls in the turn, plus 1 automatic retry of a failed call — see below), executing **6 tool calls**:
`list_files` → `read_file` ×2 → `run_command` (pytest, exit 1) → `write_file` (fix) → `run_command` (pytest, exit 0), then a final tool-free answer.

**Run 2 — repository exploration** (`run_2_explore_repo.md`):
**1 planning call + 4 inner-loop iterations** (5 LLM calls total), executing **4 tool calls**:
`list_files` → `read_file` ×2 → `web_search`, then the final tool-free answer.

## What went well

- **The loop converged fast in both runs.** The agent followed the canonical debug cycle in run 1 (read → reproduce failure → fix → re-verify) without being told to, and its fix was correct on the first attempt.
- **Error handling paid off for real.** Mid-run the model once returned malformed JSON arguments for `write_file`; the retry wrapper transparently repeated the call (`[WARNING] LLM call failed (attempt 1/3)… retrying`) and the run continued unharmed. Earlier, an invalid API key produced a clean `LLM failure: … 401` message and the chat survived instead of crashing.
- **Supervision behaved exactly as specified**: every `run_command`/`write_file` asked `[Y/n]`; the read-only exploration in run 2 never prompted.
- **Plan mode worked end-to-end**: the plan was generated without executing anything, approved, and the execution matched it step for step.
- **Verification is built into the agent's behaviour**: it re-ran pytest after the fix rather than declaring success blindly.

## What went wrong

- **One malformed tool call from the model** (invalid JSON in `write_file` arguments) cost an extra LLM round-trip. Recovered automatically, but it is wasted latency/tokens.
- **`web_search` snippets were noisy**: the Tavily result for the AWS Marketplace page contained scraped HTML fragments. The model coped, but cleaner snippet post-processing would reduce context pollution.
- **Whole-file rewrites are blunt.** `write_file` replaces the entire file, so a one-line fix resends the whole file content — fine for a 25-line demo, expensive and riskier for large files.
- **Long tool outputs enter the history verbatim** (only capped at a fixed limit). In long sessions this would inflate token usage.

## What we would improve

1. **An `edit_file` (search/replace or diff-based) tool** so small changes don't rewrite whole files.
2. **Context compaction**: summarize or drop old tool results once a turn finishes, keeping the token footprint flat over long conversations.
3. **Search-result cleaning** (strip HTML artifacts, dedupe) before handing snippets to the model.
4. **Structured plan output** (JSON list of steps) so the harness could track/report per-step progress during execution.
5. **Streaming responses** for better UX on long answers, and parallel execution of independent tool calls within one iteration.
