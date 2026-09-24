## Session protocol (mandatory)

- At the start of every session, read HANDOFF.md before doing anything else.
- After completing any task that changes code, tests, config, or docs,
  update HANDOFF.md: layer status, open issues, next action, and append
  to the session log.
- Before ending a session, update HANDOFF.md even if the task is unfinished,
  recording where you stopped and why.
- In HANDOFF.md, never mark something VERIFIED unless you ran a command
  in the current session that confirms it.
- Never delete session-log entries.

## Live-test and API-call gate (hard rule)

NEVER run any of the following without explicit user approval **in the
current turn**. All three consume paid API quota:

- `py -3.11 -m pytest` without `-m "not live"`
- `py -3.11 -m pytest -m live`
- `py -3.11 scripts/run_l5_calibration.py` (any flags)

Routine offline verification is ALWAYS:

    py -3.11 -m pytest -q -m "not live"

## Project state and workflow

- Project state lives in HANDOFF.md only. Do not store project status in
  any other memory system.
- Always launch pytest and scripts from the repo root
  (C:\Users\ASUS\Documents\jokes\Joke_identification).
- Only the owner (Daren) edits HANDOFF.md. Other contributors note status
  in their PR description.
