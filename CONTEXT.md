# Product Media Generation

This context covers media assets produced or consumed while creating product videos.

## Agent workflow

- Manage GitHub Issues with `gh`; follow `docs/agents/issue-tracker.md`.
- Use the five canonical triage labels in `docs/agents/triage-labels.md`.
- Keep domain decisions in this context and `docs/adr/`, following `docs/agents/domain.md`.

## Language

**Persistent Media**:
An image, audio file, video clip, or final video retained across tool calls or referenced by task state and product data. Persistent Media must be represented by an Object Storage reference.
_Avoid_: Local output, temporary result, provider URL

**Object Storage**:
The durable storage boundary for Persistent Media, implemented by RustFS by default but not coupled to that provider.
_Avoid_: RustFS storage, local media directory

**Temporary Media**:
A process-local working file whose lifetime is limited to one tool invocation and which is not stored in task state or product data.
_Avoid_: Cached media, generated asset

**Provider URL**:
A third-party service URL used only as an ingestion source before media is copied into Object Storage.
_Avoid_: Media URL, persistent URL

**Media Reference**:
A stable Object Storage bucket and object key stored in product or task data; it does not grant access by itself.
_Avoid_: Media path, permanent URL, signed URL

**Media Access URL**:
A short-lived, presigned URL created on demand for an authorized reader of a Media Reference.
_Avoid_: Media reference, public URL

**Media Asset**:
An immutable, database-backed record for one object owned by a user and scoped to either a product or a video task. It is the durable boundary for storage identity, access, integrity, lifecycle, and availability; regeneration creates a new Media Asset rather than overwriting one.
_Avoid_: Media file, output file, mutable asset

**Unavailable Media**:
A legacy or retained Media Asset whose bytes can no longer be read and which must be regenerated before use.
_Avoid_: Missing URL, broken file

**Video Task**:
One user-owned request to generate a product video. It preserves the product snapshot, generated outputs, and its execution history independently of later product changes.
_Avoid_: Job, render request

**Creative Brief**:
The user-reviewable creative plan for a Video Task, defining its audience, core promise, visual and emotional direction, duration, and narrative pacing before a script or visual assets are generated.
_Avoid_: Hidden prompt, script, storyboard

**Shot Plan**:
The ordered, user-reviewable visual realization of an approved Creative Brief and Script. It supplies the editing blueprint before any image or video generation.
_Avoid_: Script, list of generated images, final timeline

**Shot**:
One ordered unit in a Shot Plan with a narrative purpose, product presentation, camera or motion direction, duration, aligned voiceover segment, image prompt, and video-motion prompt.
_Avoid_: Generated video clip, arbitrary scene

**Clip Segment**:
One model-constrained, renderable portion of a Shot. A Shot may contain multiple consecutive Clip Segments when its intended duration exceeds a selected video model's maximum duration.
_Avoid_: Shot, final composition

**Keyframe**:
The approved still-image visual anchor for one Clip Segment, used as its image-to-video input. A model may use one Keyframe or a start/end sequence.
_Avoid_: Product main image, packaging image, Shot

**Editing Blueprint**:
The approved, deterministic assembly instructions derived from a Shot Plan, including shot order, target durations, voiceover alignment, transitions, subtitles, and audio markers.
_Avoid_: Free-form post-generation editing, fixed-duration clip loop

**Runtime Guidance**:
An optional intended final-runtime budget for a Video Task. It guides Creative Brief and Shot Plan pacing but never truncates a final composition; without it, runtime follows the approved script and voiceover naturally.
_Avoid_: Hard duration limit, per-clip duration

**Execution Attempt**:
One contiguous run of a Video Task, including a retry. Attempts are retained in order so a later successful retry does not obscure an earlier failure.
_Avoid_: Retry log, task run

**Execution Log**:
The durable, user-visible history of a Video Task's execution attempts, stages, and substeps. It contains safe progress and diagnostic summaries, not prompts, raw model responses, or sensitive configuration.
_Avoid_: Debug log, provider trace

**Execution Stage**:
A user-meaningful grouping within an Execution Attempt, such as scriptwriting, image generation, video generation, or composition.
_Avoid_: Graph node, pipeline step

**Execution Substep**:
An observable unit of work or human-review wait within an Execution Stage, with a lifecycle, timing, and safe output or error summary.
_Avoid_: Internal node, log line

**Generation Record**:
An immutable, task-owned audit record for one model or renderer invocation. It links the Execution Substep to its normalized input, parameters, normalized output, and referenced Media Assets, while excluding credentials and transient access URLs.
_Avoid_: Execution log entry, raw HTTP trace, provider request log

**Normalized Generation Input and Output**:
The stable, provider-independent prompt, parameters, structured result, and Media Asset references retained in a Generation Record for inspection and dataset export. A separately retained sanitized Provider Payload Snapshot preserves the provider-specific JSON shape for diagnosis.
_Avoid_: Raw HTTP request, raw provider response, training export format

**Training Candidate**:
A Generation Record whose output has passed the relevant human review and is eligible for explicit training-dataset export. Rejected or regenerated records remain retained as negative examples with their improvement feedback, but are not positive candidates by default.
_Avoid_: All generated output, automatically exported training row

**Model Configuration**:
A User-owned configuration of one available model through a provider, including its credential reference, declared capabilities, and availability. It is designed to become Tenant-owned when multi-tenant ownership is introduced, without changing the model selections frozen by existing Video Tasks.
_Avoid_: Global model setting, task credential, provider secret

**Bring Your Own Key (BYOK)**:
The User-owned credential used by a Model Configuration to call its provider. It is encrypted at rest, decrypted only by the server for a provider invocation, and never returned to the client or persisted in task data, logs, or Generation Records. A platform default may be used when the User has not selected a BYOK configuration.
_Avoid_: Exposed API key, task API key, provider key in a prompt

**Stage Model Selection**:
The Video Task-owned, capability-compatible Model Configuration selected for one execution stage. It is frozen when the task is created and may be changed only before that stage begins; a change after output exists takes effect only through an explicit regeneration, which creates a new candidate and Generation Record.
_Avoid_: Global active model, retroactive model change, mutable generation provenance

**Provider Model Catalog**:
The platform-maintained catalog of provider model identities and their declared generation capabilities and constraints. A User may enable a catalog entry through a Model Configuration, but cannot make an incompatible model eligible for an execution stage. Custom compatible models, if introduced, are explicitly experimental and declare their capabilities before use.
_Avoid_: Unverified model name, user-claimed production capability, global provider configuration

**Model Selection Stage**:
A user-meaningful generation category with its own Stage Model Selection: creative planning, scriptwriting, keyframe image generation, clip video generation, voice generation, or (for viral tasks) source analysis/transcription. Deterministic final composition is not a model selection stage; its optional text optimization uses the creative-planning selection.
_Avoid_: Internal function model setting, renderer model choice

**Model Availability Failure**:
The condition in which the Model Configuration frozen for a stage cannot serve its requested operation, such as invalid credentials, exhausted quota, provider outage, or model withdrawal. The task may retry the same configuration but must never silently switch models; it waits for the User to select a replacement and explicitly retry.
_Avoid_: Silent fallback, hidden model substitution, unexplained quality change

**Model Verification**:
The explicit, low-cost check that a User's Model Configuration can authenticate and reach its declared Provider Model Catalog entry. Only a verified, capability-compatible configuration is selectable for a task stage; where safe verification is unavailable, its first real invocation determines availability.
_Avoid_: Test generation, assumed-valid credential, selectable unverified model

**Model Invocation Boundary**:
The application service boundary that invokes every business model through the LiteLLM Python SDK using the task's frozen Stage Model Selection and a transiently decrypted BYOK or platform-default credential. A local LiteLLM proxy is not a required business routing boundary.
_Avoid_: Per-tool provider client, global proxy-only model routing, persisted decrypted credential

**Stage Model Default**:
A User's preferred verified and capability-compatible Model Configuration for a Model Selection Stage. It prepopulates a new Video Task but is copied into that task as an independent Stage Model Selection, so later default changes never alter existing tasks.
_Avoid_: Live task default, global active model, required repeated model selection

**Model Resolution Snapshot**:
The non-sensitive provider, model identity, catalog capability revision, resolved selection version, and invocation parameters frozen with a Generation Record. It remains explainable after a User changes or revokes a configuration, but never contains a credential or provider authorization data.
_Avoid_: Mutable model provenance, stored API key, provider authorization trace

**Model Configuration Revocation**:
The disabling of a Model Configuration that destroys its BYOK while retaining its non-sensitive historical identity. A configuration referenced by a task cannot be reused; unfinished stages wait for an explicit replacement, while only never-referenced configurations may be deleted.
_Avoid_: Destructive historical deletion, silent credential rotation, automatic replacement model

**Auto-Approval Preference**:
A User-owned setting that automatically approves newly completed Script or Image Candidates at their review point. It never advances a candidate that was already waiting for review when the setting changed.
_Avoid_: Task default, retroactive approval

**Video Clip Candidate**:
An immutable, task-owned Persistent Media version generated from one approved Image Candidate. Each current candidate is reviewed independently before it may be used in a Final Composition.
_Avoid_: Generated video, mutable clip

**Final Composition Candidate**:
An immutable, task-owned Persistent Media version created by combining approved Video Clip Candidates, audio, and captions. Its approval completes a Video Task.
_Avoid_: Final video, render output

**Video Review**:
The waiting state in which each current Video Clip Candidate is approved or replaced by a newly generated candidate. All current clip candidates must be approved before composition begins.
_Avoid_: Final approval, video generation

**Composition Review**:
The waiting state in which a Final Composition Candidate is approved or rejected. Approval completes the Video Task; rejection creates a replacement Final Composition Candidate from the approved inputs.
_Avoid_: Video review, retry

**Task Cancellation**:
The requested and confirmed stop of a non-terminal Video Task. Cancellation preserves the task and its Execution Log until the user separately deletes the terminal task.
_Avoid_: Task deletion, retry cancellation

**Cancellation Requested**:
The non-terminal state after a user asks to stop a Video Task while its current remote operation is still being allowed to finish or time out. No later Execution Substep may start from this state.
_Avoid_: Failed, cancelled

**Cancelled Task**:
A terminal Video Task whose work was stopped by Task Cancellation. It is distinct from a failed task and may be deleted.
_Avoid_: Failed task, deleted task

**Task Deletion**:
The irreversible removal of a terminal Video Task and its task-owned business records. It schedules task-exclusive Persistent Media for the established retention cleanup rather than making their bytes immediately inaccessible through an untracked deletion.
_Avoid_: Task cancellation, archive

**Task-Exclusive Media**:
Persistent Media owned by one Video Task and not referenced by a Product or another surviving business record. Task Deletion may schedule only Task-Exclusive Media for cleanup.
_Avoid_: Generated media, task output
