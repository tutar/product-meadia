# Plan and approve shots before generating video

Promo video generation uses an approved Creative Brief, Script, Shot Plan, Keyframes, Video Clips, and Editing Blueprint in that order. The previous one-pass script-to-prompts flow and fixed-duration clip loop were simpler, but hid creative decisions until after expensive generation and made visual pacing hard to control. Each planning layer is reviewed before its dependent assets are generated; after approval, the Editing Blueprint deterministically assembles approved clips while allowing only explainable timing adjustments for the actual audio and media durations.

## Consequences

- Promo has review points for Creative Brief, Script, Shot Plan, Keyframes, Video Clips, and the final composition.
- A Shot carries its narrative, visual, motion, duration, and voiceover-alignment instructions, making generation and feedback shot-specific.
- Runtime Guidance is optional and may be any intended final-runtime budget; it guides planning without truncating the final composition. Individual Shots are split into model-constrained Clip Segments when necessary.
- Viral and personify retain their existing flows initially; viral analysis can later become Creative Brief input.
