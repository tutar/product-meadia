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
