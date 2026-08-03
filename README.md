# docket

Markdown tickets that live in your repo. You read them in a text editor or CLI. Your agent reads them over MCP.

![Docket demo](https://raw.githubusercontent.com/Sorcerio/Docket/master/docs/demo/docket.gif)

* [docket](#docket)
    * [Start Here](#start-here)
    * [A Ticket](#a-ticket)
    * [CLI](#cli)
    * [MCP](#mcp)
    * [Key Ticket Rules](#key-ticket-rules)
    * [Configuration](#configuration)
    * [Concurrent Access](#concurrent-access)
    * [Validation](#validation)
    * [Docket Runs on Docket](#docket-runs-on-docket)
    * [Development](#development)
    * [License](#license)

---

## Start Here

```bash
uv tool install docket # or: pipx install docket
cd my-project
docket deploy .
```

Then add at least one key to `.docket.toml` (a ticket cannot exist without one):

```bash
docket key add "CORE" "tactical-sim core"
```

Make your first ticket:

```bash
docket new CORE "Skirmish setup"
```

## A Ticket

File: `docs/tickets/todo/CORE-14_skirmishSetup.md`

```markdown
---
id: CORE-14
title: Skirmish setup
status: todo
priority: 1
requires: [CORE-9, GEN-3]
metadata: {}
---

Goal: a screen where the player sets up one battle and plays it.
```

| Field | Notes |
|---|---|
| `id` | `<KEY>-<NUM>`. Must match the filename prefix. |
| `title` | Free text. Changing it does not rename the file. |
| `status` | `todo`, `wip`, or `done`. Fixed vocabulary. |
| `priority` | Integer, `0` most urgent. Ceiling configurable. |
| `requires` | Ids this depends on. Never lists what it blocks. |
| `metadata` | Additional freeform key:value pairs handled first-party. |

Unknown fields are round-tripped untouched. Filenames are frozen at creation so prose cross-references never break.

## CLI

> [!IMPORTANT]
> In Windows PowerShell, the \` character can be treated as an escape character. Typing "Use \`argparse\` instead" produces `\x07`. For code blocks in a body, use the MCP surface or a text editor.

A ticket id is the command:

```bash
docket CORE-14         # show it, dependency context and all
docket CORE-14 status  # bare word, for a pipe
docket CORE-14 done    # todo, wip, or done. The file follows
docket CORE-14 set [-t TEXT] [-p N] [-r A,B|none] [-ra A,B] [-rr A,B]
docket CORE-14 meta [KEY [VALUE]] [-c]
```

Everything else works on the set:

```bash
docket new CORE "Skirmish setup" [-r CORE-9,GEN-3] [-p 1] [-b TEXT]
docket list [-s todo] [-k CORE] [-m 2]
docket graph [-i CORE-14 | -k GEN] [-o FILE]
docket key list | add KEY "desc" [-r TEXT] | remove KEY
docket validate | deploy PATH | upgrade PATH
```

`-r` replaces the dependency list. `-ra` and `-rr` edit the one already there. Both in one call is refused.

Every short flag has a long form (`-k/--key`, `-p/--priority`, `-m/--priority-max`, and so on). `--help` lists your actual keys and priority range.

## MCP

`docket-mcp` is a stdio server. Nine tools, every one returning JSON as text.

| Tool | Purpose |
|---|---|
| `list_tickets(status?, key?, priority_max?)` | Summaries only, never bodies. |
| `read_ticket(id)` | Full body plus both dependency directions. |
| `create_ticket(key, title, body?, requires?, priority?)` | Allocates the id, writes the file. |
| `update_ticket(id, title?, priority?, requires?, requires_add?, requires_remove?)` | Those three fields only. |
| `set_status(id, status)` | Writes frontmatter and moves the file together. |
| `graph(id?, key?)` | Mermaid source. |
| `list_keys()` | The registered keys. |
| `add_key(key, description, rationale)` | After the agent has asked the user. |
| `validate()` | Structured findings. |

## Key Ticket Rules

1. **Dependencies point one way.** A ticket declares `requires` and nothing else. Reverse edges are derived, so a one-sided edge is impossible rather than merely detectable.
2. **Status is the truth, the directory follows.** Only `done` moves a file, and nothing writes one without the other. `validate` catches a file moved by hand.
3. **Keys are a whitelist.** An unregistered key is refused, so a typo cannot spawn an orphan group. A key must be added explicitly before it can be used.

## Configuration

`.docket.toml` at the repo root. Read and written with `tomlkit`, so comments, spacing, and key order survive every write like:

```toml
root = "docs/tickets"
todoDir = "todo"
doneDir = "done"
defaultPriority = 2
maxPriority = 4
lockTimeout = 5.0

[keys]
# Primary arch
CORE = "tactical-sim core"
# The strategic layer is a distinct area.
META = "campaign and progression"
```

A key's rationale becomes the comment above it, and removing the key takes the comment with it. The status vocabulary is deliberately not configurable.

`docket deploy` never rewrites an existing `.docket.toml`. Run `docket upgrade .` later to refresh the template and repair the server entry without touching your config or tickets.

## Concurrent Access

Writes are serialized across processes through `.docket.lock` at the repo root, which `deploy` adds to your `.gitignore`.

- Readers share the lock, writers take it exclusively.
- The whole read-modify-write is held, not just the write. Two processes cannot mint the same id.
- Files are replaced atomically.

Config value `lockTimeout` is how long a process waits before giving up. Hitting it raises an error that changed nothing, so the call is always safe to retry.

## Validation

`docket validate` errors on:

- A `requires` entry naming an id that does not exist, or a dependency cycle
- Two tickets sharing an id, or an unregistered key
- An id disagreeing with its filename prefix, or a status disagreeing with its directory
- A priority outside the band, or a status outside the vocabulary
- A file under a status directory that cannot be read as a ticket

`validate` has no warnings of its own. That severity exists for `create_ticket`, which downgrades a dangling `requires` entry so a batch written out of order is not stranded halfway.

## Docket Runs on Docket

This repo is its own first consumer. Every feature above arrived as a ticket, committed in `docs/tickets/`. `done/` is the history of how the tool got built, `todo/` is what is next.

## Development

```bash
uv sync
uv run pytest
uv run docket --help
uv tool install --editable --force .  # install your working copy
```

The core library holds every rule. The CLI and MCP server are thin shells with no logic of their own, which is what keeps the two surfaces from disagreeing.

The version lives in exactly one place, `src/docket/__init__.py`. Bump it with the script, never by hand, then run `uv sync`:

```bash
python scripts/bumpVersion.py patch
python scripts/bumpVersion.py 0.2.0
python scripts/bumpVersion.py minor --dry-run
```

## License

[GNU GPL v3.0 or later](LICENSE), with an output exception.

Anything Docket writes into your repository is yours under whatever terms you choose: deployed templates, ticket files, generated artifacts. Running Docket against a repository places no license obligation on that repository. The exception reaches only what Docket produces, never Docket's own source.
