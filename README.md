# docket

A per-repo ticketing system that is a plain-markdown collection a human can read in a text editor and a structured store a Claude Code agent can query over MCP, at the same time.

Docket is developed here and deployed into any number of consumer repositories with one command.
A consumer repository receives ticket data and configuration. It never receives a copy of the tool.

## Install

Once per machine:

```bash
uv tool install git+https://github.com/Sorcerio/Docket
```

That provides two console scripts, `docket` for humans and CI, and `docket-mcp` for agents.

## Deploy into a Repository

```bash
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

## What a Ticket Looks Like

```markdown
---
id: CORE-14
title: Skirmish setup
status: todo
priority: 1
requires: [CORE-9, GEN-3]
---

# Skirmish Setup

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

## Three Ideas Worth Knowing

- **Dependencies are stored one way.** A ticket declares `requires` and nothing else. Reverse edges are derived by scanning, which makes a one-sided edge impossible rather than merely detectable.

- **Status is the truth and the directory follows it.** Only `done` moves a file. Nothing writes one without the other, and `validate` catches a file that was moved by hand.

- **Keys are closed, and adding one is the user's call.** An unregistered key is refused, so a typo cannot spawn an orphan group. An agent that needs a new key is told to ask first, with `AskUserQuestion`, and only then call `add_key`. The gate is a conversation rather than a queue of proposals to triage later, because in practice a human would never propose a key, they would just add it.

## CLI

```bash
docket new --key CORE --title "Skirmish setup" [--requires CORE-9,GEN-3] [--priority 1] [--body TEXT]
docket show CORE-14
docket list [--status todo] [--key CORE] [--priority-max 2]
docket set CORE-14 [--title TEXT] [--priority N] [--requires A,B]
docket status CORE-14 done
docket graph [--id CORE-14 | --key GEN] [--out FILE]
docket key list
docket key add META "campaign and progression" [--rationale TEXT]
docket key remove META
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
| `list_keys()` | The registered keys. |
| `add_key(key, description, rationale)` | Registers a new key, after the agent has asked the user. |
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

# The strategic layer is a distinct area.
META = "campaign and progression"
```

A key added through `add_key` or `docket key add --rationale` writes its rationale as the comment above it, and removing the key takes that comment with it.

The file is read and written with `tomlkit`, so comments, spacing, and key order survive every write the tool makes.

The status vocabulary is deliberately not configurable.

## Validation Rules

Errors: a `requires` entry naming an id that does not exist, a dependency cycle, two tickets sharing an id, an unregistered key, an id that disagrees with its filename prefix, a status that disagrees with its directory, a priority outside the band, a status outside the vocabulary, and a file under a status directory that cannot be read as a ticket.

`validate` reports no warnings of its own. The warning severity exists for `create_ticket`, which downgrades a `requires` entry naming a ticket that does not exist yet, so a batch written out of order is not stranded halfway. `validate` reports that same dangling entry as an error once the batch is done.

## Development

```bash
uv sync
uv run pytest
uv run docket --help
```

The core library holds every rule. The CLI and the MCP server are thin shells over it and contain no logic of their own, which is what keeps the two surfaces from ever disagreeing.
