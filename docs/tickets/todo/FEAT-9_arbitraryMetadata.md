---
id: FEAT-9
title: Track arbitrary additional metadata on tickets/groups
status: todo
priority: 1
requires: []
---

# Track arbitrary additional metadata on tickets/groups

## Context

Comes out of designing a `video-planner` skill (see `.claude/skills/video-planner/SKILL.md`) that drafts Dev Log video scripts from Docket ticket data and git history. That skill needs to know which tickets or ticket-groups have already been used in a past video, so it does not re-suggest them and so it can suggest "what's new since the last video."

That video-tracking need is just one consumer. The underlying gap is that Docket tickets have no place to attach arbitrary, tool-defined metadata without touching the core frontmatter schema. This ticket generalizes the mechanism to a `metadata: {key: value}` style store, of which "which video covered this ticket" is one example use, not the whole scope.

This ticket is scoped to the metadata/tracking mechanism only, not the video-planner skill itself (that is separate work, deliberately decoupled so this can land on its own PR/version bump).

## Decision needed

Pick one of:

- A new ticket frontmatter key, `metadata`, holding a free-form `{key: value}` map that any tool or skill can read/write its own namespaced entries into (e.g. `metadata.video`). Would be a **major** version bump per this repo's versioning rules, since it changes ticket frontmatter schema, but only once, future consumers reuse the same key instead of each adding their own.
- A separate registry file (outside individual ticket frontmatter) that records arbitrary key/value metadata per ticket id or ticket-group, keyed by whatever the consumer needs (e.g. video slug/date for the video use case).

Registry file avoids touching the frontmatter schema and the `major` bump that implies, and keeps consumer-specific concerns (like "video") outside Docket's core ticket model, similar to how the repo keeps `scripts/` standalone from `docket`. Leaning registry-file for that reason, but not decided.

## Assumptions from the design discussion

- Repo-agnostic: the mechanism should work for any repo with Docket deployed, not just this one.
- General-purpose: not video-specific. The video-planner skill's need (distinguishing "already covered" from "new" tickets) is the motivating example, but the mechanism should support arbitrary `key: value` metadata from any future consumer, not just this one.
- No MCP tool exists yet for reading/writing this metadata; whichever storage form is chosen, decide whether it needs its own MCP tool (`mcp__docket__*`) or if a consuming skill can read/write it directly as a plain file.

## Open questions to resolve when picking this up

- Frontmatter `metadata` key vs registry file, per above.
- If registry file: where does it live (a consumer's own output dir, or somewhere under Docket's own ticket data directory), and what format (YAML/JSON/markdown)?
- If frontmatter `metadata` key: how do multiple consumers avoid colliding on the same sub-key, and does Docket enforce or just allow namespacing?
- Does a key/entry ever need to apply to a ticket-group without every ticket in the group carrying it individually (partial group coverage)?
