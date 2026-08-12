---
id: FEAT-9
title: Track Arbitrary Additional Metadata on Tickets/Groups
status: done
priority: 1
requires: []
metadata:
  key: value
---

# Track arbitrary additional metadata on tickets/groups

## Context

Comes out of designing a `video-planner` skill (see `.claude/skills/video-planner/SKILL.md`) that drafts Dev Log video scripts from Docket ticket data and git history. That skill needs to know which tickets or ticket-groups have already been used in a past video, so it does not re-suggest them and so it can suggest "what's new since the last video."

That video-tracking need is just one consumer. The underlying gap is that Docket tickets have no place to attach arbitrary, tool-defined metadata without touching the core frontmatter schema. This ticket generalizes the mechanism to a `metadata: {key: value}` style store, of which "which video covered this ticket" is one example use, not the whole scope.

This ticket is scoped to the metadata/tracking mechanism only, not the video-planner skill itself (that is separate work, deliberately decoupled so this can land on its own PR/version bump).

## Decision made

Went with a new ticket frontmatter key, `metadata: {key: value}`. Reasoning: `Ticket.extra` in `ticket.py` already round-trips any unrecognized frontmatter field verbatim, including nested dicts, so a `metadata:` block would have survived writes even before this ticket. Promoting it to a first-class field bought typed validation (must be a mapping, keys must be strings) and a dedicated write tool, at very low cost, rather than standing up a separate registry file, format, and location decision.

Write semantics: merge one key at a time rather than full-map replace, so two consumers (e.g. `video-planner` and something else) writing different keys to the same ticket never clobber each other. Passing a `null`/`None` value removes the key instead of storing a null placeholder.

Version bump: shipped as **minor**, not major. `bump-version`'s own table lists "a changed ticket frontmatter schema" under major, which was raised and reconsidered mid-implementation, but the call stood: existing tickets are unaffected (`metadata` defaults to `{}` when absent, same as `requires` defaulting to `[]`), and no existing tool call or field is removed or renamed.

## What shipped

- `Ticket.metadata: dict[str, Any]` (`src/docket/core/ticket.py`), parsed via a new `readDict` helper in `src/docket/core/fields.py`. Absent/null reads as `{}`. A non-mapping value or a non-string key is a `TicketParseError`, same tier as a malformed `requires`.
- `metadata` is in `CANONICAL_FIELDS`, ordered right after `requires`, and always serialized explicitly (`metadata: {}` on a ticket with nothing in it, block style otherwise) rather than omitted.
- `Store.setMetadata(ticketId, key, value)` in `src/docket/core/store.py`, merges one key, `None` deletes it.
- MCP tool `set_metadata(id, key, value)` in `src/docket/server.py`. `read_ticket`'s payload carries `metadata` as its own field, separate from `extra` (unrecognized fields). `SERVER_INSTRUCTIONS` documents it and the namespacing convention (e.g. `video` as a key, not `covered`).
- CLI: `docket meta get <id>` and `docket meta set <id> <key> <value>` (with `-c/--clear` to remove a key), added to `src/docket/cli.py` alongside the other subcommands, same shorthand-flag conventions as `new`/`set`/`list`.
- `docs/tickets/CLAUDE.md` frontmatter table and tool table updated.
- Tests added across `test_ticket.py`, `test_store.py`, `test_server.py`, `test_cli.py`.

Not done, deliberately out of scope per the original ticket: the `video-planner` skill itself does not yet call `set_metadata`. That is separate follow-up work.
