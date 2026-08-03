# docket

Docket provides tickets you can read, version, and control within your existing repository. Your favorite agent can read it too.

Each ticket is plain markdown. Open it in any text editor and it reads like a note. Underneath, the same file is a structured record, and a Claude Code agent queries it over MCP with no parsing hacks and no hidden sync. One file, two readers.

Docket itself lives in this repo alone. Deploy it into any number of consumer repositories with one command, and only the ticket data and configuration travel. Never a copy of the tool.

![Docket demo](docs/demo/docket.gif)

* [docket](#docket)
    * [Install](#install)
    * [Deploy into a Repository](#deploy-into-a-repository)
    * [What a Ticket Looks Like](#what-a-ticket-looks-like)
    * [Three Ideas Worth Knowing](#three-ideas-worth-knowing)
    * [CLI](#cli)
    * [MCP](#mcp)
    * [Configuration](#configuration)
    * [Validation Rules](#validation-rules)
    * [Development](#development)
        * [Working on the Repo](#working-on-the-repo)
        * [Versioning](#versioning)
        * [Local Installation](#local-installation)

---

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
docket new -k CORE -t "Skirmish setup" [-r CORE-9,GEN-3] [-p 1] [-b TEXT]
docket show CORE-14
docket list [-s todo] [-k CORE] [-m 2]
docket set CORE-14 [-t TEXT] [-p N] [-r A,B|none]
docket status CORE-14 done
docket graph [-i CORE-14 | -k GEN] [-o FILE]
docket key list
docket key add META "campaign and progression" [-r TEXT]
docket key remove META
docket validate
docket deploy PATH
docket upgrade PATH
```

Every short flag has a long form: `-k/--key`, `-t/--title`, `-r/--requires`, `-p/--priority`, `-b/--body`, `-s/--status`, `-m/--priority-max`, `-i/--id`, `-o/--out`, `-r/--rationale`, `-V/--version`.

Where an argument takes one of a discrete set, `--help` lists the set. The keys come from your `[keys]` table and the priorities from `0` through `maxPriority`, so the options shown are the ones this repository actually accepts.

> [!IMPORTANT]
> In Windows Powershell, the \` character can be contextually treated as _an escape character_!
> 
> Typing, "Use \`argparse\` instead", will result in an escaped `a` character as `\x07`.
> If providing code blocks in a body, use the MCP surface or simply update your ticket body in your favorite text editor.
>
> The MCP surface, bash, and similar non-Windows terminals _do not_ have this issue.

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

### Working on the Repo

```bash
uv sync
uv run pytest
uv run docket --help
```

The core library holds every rule. The CLI and the MCP server are thin shells over it and contain no logic of their own, which is what keeps the two surfaces from ever disagreeing.

### Versioning

The version is written in exactly one place, `src/docket/__init__.py`. `pyproject.toml` declares no version of its own and reads that one at build time, the CLI reports it through `--version`, and the MCP server advertises it on connect. Nothing else needs editing.

Bump it with the script rather than by hand, which validates the new version and resyncs the lock file for you:

```bash
python scripts/bumpVersion.py patch
python scripts/bumpVersion.py 0.2.0
python scripts/bumpVersion.py minor --dry-run
```

The version argument is either an explicit semantic version or one of `major`, `minor`, or `patch`. Anything that is not three plain numbers is refused, as is a version that does not come after the current one. `--dry-run` reports the change without writing it.

Run `uv sync` after a bump, since the installed metadata carries the old version until you do.

### Local Installation

You can install Docket as a tool from your repo root:

```bash
cd /your/repo/root/
uv tool install --editable --force .
```
