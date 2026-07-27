# docket

A per-repo ticketing system that is a plain-markdown collection a human can read in a text editor and a structured store a Claude Code agent can query over MCP, at the same time.

Docket is developed here and deployed into any number of consumer repositories with one command.
A consumer repository receives ticket data and configuration. It never receives a copy of the tool.

## Install

Once per machine:

```
uv tool install git+https://github.com/Sorcerio/Docket
```

That provides two console scripts, `docket` for humans and CI, and `docket-mcp` for agents.

## Deploy into a repository

```
cd my-project
docket deploy .
```

That creates the ticket directories, writes agent instructions beside them, writes `.docket.toml` at the repository root, and merges a server entry into `.mcp.json`.
It is idempotent, and it never rewrites an existing `.docket.toml`, because that file holds the key registry.

Then add your keys, since a ticket cannot be created under a key that does not exist:

```toml
[keys]
CORE = "tactical-sim core"
GEN  = "map generation"
```

Run `docket upgrade .` later to refresh the deployed template and repair the server entry without touching your configuration or your tickets.

## What a ticket looks like

```markdown
---
id: CORE-14
title: Skirmish setup
status: todo
priority: 1
requires: [CORE-9, GEN-3]
---

# Skirmish setup

Goal: a screen where the player sets up one battle and plays it.
```

| Field | Notes |
|---|---|
| `id` | `<KEY>-<NUM>`, allocated by scanning existing ids. Must match the filename prefix. |
| `title` | Free text. May change without renaming the file. |
| `status` | `todo`, `wip`, or `done`. Fixed vocabulary. |
| `priority` | Integer, `0` most urgent. Ceiling is configurable. |
| `requires` | Ids this ticket depends on. Never lists what it blocks. |

Any other field is round-tripped untouched, so a repository can extend the schema without a tool change.

The filename is `CORE-14_skirmishSetup.md`, frozen at creation. Retitling does not rename it, because renaming would break every prose cross-reference pointing at it.

## Three ideas worth knowing

**Dependencies are stored one way.** A ticket declares `requires` and nothing else. Reverse edges are derived by scanning, which makes a one-sided edge impossible rather than merely detectable.

**Status is the truth and the directory follows it.** Only `done` moves a file. Nothing writes one without the other, and `validate` catches a file that was moved by hand.

**Keys are closed, with a soft gate.** An unregistered key is refused, so a typo cannot spawn an orphan group. An agent that needs a new key calls `propose_key`, which writes it into configuration where it shows up in the git diff. Tickets can use a proposed key immediately, so a batch in flight is never stranded, and `validate` warns until a human runs `docket key approve`.

## CLI

```
docket new --key CORE --title "Skirmish setup" [--requires CORE-9,GEN-3] [--priority 1] [--body TEXT]
docket show CORE-14
docket list [--status todo] [--key CORE] [--priority-max 2]
docket set CORE-14 [--title TEXT] [--priority N] [--requires A,B]
docket status CORE-14 done
docket graph [--id CORE-14 | --key GEN] [--out FILE]
docket key list [--proposed]
docket key approve META
docket key reject META
docket validate
docket deploy PATH
docket upgrade PATH
```

`show` prints the body with resolved dependency context, not the raw file. Use `cat` for that.

`graph` writes bare mermaid source to stdout, so it pipes and redirects cleanly. GitHub and most editors render it natively.

`validate` exits `1` when it finds errors and `0` when it finds only warnings, which is what makes it usable in a pre-commit hook or in CI.

## MCP

`docket-mcp` is a stdio server exposing nine tools.

| Tool | Purpose |
|---|---|
| `list_tickets(status?, key?, priority_max?)` | Summaries only, never bodies. |
| `read_ticket(id)` | Full body plus both dependency directions resolved. |
| `create_ticket(key, title, body?, requires?, priority?)` | Allocates the id and writes the file. |
| `update_ticket(id, title?, priority?, requires?)` | Changes only these three fields. |
| `set_status(id, status)` | Updates frontmatter and moves the file together. |
| `graph(id?, key?)` | Returns mermaid source. |
| `list_keys()` | Registered and proposed keys. |
| `propose_key(key, description, rationale)` | Opens a new key for immediate use. |
| `validate()` | Structured findings. |

Every tool returns JSON as text.

## Configuration

`.docket.toml` at the repository root.

```toml
root = "docs/tickets"
todoDir = "todo"
doneDir = "done"
defaultPriority = 2
maxPriority = 4

[keys]
CORE = "tactical-sim core"

[keys.proposed]
META = { description = "campaign and progression", rationale = "the strategic layer is a distinct area", by = "agent", at = "2026-07-27" }
```

The file is read and written with `tomlkit`, so comments, spacing, and key order survive every write the tool makes.

The status vocabulary is deliberately not configurable.

## Validation rules

Errors: a `requires` entry naming an id that does not exist, a dependency cycle, two tickets sharing an id, an unregistered key, an id that disagrees with its filename prefix, a status that disagrees with its directory, a priority outside the band, a status outside the vocabulary, and a file under a status directory that cannot be read as a ticket.

Warnings: a key that is proposed but not approved, and a proposed key no ticket uses.

## Development

```
uv sync
uv run pytest
uv run docket --help
```

The core library holds every rule. The CLI and the MCP server are thin shells over it and contain no logic of their own, which is what keeps the two surfaces from ever disagreeing.

`docs/scopeOfWork.md` records the design decisions, the reasoning behind each, and the alternatives that were rejected. Read it before changing behavior.
