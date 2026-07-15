# Example run 5 — Changing strategy: loop detection + asking for help

**Task:** an intentionally **under-specified** request — "Something in the appointments
feature is broken. Please fix it." — with no error message, no logs, no reproduction.
**Modes:** plan mode **off**, supervision **off**, observability **langfuse**.
**What it demonstrates (both guardrails fire in one run):**
1. **Loop detection** — while a subagent repeatedly tried to read a file at the wrong path
   (`tests/Feature/StoreUserAppointmentTest.php`, which doesn't exist — the file is under
   `tests/Feature/Appointments/`), the loop detector fired
   `(loop detected — asked the agent to change strategy)`, after which the agent corrected
   itself (listed the directory, found the real path).
2. **Insufficient evidence → `ask_user`** — lacking the information to actually diagnose a
   bug, the agent did **not guess**: it used `ask_user`, and its final answer enumerates
   exactly what it needs from the user to proceed.
**Result:** the agent stopped guessing and asked for specifics; no files were modified.

## Terminal transcript (verbatim, abridged in the middle)

````
Coding Agent — model: gpt-4o-mini
plan mode: off | supervision: on | /help for commands | exit/quit to leave
>> supervision: off
>>   -> delegate {"agent": "explorer", "task": "Investigate the appointments feature in the project, including its structure, relevant files, and potential sources of error."}
  [explorer] task: Investigate the appointments feature in the project, including its structure, relevant files, and potential sources of error.
  -> list_files {"path": "./HealthApi-AlbertoPizzi"}
  <- .ai/ | .git/ | .github/ | bootstrap/ | config/ | database/ | ...
  -> list_files {"path": "./HealthApi-AlbertoPizzi/src"}
  <- Appointments/ | Authentication/ | Clinics/ | Doctors/ | Security/ | Shared/ | Users/ | Application.php
  -> list_files {"path": "./HealthApi-AlbertoPizzi/src/Appointments"}
  <- App/ | Domain/
  ... (explorer maps App/{Controllers,Policies,Resources} and Domain/{Actions,DataTransferObjects,Enums,Models}, reads each file) ...
  -> read_file {"path": "./HealthApi-AlbertoPizzi/tests/Feature/Appointments/StoreUserAppointmentTest.php"}
  <- <?php | declare(strict_types=1); | use Carbon\CarbonImmutable; | use Database\Factories\ClinicFactory; ...
... [truncated, 4324 characters omitted]
  (inner loop iterations: 11)
  <- [explorer report] | The "appointments" feature ... resides within ... `src/Appointments` ...
... [truncated, 2902 characters omitted]
  -> delegate {"agent": "implementer", "task": "Identify and fix the issues causing the appointments feature to malfunction ..."}
  [implementer] task: Identify and fix the issues causing the appointments feature to malfunction ...
  -> read_file {"path": "./HealthApi-AlbertoPizzi/src/Appointments/Policies/AppointmentPolicy.php"}
  <- error: File not found: HealthApi-AlbertoPizzi/src/Appointments/Policies/AppointmentPolicy.php
  -> read_file {"path": "./HealthApi-AlbertoPizzi/tests/Feature/StoreUserAppointmentTest.php"}
  <- error: File not found: HealthApi-AlbertoPizzi/tests/Feature/StoreUserAppointmentTest.php
  -> read_file {"path": "./HealthApi-AlbertoPizzi/src/Appointments/Controllers/GetAppointmentController.php"}
  <- error: File not found: HealthApi-AlbertoPizzi/src/Appointments/Controllers/GetAppointmentController.php
  ... (the implementer guessed the pre-DDD layout; it then re-listed the real directories and re-read the correct files) ...
  -> read_file {"path": "./HealthApi-AlbertoPizzi/src/Appointments/App/Policies/AppointmentPolicy.php"}
  <- <?php | declare(strict_types=1); | namespace Lightit\Appointments\App\Policies; ...
  -> read_file {"path": "./HealthApi-AlbertoPizzi/tests/Feature/StoreUserAppointmentTest.php"}
  <- error: File not found: HealthApi-AlbertoPizzi/tests/Feature/StoreUserAppointmentTest.php
  (loop detected — asked the agent to change strategy)
  -> list_files {"path": "./HealthApi-AlbertoPizzi/tests/Feature"}
  <- Appointments/ | Clinics/ | Doctors/ | Users/ | ExampleTest.php
  -> list_files {"path": "./HealthApi-AlbertoPizzi/tests/Feature/Appointments"}
  <- DeleteUserAppointmentTest.php | StoreUserAppointmentTest.php
  -> read_file {"path": "./HealthApi-AlbertoPizzi/tests/Feature/Appointments/StoreUserAppointmentTest.php"}
  <- <?php | declare(strict_types=1); | use Carbon\CarbonImmutable; ...
... [truncated, 4324 characters omitted]
  (inner loop iterations: 10)
  <- [implementer report] | I've conducted an analysis of the appointments feature, focusing on ... authorization, data validation, and business logic. | ### Findings: ...
... [truncated, 2859 characters omitted]
  -> ask_user {"question": "Do you want me to implement the appointment overlapping logic in the StoreUserAppointment action to prevent conflicts, as detailed in my findings?"}

[agent question] Do you want me to implement the appointment overlapping logic in the StoreUserAppointment action to prevent conflicts, as detailed in my findings?
>   <- User answered: I don't have the error details or logs right now. Tell me exactly what information you need from me to proceed, and don't guess.
  (inner loop iterations: 4)

Assistant:
To proceed effectively with fixing the appointments feature, I need the following information from you:

1. **Detailed Error Messages**: If you have encountered specific error messages or behavior (e.g., HTTP status codes) while using the appointments feature, please share those.

2. **Use Cases**: Please describe any specific scenarios where the feature breaks. For example, does it happen when creating, updating, or deleting appointments?

3. **Log Files**: If there are any relevant log files (application logs, error logs) that could provide insight into the errors occurring, please mention them.

4. **Database Schema**: If there have been any recent changes to the database schema that might affect the appointments (like changes to the appointments table), please provide that context.

With this information, I can better diagnose the issue and implement a solution.

>>   (session summary saved to project memory)
Goodbye!
````

## Notes

- **Loop detector** (`agent/loop_detector.py`): warns/nudges after repeated identical
  (tool-call, result) pairs and aborts after the 4th. Here the nudge line
  `(loop detected — asked the agent to change strategy)` was enough — the implementer stopped
  re-reading the missing path and instead listed the directory to discover the real location.
- **`ask_user` + insufficient-evidence rule** (`INSUFFICIENT_EVIDENCE_INSTRUCTION` in
  `agent/prompts.py`): with no error details available, the agent asked rather than
  fabricating a fix, and its final message states precisely what it needs — the intended
  "stop and explain what's missing" behaviour.
- The middle of the transcript is abridged (`...`) for readability; the tool calls shown are
  verbatim. Nothing was written or executed — every tool used was `read_only`/`list_files`.
- This run also illustrates a real hazard the agent recovered from: the model initially
  assumed the classic `app/`-style Laravel layout, but this repo uses a DDD
  `src/<Context>/{App,Domain}` structure, so its first guessed paths 404'd.
