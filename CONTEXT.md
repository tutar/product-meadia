# Product Media Generation

This context covers media assets produced or consumed while creating product videos.

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
