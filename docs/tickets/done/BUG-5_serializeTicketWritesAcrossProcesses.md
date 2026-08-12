---
id: BUG-5
title: Serialize Ticket Writes Across Processes
status: done
priority: 3
requires: []
metadata: {}
---

# Serialize ticket writes across processes

## Problem

Every mutating path in `docket.core` reads state, changes it in memory, and writes it back, with nothing holding the gap. Two writers overlapping in that gap lose data silently.

The concrete cases:

- `Store.create` calls `loadAll()`, derives an id from `nextId(key, existing.ids())`, and writes. Two overlapping creates under one key allocate the same id. The filename slug comes from the title, so this does not even collide on disk. It produces two files claiming one id, and only `validate` notices, afterwards.
- `Store.update`, `Store.setMetadata`, and `Store.setStatus` each load a ticket, change one field, and write the whole file back. The later write reverts the earlier one.
- `Config.addKey` reads the document, adds the key, and rewrites the file through `tomlkit.dumps`. One of two concurrent additions disappears.
- `Store.write` uses `Path.write_text`, which is not atomic. A reader running `list_tickets` against a concurrent write can parse a truncated file. This one hits readers, not just writers, so guarding only the mutators would not fix it.

## Scope

This is about separate processes. Within one process the server is already safe: `BUG-3` made every MCP handler `async`, which keeps them on the event loop and serialized, and `tests/test_server.py::testEveryHandlerIsAsync` holds that. That fix does nothing here, because an in-process guarantee says nothing about a second process.

The exposed combinations are a `docket` CLI command running while an MCP server is live in the same repository, two MCP servers over one repository, and any script driving `docket.core` alongside either. All three are ordinary, none are exotic.

This predates the `mcp` 2.x migration. Nothing in that migration made it worse. It was deliberately left out of `BUG-3` because cross-process safety is a different problem from the in-process one that migration created.

## Directions, undecided

Two shapes look plausible and they are not exclusive:

- Write atomically. Write to a temporary file in the destination directory and `os.replace` it into place. That is atomic on both POSIX and Windows and it removes the torn-read case for free, without any lock. It does not fix a lost update, since both writers still read the same starting state.
- Lock the repository. A lock file under the tickets directory, held across the read and the write. Fixes the lost updates and the duplicate ids. Costs a cross-platform locking implementation, `msvcrt` on Windows and `fcntl` elsewhere, plus a stale lock story for a process that dies holding one.

Atomic writes are the cheaper half and fix a real case on their own, so they are worth doing whether or not the lock lands.

## Notes

Whatever lands has to work on Windows, since that is where this repository is developed. Any test for it needs real concurrent processes rather than threads, because threads would pass against the current code without proving anything.
