# Retain generation records for audit and training

Each model or renderer invocation will create an immutable, task-owned Generation Record separate from the safe user-facing Execution Log. Generation Records retain normalized inputs, parameters, outputs, and Media Asset references indefinitely so they support quality diagnosis and future training datasets; when their Video Task is deleted, they follow the established delayed cleanup lifecycle with the task's other exclusive records and media.

## Consequences

- Execution Logs continue to exclude prompts, raw provider responses, credentials, and transient access URLs.
- Generation Records store media by Media Asset reference rather than a Data URI, provider URL, or presigned URL.
- Task detail can expose generation provenance without turning the Execution Log into a provider-debug dump.
- Complete Generation Records are visible only to the task owner; a future organization may grant the same access to an administrator or a member with an explicit generation-audit permission.
- Each record retains both provider-independent normalized input/output for inspection and dataset export, and a sanitized provider-payload snapshot for diagnosis; raw HTTP headers, credentials, transient URLs, and Data URIs are not retained.
- Task Detail exposes completed and review-stage work through a Generation Materials panel scoped to the selected stage, with the newest record selected by default and prior attempts or regenerations available as history; the Execution Log remains a concise timeline.
- Human-approved outputs become Training Candidates for explicit dataset export. Rejected or regenerated records remain retained as negative examples with their improvement feedback but are not positive candidates by default.
- A Generation Record is created for each semantic LLM, multimodal-model, or renderer invocation and each regeneration or recomposition, but not for polling, transport retries, downloads, object-storage operations, or presigning.
- Each record freezes the provider/model identity, parameters, prompt-template content hash, workflow git commit, input Media Asset checksums, creation time, and its Execution Attempt and Execution Substep links so quality changes remain explainable.
