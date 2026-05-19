# Weekly Engineering Status Skill

## Purpose

Generate compact weekly engineering status reports from:

- GitHub PRs
- Jira tickets
- git branches
- commits
- slides/docs
- existing engineering notes

The report should be:

- concise
- engineering-focused
- context-centric
- AI-readable
- easy for managers and engineers to scan

---

# Output Format

Use exactly this structure:

```markdown
- <Date>

---

# <Area>

## <Context>

### <Sub-context>

- Owner: <name>
- Collaborators: <name>, <name>, ...
- Tags: `tagA` `tagB`

- This week:
  - <high-signal progress item>
  - <link>
    - <short description>
    - Jira ID (if any)
```

`<link>` can be any supporting evidence:

- PRs
- Jira tickets
- slides
- docs
- branch compare links
- dashboards

If information is missing:

- leave the field blank
- preserve the structure
- never invent information

Example:

```markdown
- May 14, 2026

---

# Backend compiler

## Register allocation

### Whole kernel CFG

- Owner: PoSheng
- Collaborators:
- Tags: `compiler` `cfg`

- This week:
  - Handle indirect jumps properly in whole-kernel CFG construction.
  - https://github.com/org/repo/pull/123
    - Adds conservative CFG edge modeling for indirect jump targets.
    - Jira ID: ...
```

---

# Grouping Rules

Group work by engineering context, NOT by person.

Preferred hierarchy:

```markdown
# Area
## Context
### Sub-context
```

Examples:

```markdown
# Backend compiler
## Register allocation
### Whole kernel CFG
```

```markdown
# Infrastructure
## Memory token assignment
### TensileLite
```

Avoid:

```markdown
# PoSheng
# Sean
```

unless explicitly requested.

---

# PR Extraction Rules

When PRs are available, extract:

- PR title
- PR URL
- author
- reviewers if available
- merged/open status
- affected subsystem
- short technical summary
- related Jira if mentioned

Use these signals to determine the proper context:

- file paths
- branch names
- PR title
- Jira keys
- touched components
- existing report headings

---

# High-Signal Rules

Prioritize:

- merged implementation work
- meaningful progress
- architecture/design changes
- blockers
- risks
- integration issues
- validation progress

Avoid:

- commit spam
- formatting-only changes
- rebases
- trivial edits
- noisy low-value summaries

Good:

```markdown
- Added CFG-aware waitcnt propagation.
```

Bad:

```markdown
- Updated files.
- Fixed issues.
- Worked on scheduler.
```

---

# Link Formatting Rules

Always use:

```markdown
- <link>
  - <description>
```

Descriptions should explain:

- why the link matters
- what changed
- what the PR/doc/Jira represents

Do NOT repeat raw titles unnecessarily.

---

# This Week Section Rules

The `This week` section should contain:

- concise progress summaries
- meaningful technical movement
- important blockers if present

Prefer:

```markdown
- Implemented predecessor propagation for waitcnt insertion.
```

Avoid:

```markdown
- Continued development.
```

---

# Missing Information Rules

If owner unknown:

```markdown
- Owner:
```

If no collaborators:

```markdown
- Collaborators:
```

Do NOT remove sections because data is missing.

---

# Engineering Style

Use:

- concise technical language
- subsystem-oriented grouping
- objective summaries
- implementation-focused wording

Assume audience includes:

- compiler engineers
- GPU kernel engineers
- tech leads
- managers

---

# Review Checklist

Before finalizing:

- markdown hierarchy is valid
- contexts are grouped correctly
- links are preserved exactly
- no hallucinated PRs/Jira
- summaries are concise
- low-signal noise removed
- structure remains compact and readable

---

# Goal

The generated report should allow readers to quickly answer:

- What moved this week?
- What is blocked?
- Which subsystem changed?
- What evidence supports the status?
- Which areas need attention?

without reading all PRs/Jira tickets manually.