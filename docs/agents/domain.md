# Domain Docs

This is a single-context repository.

## Before exploring

- Read `CONTEXT.md` at the repository root when it exists.
- Read relevant decisions in `docs/adr/` when they exist.
- If either is absent, proceed without treating that as a setup problem.

## File structure

```text
/
├── CONTEXT.md
├── docs/adr/
│   └── *.md
└── src/
```

Use the terminology defined in `CONTEXT.md` when naming domain concepts. If a needed term is missing, record that as a domain-modeling gap rather than silently introducing competing vocabulary.

If a proposed change conflicts with an ADR, call out the conflict explicitly instead of silently overriding it.
