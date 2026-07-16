# Persist all durable media in object storage

All media that survives a tool invocation or is referenced by task/product state must be stored as a private Media Asset in object storage, with RustFS as the default S3-compatible implementation. Business records store an asset ID backed by bucket and object key; they never persist local paths, provider URLs, or presigned URLs. This makes media durable across workers and deployments, enforces user ownership, and keeps the application portable to another object-store provider.

## Consequences

- Object storage is a fail-closed dependency: a generation node succeeds only after upload, validation, and durable reference creation succeed.
- Applications access media through `MediaService`; external providers and authorized clients receive short-lived, read-only presigned URLs.
- Media Assets are immutable. Replacements, failed outputs, and orphans are retained for seven days before asynchronous deletion.
- Existing paths and URLs require an idempotent migration; irrecoverable media is marked `unavailable`.
