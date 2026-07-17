# Delete terminal tasks with deferred media cleanup

Only terminal Video Tasks may be deleted; a non-terminal task must first complete cooperative Task Cancellation. A cancellation is recorded separately from failure: remote work already in flight may finish or time out, but no downstream substep starts, and the task becomes a Cancelled Task. Deletion immediately removes the task's business records and schedules task-exclusive Media Assets for the existing seven-day asynchronous cleanup window, rather than directly deleting object-store bytes during the request.

## Consequences

- An in-flight worker cannot race a direct task deletion; it observes cancellation before downstream work begins.
- Deleted tasks disappear from product and task views immediately, while their private object bytes retain a short recovery and cleanup window.
- Media shared with a Product or another surviving business record is not deleted as task-exclusive media; deletion determines this from surviving references rather than from the task foreign key alone.
- Deleting a task never deletes its source Product or other tasks that use that Product; each task retains its own product snapshot until deletion.
