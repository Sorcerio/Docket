## Ticket

Closes:
<!-- The ticket ids this change closes, for example FEAT-11, or BUG-3 and BUG-4. Write "none" for a change that has no ticket. -->

## What changed

<!-- What the change does, and why it is the right shape. The ticket carries the background, so this does not need to repeat it. -->

## Version

- [ ] The version was bumped with `python scripts/bumpVersion.py <#.#.#|major|minor|patch>`
- [ ] `uv sync` was run afterwards, so `uv.lock` agrees with `pyproject.toml`

One pull request is one bump, no matter how many tickets it closes.
Two tickets landing together is still a single bump.
A completed ticket earns at least a minor, unless nothing under `src/` changed.

## Checks

- [ ] `uv run pytest` passes locally
- [ ] New behavior has tests covering it
- [ ] Ticket status was moved with `docket <ID> done` rather than by moving the file
