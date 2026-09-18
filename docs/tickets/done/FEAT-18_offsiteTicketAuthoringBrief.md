---
id: FEAT-18
title: Offsite Ticket Authoring Brief
status: done
priority: 1
requires: []
metadata: {}
---

# Offsite Ticket Authoring Brief

## What this is

One document, written to be pasted into a chat system that has no connection to Docket, that teaches it to write Docket tickets as markdown files by hand.

The chat answers with a set of ticket files. The user saves them into a Docket repository's `todo` directory, registers the keys the document told it to propose, and runs `validate`. That is the whole pipeline. No importer, no carried format, no parser.

The point is to let the thinking part of starting a backlog happen wherever the user already is, rather than requiring them to be inside a Docket instance before a single ticket can exist.

## Why it is a document and not a command

Two heavier designs were assessed first and both were rejected.

A CSV or bundle format with a `docket import` command means a second format specification, a second parser, temporary reference resolution, a topological sort, a bulk write holding one lock, and a key registration path that routes around the rule saying a key needs the user's agreement. All of that to move text into files.

Handing the file to an on-site agent with MCP and letting it transcribe removes the parser but makes the transcription probabilistic, and it still needs the same authoring document. It is a reasonable fallback for a user who prefers to work conversationally, and nothing here prevents it, but it is not worth building toward.

Writing the files directly is the lightest path that keeps every existing guarantee, because of the next section.

## `validate` is already the importer

Every rule a bulk import would have needed exists in `docket.core.validate` today.

Unreadable files, duplicate ids, missing dependencies, dependency cycles, unregistered keys, a filename disagreeing with its id, a status disagreeing with its directory, a priority outside the configured band, an unknown status, and title case as a warning.

That is not an approximation of an import validator, it is one. Any programmatic import would have meant writing a second rule set that then has to agree with this one forever. Dropping files in and running `validate` reuses the rule set that already exists, so the acceptance test for a handoff is a command the user already runs and a command CI already runs.

The authoring burden is correspondingly small. `requires` and `metadata` both read as empty when absent, so a valid ticket needs only `id`, `title`, `status`, and `priority`. `_checkFilename` deliberately checks only the `<ID>_` prefix and not the slug, because slugs are expected to go stale, so any readable filename with the right prefix passes.

## The constraint that makes it safe

Id allocation is the only real risk, and it is removed by scoping what the external chat is allowed to author.

The chat cannot know the highest number already used under a key, so against an existing instance it will guess. Usually that fails loudly, since the same id under a different title produces two files and a `duplicateId` error naming both. The quiet case is narrow but real, because an id and a title that slugify identically produce the same filename, so saving the file overwrites the existing ticket and validation sees nothing wrong, there being only one internally consistent file left.

So the document instructs the chat to propose new keys only. A brand new key always starts at 1, which makes collision structurally impossible rather than merely unlikely. Appending to an existing key stays possible, but only when the user pastes in the ids already in use, and the document says that plainly rather than letting the chat infer it.

This also puts key registration in the right hands. Keys must be registered before the files validate, so the output carries a short header naming each proposed key with its description and the literal `docket key add` lines to run. The user types them, which satisfies the rule that a key is never added without the user's agreement, by construction rather than by trust.

## It is a sibling of `docs/tickets/CLAUDE.md`, not a copy

That file is most of the needed content already, and it is the natural starting point. It cannot be handed over unchanged, because the parts that differ are inverted rather than merely absent.

It says not to create, move, rename, or delete ticket files. This document's central instruction is to create them by hand. It says to let the tool convert titles to title case, where the external chat has no tool and has to case them itself. Its two tables name MCP tools the reader cannot call, and its keys section tells the reader to ask the user through `AskUserQuestion`.

So the new document states in its first line that it is for preparing tickets outside a Docket instance, for a reader with no tools. Two documents in one repository giving opposite instructions about hand-editing ticket files is a hazard worth one explicit sentence in each, especially since `docs/tickets/CLAUDE.md` is what `deploy` ships into consumer repositories.

## Output shape

A zip is a convenience, not the specification. Most chat systems cannot reliably emit a binary, and the ones that cannot are much of the audience this exists for. A zip is also opaque to review at the exact moment the user should be reading what they are about to commit.

So the primary instruction is one fenced block per ticket with its filename on the line above, which works in any chat window and stays reviewable. Environments that can package the result may offer a zip as well.

## Acceptance

- A chat with no Docket access, given only this document and a project description, produces files that pass `validate` with no errors once the named keys are registered.
- Title case warnings are acceptable output and the document says how to clear them, through `update_ticket` or by the on-site agent.
- The document never tells the reader to call a tool, and never assumes it can see a repository.

## Decisions taken

- The brief lives at `src/docket/docs/writingTicketsOffsite.md.jinja`, inside the package so the CLI can print it, and deliberately not under `templates/`, which stays reserved for `FEAT-6`.
- `deploy` does not ship it into consumer repositories. A document whose rules invert the ones beside the tickets should not sit beside the tickets.
- `docket docs handoff` prints it, through `output.raw` so a redirect receives exactly the document.
- It is a rendered template rather than a flat file, which retired the constraint this ticket originally proposed. Rather than restricting the reader to new keys, the brief now names the registered keys, what each covers, and the first free number under each. Collision stops being a rule the reader has to follow and becomes a fact it is handed, so appending to an existing key is the ordinary path and proposing a new one is the exception it argues for.
- Nothing is shared with `docs/tickets/CLAUDE.md`. The two disagree on purpose, so a shared source would have to encode the disagreement.

## Notes

Not documentation only in the end. Rendering the brief against the repository needed `docket.core.handoff`, and sharing the package data reader with `deploy` needed `docket.core.resources`.

The residual cost against every alternative is that hand-written frontmatter skips the title casing `create_ticket` performs, so the first `validate` after a handoff usually reports title case warnings to clear. That is self-healing and cheaper than either rejected design.
