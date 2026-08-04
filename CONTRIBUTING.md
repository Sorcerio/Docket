# Contributing to Docket

Docket runs on Docket.

> [WARNING!]
> Work is tracked as tickets in `docs/tickets/`.
>
> GitHub Issues are used as **intake**.
> Confirmed development becomes a docket ticket!

* [Contributing to Docket](#contributing-to-docket)
    * [Issues and Tickets](#issues-and-tickets)
    * [Getting Set Up](#getting-set-up)
    * [Code Style](#code-style)
    * [Naming Across Interfaces](#naming-across-interfaces)
    * [Versioning](#versioning)
    * [Tests](#tests)
    * [Opening a Pull Request](#opening-a-pull-request)
    * [Releases](#releases)
    * [License](#license)

## Issues and Tickets

Issues are intake, tickets are the tracker.

Open an issue to report a bug or request a feature.
The templates match the `BUG` and `FEAT` ticket keys, so an accepted issue converts to a ticket by copy.
The ticket carries the status, priority, and dependencies, and the issue closes when the ticket does.

To check whether something is planned, read the board instead of opening an issue:

```bash
docket list --status todo
```

Tickets are markdown, so browsing `docs/tickets/` on GitHub works too.

## Getting Set Up

```bash
uv sync
uv run pytest
uv run docket --help
uv tool install --editable --force .  # install your working copy
```

Branch after the ticket you are closing, for example `FEAT-11`.
Two tickets landing together share one branch.

Move status through the CLI, never by hand:

```bash
docket FEAT-11 wip
docket FEAT-11 done
```

`done` rewrites the frontmatter and moves the file in one step.
Moving files between `todo/` and `done/` yourself makes the two disagree and `docket validate` will reject it.
Never rename a ticket file, other tickets reference it by name.

## Code Style

Match the surrounding code exactly:

- **camelCase** for functions, variables, and parameters, never snake_case.
- **`# MARK:` section headers** in every module: `Imports`, `Constants`, `Functions`, `Classes`, in that order.
- **Module docstrings**: title line, blank line, one line description.
- **Function docstrings**: description, blank line, `paramName: description.` lines, then a `Returns ...` sentence. No Sphinx or Google style. Backticks around code references.
- **A short imperative comment above nearly every logical block.** "Stash the changes", not a paragraph.
- **Full type hints everywhere.** `Optional[X]` and `Union[X, Y]` from `typing`, builtin generics like `list[str]`.
- **Private helpers** are prefixed `_name` or `__name`.
- **Class body order**: Properties, Initializer, Python Functions (dunders), Private Functions, Functions.
- **No em dashes anywhere**, in code, comments, docs, or output.
- **Never break a line mid sentence** in prose, docs, or comments. Word wrap handles the width.

Scripts under `scripts/` are standalone and import nothing from `docket`.
Keep them that way.

## Naming Across Interfaces

Two external interfaces deliberately break camelCase, and neither convention leaks into the other.

| Surface | Convention | Examples |
| --- | --- | --- |
| Python source | camelCase | `updateRootBranches`, `defaultPriority` |
| MCP tool names and parameters | snake_case | `list_tickets`, `read_ticket`, `priority_max` |
| Ticket frontmatter keys | lowercase data keys | `id`, `title`, `status`, `priority`, `requires` |
| TOML config keys | camelCase | `todoDir`, `lockTimeout`, `maxPriority` |

snake_case is the MCP ecosystem convention and it is what the model reads, so a camelCase tool name or parameter is a bug.
The mapping lives explicitly in `server.py`.

## Versioning

The version lives in exactly one place, `__version__` in `src/docket/__init__.py`.
`pyproject.toml` reads it through `[tool.hatch.version]`, `cli.py` imports it for `--version`, and `server.py` assigns it onto the MCP server.
Never add a second literal and never edit it by hand:

```bash
python scripts/bumpVersion.py patch
python scripts/bumpVersion.py 1.2.0
python scripts/bumpVersion.py minor --dry-run
```

Run `uv sync` afterwards so `uv.lock` agrees, because CI installs with `--locked`.

One pull request is one bump, no matter how many tickets it closes.
A completed ticket earns at least a minor, or a patch if nothing under `src/` changed.

## Tests

```bash
uv run pytest
```

New behavior needs tests.
The core library holds every rule and the CLI and MCP server are thin shells over it, so test the rule in the core and the wiring at the surface.

CI runs the same command on Ubuntu and Windows.
The suite has no platform specific assertions, so a failure on only one of them is a real finding worth reporting.

## Opening a Pull Request

The template asks for the ticket id, the version bump, and the checks.
Beyond that:

- Target `master`.
- Keep the diff to the ticket. Unrelated cleanups get their own ticket.
- Mark the ticket `done` in the same pull request.
- Both workflows must be green.

Dependabot opens its own pull requests weekly for workflow actions and for dependencies.

## Releases

Releases are automatic and there is no PyPI token anywhere.
Pushing a bare numeric tag on `master` runs the full suite, then publishes to PyPI through GitHub OIDC trusted publishing.

```bash
git tag 1.0.1
git push origin 1.0.1
```

Tags carry no `v` prefix.
The tag must equal `__version__` exactly or the workflow refuses to build, because a version number is spent the moment PyPI accepts it.

The README demo GIF is served to PyPI from `raw.githubusercontent.com` on `master`.
Renaming that branch or moving `docs/demo/docket.gif` permanently breaks the image on every published release, because a published README can never be edited.

## License

Docket is [GNU GPL v3.0 or later](https://github.com/Sorcerio/Docket/blob/master/LICENSE), with an output exception.
Contributions are accepted under those terms.
