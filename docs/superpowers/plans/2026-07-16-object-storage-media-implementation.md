# Private Media Asset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every persistent product and video-pipeline media value to private, immutable Media Assets stored through a provider-neutral ObjectStorage interface with RustFS as the default adapter.

**Architecture:** APIs, workers, Agents, and tools reference asset IDs and call MediaService. MediaService validates bytes, calculates integrity metadata, owns idempotency and lifecycle rules, and delegates object operations to ObjectStorage; RustFS is isolated in one S3-compatible adapter. Temporary paths and Provider URLs exist only inside one ingestion/tool call.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, PostgreSQL, Celery, boto3-compatible S3 client, RustFS, React/TypeScript, pytest, Playwright.

## Global Constraints

- Persistent Media is represented by immutable `media_assets`; business records and task state never persist local paths, Provider URLs, object keys, or presigned URLs.
- Objects are private and access URLs default to one hour.
- Media writes are fail-closed: validation, upload, readability confirmation, asset creation, and business-reference update must succeed before a node succeeds.
- Record SHA-256, byte size, content type, ownership, category, status, and optional idempotency key.
- Reuse is limited to the same user and task/node idempotency boundary; never deduplicate globally across users.
- Replacements and failed/orphan assets are retained for seven days; deleting a task schedules deletion of task-owned assets.
- External providers receive a fresh read-only URL on every call/retry; precise retries reuse already-successful asset IDs.
- RustFS SDK usage and key construction are confined to the storage adapter/MediaService boundary.
- `api/openapi.yaml` and `db/schema.sql` remain authoritative.
- Tests use the five user-approved seams: ObjectStorage, MediaService, HTTP API, video-task behavior, and migration command.

---

### Task 1: Media Contract, DDL, and ORM

**Files:**
- Modify: `db/schema.sql`
- Modify: `api/openapi.yaml`
- Create: `src/models/media_asset.py`
- Modify: `src/models/product.py`
- Modify: `src/models/generated_image.py`
- Modify: `src/models/task.py`
- Modify: `src/models/__init__.py`
- Create: `tests/test_media/test_contracts.py`

**Interfaces:**
- Produces: `MediaAsset`, `MediaCategory`, `MediaStatus`; product/image/task asset foreign keys.

- [ ] Write a failing contract test asserting `media_assets`, asset FKs, `/media/{asset_id}/access`, and absence of persistent URL/path fields in final schemas.
- [ ] Run `pytest tests/test_media/test_contracts.py -v`; confirm failure is missing media contract.
- [ ] Add complete DDL/OpenAPI and matching ORM. Include unique `(owner_user_id, idempotency_key)` when the key is non-null, ownership indexes, status/category checks, `superseded_at`, and `delete_after`.
- [ ] Run the contract/model tests and existing database tests.
- [ ] Commit: `feat: define private media asset contract`.

### Task 2: ObjectStorage Interface and RustFS Adapter

**Files:**
- Create: `src/media/storage.py`
- Create: `src/media/rustfs.py`
- Modify: `src/config.py`
- Modify: `requirements.txt`
- Create: `tests/test_media/test_storage_contract.py`
- Create: `tests/test_media/test_rustfs_integration.py`

**Interfaces:**
- Produces:
  - `ObjectStorage.upload(bucket, key, stream, content_type) -> None`
  - `download(bucket, key) -> bytes`
  - `exists(bucket, key) -> bool`
  - `delete(bucket, key) -> None`
  - `presign_get(bucket, key, expires_seconds=3600) -> str`

- [ ] Write one storage-contract tracer test using an in-memory boundary implementation: private upload → exists → download → delete.
- [ ] Run it RED because `ObjectStorage` does not exist.
- [ ] Implement the protocol and minimal RustFS adapter; adapter maps S3 errors to typed storage exceptions and never exposes credentials.
- [ ] Add a marked integration test using configured RustFS, verifying private object round-trip and presign.
- [ ] Run unit tests; run RustFS integration only when configuration is present.
- [ ] Commit: `feat: add object storage boundary and RustFS adapter`.

### Task 3: MediaService Ingestion, Integrity, and Idempotency

**Files:**
- Create: `src/media/service.py`
- Create: `src/media/validation.py`
- Create: `src/media/keys.py`
- Create: `tests/test_media/test_media_service.py`

**Interfaces:**
- Produces:
  - `create_from_bytes(owner_user_id, category, content, content_type, product_id=None, task_id=None, idempotency_key=None) -> MediaAsset`
  - `ingest_provider_url(..., provider_url, ...) -> MediaAsset`
  - `get_access_url(asset_id, owner_user_id, expires_seconds=3600) -> MediaAccess`
  - `mark_superseded(asset, now) -> None`

- [ ] RED: create PNG bytes and assert returned asset has literal known SHA-256, size, private bucket/key, and available status.
- [ ] GREEN: validate supported image/audio/video signatures, compute metadata, upload, confirm `exists`, flush asset, and fail closed.
- [ ] RED/GREEN: same owner/idempotency key returns the existing asset without a second upload; another user creates a distinct asset.
- [ ] RED/GREEN: upload/readability/database failure never returns an asset; uploaded-but-uncommitted objects are eligible for orphan cleanup.
- [ ] RED/GREEN: access rejects another user and signs for exactly 3600 seconds.
- [ ] Commit: `feat: add fail-closed MediaService`.

### Task 4: Authenticated Media HTTP API

**Files:**
- Create: `src/schemas/media.py`
- Create: `src/api/media.py`
- Modify: `src/main.py`
- Create: `tests/test_media/test_media_api.py`

**Interfaces:**
- Produces:
  - `POST /api/v1/media/upload`
  - `GET /api/v1/media/{asset_id}/access`

- [ ] RED: authenticated upload returns asset metadata/ID but no bucket, key, or persistent URL.
- [ ] GREEN: route streams upload through MediaService and scopes product/task ownership.
- [ ] RED/GREEN: owner receives `{url, expires_at}`; other user receives 404.
- [ ] RED/GREEN: unavailable asset returns a regeneration-required conflict rather than a broken URL.
- [ ] Commit: `feat: expose private media access API`.

### Task 5: Product Main Images and Frontend Asset Access

**Files:**
- Modify: `src/api/products.py`
- Modify: `src/services/main_image_candidates.py`
- Modify: `src/services/sample_catalog.py`
- Modify: `src/schemas/product.py`
- Modify: `frontend/src/api/catalog.ts`
- Create: `frontend/src/hooks/useMediaAccess.ts`
- Modify: `frontend/src/pages/ProductsPage.tsx`
- Modify: `frontend/src/pages/ProductFormPage.tsx`
- Modify: `frontend/src/pages/CreateTaskPage.tsx`
- Create: `tests/test_media/test_product_media.py`
- Create: `frontend/tests/media-access.spec.ts`

**Interfaces:**
- Consumes: MediaService and `/media/{id}/access`.
- Produces: product `main_image_asset_id`; refreshable frontend media hook.

- [ ] RED/GREEN: product upload/AI candidate confirmation stores only `main_image_asset_id`; replacing an image supersedes the old asset.
- [ ] RED/GREEN: sample images are ingested as assets during catalog initialization.
- [ ] RED/GREEN: frontend requests access URLs by asset ID, refreshes near expiry/401/403, and never renders bucket/key.
- [ ] Remove new writes to `main_image_url` and update OpenAPI/frontend types.
- [ ] Commit: `feat: migrate product images to Media Assets`.

### Task 6: Generated Images and Provider Input URLs

**Files:**
- Modify: `src/tools/image_gen.py`
- Modify: `src/agents/promo_graph.py`
- Modify: `src/agents/viral_graph.py`
- Modify: `src/agents/personify_graph.py`
- Modify: `src/tasks/video_tasks.py`
- Modify: `src/api/tasks.py`
- Modify: `src/schemas/task.py`
- Create: `tests/test_media/test_image_pipeline.py`

**Interfaces:**
- Agent state uses image asset IDs; generated image rows use `asset_id`.

- [ ] RED: a generated Provider URL is ingested before the node output is accepted and task state contains only asset IDs.
- [ ] GREEN: copy Provider output through MediaService, store generated-image asset references, and sign fresh input URLs for downstream video/lipsync calls.
- [ ] RED/GREEN: retry with an existing node idempotency key reuses the asset and does not regenerate/reupload.
- [ ] RED/GREEN: upload failure fails the node and persists neither Provider URL nor local path.
- [ ] Commit: `feat: persist generated images as Media Assets`.

### Task 7: Audio, Video Clips, Lipsync, Source Video, and Final MP4

**Files:**
- Modify: `src/tools/tts.py`
- Modify: `src/tools/video_gen.py`
- Modify: `src/tools/lipsync.py`
- Modify: `src/tools/transcription.py`
- Modify: `src/tools/render.py`
- Modify: `src/agents/state.py`
- Modify: `src/agents/promo_graph.py`
- Modify: `src/agents/viral_graph.py`
- Modify: `src/agents/personify_graph.py`
- Modify: `src/tasks/video_tasks.py`
- Create: `tests/test_media/test_video_pipeline.py`

**Interfaces:**
- Task/Agent media state uses asset IDs for source, clips, audio, lipsync, character, and final video.

- [ ] For each media category, write one vertical test: provider/local output → MediaService asset → downstream fresh access URL.
- [ ] Make TTS, clips, lipsync, source video, and final MP4 fail closed on persistence failure.
- [ ] Ensure HyperFrames final local file is temporary and `result_video_asset_id` is committed before done.
- [ ] Verify exact retry reuses successful assets and preserves execution progress.
- [ ] Commit: `feat: migrate video pipeline media to private assets`.

### Task 8: Task/Product Reads and Frontend Preview/Download

**Files:**
- Modify: `src/api/tasks.py`
- Modify: `src/schemas/task.py`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/pages/TaskDetailPage.tsx`
- Modify: `frontend/src/api/catalog.ts`
- Create: `tests/test_media/test_task_media_access.py`
- Modify: `frontend/tests/media-access.spec.ts`

**Interfaces:**
- Task/product responses expose asset IDs; previews/downloads resolve through media access API.

- [ ] RED/GREEN: task detail/image review/final download expose asset IDs and authorized access URLs only on demand.
- [ ] RED/GREEN: expired image/video URL refresh preserves preview; final download works across API and worker containers.
- [ ] Remove local `FileResponse`, Provider redirect, and persistent URL compatibility from normal runtime.
- [ ] Commit: `feat: serve task media through private access URLs`.

### Task 9: Migration and Unavailable Media

**Files:**
- Create: `src/media/migration.py`
- Create: `scripts/migrate_media_assets.py`
- Create: `tests/test_media/test_migration.py`

**Interfaces:**
- Produces: resumable `migrate_batch(after_id, limit) -> MigrationReport`.

- [ ] RED/GREEN: local path, Provider URL, and old object-store URL each become a Media Asset and business FK.
- [ ] RED/GREEN: rerun skips completed records and resumes after a checkpoint.
- [ ] RED/GREEN: missing/expired media creates an `unavailable` asset and the API reports regeneration required.
- [ ] Ensure new code never writes legacy formats during the migration window.
- [ ] Commit: `feat: add resumable legacy media migration`.

### Task 10: Lifecycle Cleanup and Task Deletion

**Files:**
- Create: `src/tasks/media_tasks.py`
- Modify: `src/tasks/celery_app.py`
- Modify: `src/api/tasks.py`
- Create: `tests/test_media/test_lifecycle.py`

**Interfaces:**
- Produces cleanup of due superseded/failed/orphan assets and task-deletion scheduling.

- [ ] RED/GREEN: superseded/failed/orphan assets are retained until exactly seven days then deleted.
- [ ] RED/GREEN: current product image/final video/approved images are retained.
- [ ] RED/GREEN: deleting a task schedules all task-owned assets and later removes objects/rows idempotently.
- [ ] Commit: `feat: add Media Asset lifecycle cleanup`.

### Task 11: Remove Legacy Persistence and Full Verification

**Files:**
- Modify: `db/schema.sql`
- Modify: `api/openapi.yaml`
- Modify: affected backend/frontend tests and documentation only where contract drift is found.

**Interfaces:**
- Produces a codebase with no persistent local path, Provider URL, or presigned URL fields.

- [ ] Scan runtime/DDL/API for legacy `main_image_url`, `image_url`, `result_video_url`, `final_video_path`, persistent audio/video URL state; classify temporary/provider inputs separately.
- [ ] Run `pytest -m 'not integration' -q`.
- [ ] Run configured RustFS/media integration tests.
- [ ] Run `npm run lint`, `npm run build`, and Playwright media scenarios.
- [ ] Run `git diff --check` and verify OpenAPI/DDL/ORM/frontend type alignment.
- [ ] Commit only necessary consistency corrections: `chore: complete Media Asset migration`.
