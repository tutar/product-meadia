# Review Voiceover Candidates and recompose deterministically

Voice Generation is a model-selection stage, while Voiceover Review is a separate user decision boundary. New Video Tasks retain immutable, versioned Voiceover Candidates that reference their audio Media Asset and retain narration text, timing, review status, and generation provenance. Every task type that generates narration reaches Voiceover Review; a task with lip sync generates lip sync only after the Voiceover Candidate is approved.

A rejected Voiceover Candidate must change an auditable TTS input: its narration text or the explicitly selected compatible Voice Generation Model Configuration. It creates a new candidate, invokes only the voice-generation selection, and uses that selection's latest configuration revision unless the User explicitly changes configuration. Voiceover Review always requires explicit approval in the first release.

Final composition is deterministic and has no model-selection stage. Composition Review replaces the ambiguous recompose action with three explicit choices: edit and save an Editing Blueprint before deterministic re-rendering; Review Rewind to Voiceover Review; or Review Rewind to Video Review for one or more selected Clip Segments. A re-render requires a saved Blueprint change. A changed Voiceover Candidate or Video Clip Candidate enters Editing Blueprint Review only when its duration changes; the initial flow and unchanged durations proceed directly to composition.

## Consequences

- `voice_review` is a user-visible review state and execution-history wait for new tasks; pre-existing tasks are not migrated.
- Voiceover Candidate history, feedback, and selection provenance remain immutable and auditable; only the current approved candidate may drive composition.
- A Voiceover Review approval advances automatically to composition, or to lip-sync generation and then composition for a task with lip sync.
- Review Rewind retains unaffected approved candidates and never silently invokes TTS, video, or creative-planning models.
- Composition feedback remains retained audit context; it is never interpreted by a model to alter an Editing Blueprint.
- Editing Blueprint Review is conditional rather than an additional mandatory checkpoint in the initial flow.
- This refines ADR 0004's final-composition replacement consequence: a final-composition rejection no longer implies an implicit model-assisted regeneration.
