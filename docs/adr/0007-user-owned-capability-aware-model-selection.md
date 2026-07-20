# Use user-owned, capability-aware model selection

Business model calls use the LiteLLM Python SDK with a User-owned BYOK or optional platform default, rather than routing through a globally configured model proxy. The platform maintains a Provider Model Catalog that declares capabilities and constraints; Video Tasks freeze a compatible Stage Model Selection for each user-meaningful generation stage so unavailable models never silently fall back and historical Generation Records remain explainable.

## Consequences

- Tenant ownership is intentionally deferred: each User owns Model Configurations and Stage Model Defaults until a future tenant migration changes only their ownership boundary.
- Model Configurations require low-cost verification before they are selectable; credentials are encrypted at rest, transiently decrypted only for invocation, and never exposed in clients, task data, Execution Logs, or Generation Records.
- A task can edit only an unstarted stage selection. Regeneration after output exists creates a new candidate and Generation Record using the explicitly chosen replacement.
- Planning, scriptwriting, keyframe generation, clip generation, voice generation, and viral analysis/transcription have separate selections; deterministic composition does not. Optional composition text optimization uses the creative-planning selection.
- Revoking an in-use configuration destroys its credential and makes unfinished stages wait for a user-selected replacement, while preserving non-sensitive Model Resolution Snapshots for completed work.
