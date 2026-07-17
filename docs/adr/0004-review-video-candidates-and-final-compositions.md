# Review video candidates and final compositions separately

Video Clip Candidates and Final Composition Candidates represent different user decisions and must be reviewed at separate task states. Every current Video Clip Candidate is approved or replaced independently before composition. The resulting Final Composition Candidate is then reviewed; only its approval completes the Video Task. Replacing a clip regenerates only that clip, while rejecting a final composition creates a new composition from the approved clips, audio, and captions.

Users may automatically approve newly completed scripts and image candidates through their own preferences. These settings are evaluated when a review point is reached and never retroactively advance a task already waiting for review. Video and composition reviews always require explicit approval.

## Consequences

- `video_review` and `composition_review` are distinct task states and execution-history waits.
- Replacements retain prior immutable Media Assets and mark the superseded candidate as rejected; only the current candidate can advance a task.
- Automatic approval is visible in Execution History so task progress remains auditable.
