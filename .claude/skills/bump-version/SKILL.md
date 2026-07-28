---
name: bump-version
description: Bump this repo's version through scripts/bumpVersion.py, choosing the right part and confirming before writing. Use when the user asks to bump/raise/set the version, cut a release, or says "/bump-version", and when a ticket has just been finished.
---

Raise the version using `scripts/bumpVersion.py`. Never edit a version literal by hand.

The version lives in exactly one place, `__version__` in `src/docket/__init__.py`. Everything else derives from it: `pyproject.toml` reads it at build time through `[tool.hatch.version]`, `cli.py` imports it for `--version`, and `server.py` assigns it onto the lowlevel MCP server. If you find yourself editing a second version literal, stop, because it should not exist.

## Steps

1. Read the current version from `src/docket/__init__.py`.
2. Decide the part to bump using the table below. If the change is ambiguous, ask the user rather than guessing upward.
3. Run the dry run and show the user its output:
   ```bash
   python scripts/bumpVersion.py <#.#.#|major|minor|patch> --dry-run
   ```
4. Ask before the real run. Never bump unprompted, the same way `commit-message` never commits unprompted.
5. Run it for real once the user agrees. The script resyncs `uv.lock` itself.
6. Tell the user to run `uv sync`, since the installed metadata carries the old version until they do.

## Choosing the part

| Part | When |
|---|---|
| `minor` | The default. Any finished ticket, whatever it turned out to involve. |
| `patch` | Work no ticket covers. A stray docs fix, a lint pass, a test-only change. |
| `major` | A break in a contract someone else depends on. A renamed or removed CLI subcommand, MCP tool, or MCP parameter, a changed ticket frontmatter schema, a changed `docket.toml` key, or a change to how ticket files are laid out on disk. |

Completing a ticket earns a minor. Reach for `major` only when the table above actually calls for it, and say why when you do.

One pull request is one bump, no matter how many tickets it closes. Two tickets landing together is still a single minor, so bump once for the branch rather than once per ticket.

## What the script refuses

It exits 2 without writing when the version is malformed or does not move forward. Both are usually a typo, so read the message back to the user rather than working around it.

- Not three plain numbers: `0.2`, `v0.2.0`, `0.2.0-rc1`, `01.2.0`.
- Not after the current one: the current version itself, or anything lower.

## Never

- Never hand-edit `__version__`, `pyproject.toml`, or `uv.lock` to change a version.
- Never add `: str` back to the `__version__` assignment. Hatchling's default regex does not allow an annotation, and the comment above the line says so.
- Never add a second version literal anywhere in the repo.
