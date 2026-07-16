# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues in `tutar/product-meadia`. Use the `gh` CLI for issue operations.

## Conventions

- Create an issue: `gh issue create --title "..." --body "..."`
- Read an issue: `gh issue view <number> --comments`
- List issues: `gh issue list --state open --json number,title,body,labels,comments`
- Comment on an issue: `gh issue comment <number> --body "..."`
- Apply or remove labels: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- Close an issue: `gh issue close <number> --comment "..."`

Infer the repository from the Git remote when running `gh` inside this clone.

## Pull requests as a triage surface

PRs are not treated as a request surface for triage. Only GitHub issues enter the triage workflow.

## When a skill says “publish to the issue tracker”

Create a GitHub issue.

## When a skill says “fetch the relevant ticket”

Run `gh issue view <number> --comments` and inspect its labels and comments.
