# Example run 4 — Persistent memory across sessions

**Task:** in a **fresh session** (new process, empty conversation history), recall what the
agent learned about the HealthApi project in run 3.
**Modes:** plan mode **off**, supervision **off**, observability **langfuse**.
**What it demonstrates:** the session summary saved to `.agent/memory.json` at the end of
run 3 is (a) shown by the `/memory` command and (b) loaded into the system prompt at startup,
so the agent answers **from `[memory]`** without re-exploring the repository.
**Result:** `/memory` prints the run-3 summary; the agent answers in **1 inner-loop iteration**
(no tools needed) and labels the facts as coming from memory.

> This run depends on run 3 having been executed first (it writes the memory this run reads).
> Memory lives in `.agent/memory.json` (gitignored).

## Terminal transcript (verbatim)

````
Coding Agent — model: gpt-4o-mini
plan mode: off | supervision: on | /help for commands | exit/quit to leave
>> previous sessions:
- [2026-07-15] Analyzed the Laravel API in `./HealthApi-AlbertoPizzi`, delegating exploration and Laravel concept research. Key findings include the project directory structure, important dependencies (like Sanctum for authentication), potential risks (such as dependency management), and useful commands for operation. Resolutions were made on architecture and dependencies, with no unresolved issues noted. All insights are documented for future reference.
>>   (inner loop iterations: 1)

Assistant:
Based on the persistent memory from our previous session, here's what we already know about the HealthApi Laravel project:

### Key Dependencies:
- **Sanctum**: Used for authentication.

### Useful Commands:
- No specific commands were detailed in the previous session's entries.

### Origin of Information:
- Key dependencies and useful commands information come from [memory].

If you need more specific details or additional information, please let me know!

>>   (session summary saved to project memory)
Goodbye!
````

## Notes

- The first `>>` line is the output of the `/memory` command — the persisted run-3 summary.
- The agent needed **no tool calls**: the memory is injected into the system prompt at
  startup (`build_system_prompt(..., memory=...)`), so the model answers directly and tags
  the facts `[memory]` per the source-labeling instruction.
- The answer is only as rich as the stored summary (a deliberately short, ≤5-line session
  summary). It faithfully reflects what was persisted rather than re-deriving it — which is
  exactly the behaviour under test. Running a full analysis first (run 3) and then asking
  follow-ups here shows memory surviving across process boundaries.
- This session also appends its own summary to memory on `exit`.
