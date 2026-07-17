# Retain structured execution history for video tasks

Video Tasks retain a user-visible Execution Log grouped into Execution Attempts, Execution Stages, and Execution Substeps. The log records real-time lifecycle, duration, safe output or error summaries, and review waits, while excluding prompts, raw model responses, and sensitive configuration; this makes retries diagnosable without conflating their history or exposing provider internals.

## Consequences

- A retry creates a new Execution Attempt and retains prior attempts.
- Scriptwriting is a distinct Execution Stage whose work, review wait, and approval can be understood together.
- The UI may collapse successful history while expanding active and failed work without changing the stored history.
