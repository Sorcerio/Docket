# CLAUDE.md

## Other CLAUDE.md Files in This Repo

The `CLAUDE.md` file in `src\docket\templates\CLAUDE.md` is *not* for you.
It is a template provided when Docket is deployed.

## Code Style

Match existing style exactly:

- camelCase for functions, variables, params (`updateRootBranches`, `doTheThing`). NOT snake_case. Repo-wide, intentional, keep it.
- `# MARK: Imports` / `# MARK: Constants` / `# MARK: Functions` / `# MARK: Classes` section headers in every module.
- Module docstring: title line, blank line, one-line description.
- Function docstrings: description, blank line, then `paramName: description.` lines (no Sphinx/Google style), then `Returns ...` sentence. Backticks around code refs.
- Inline comment above nearly every logical block, short imperative ("# Stash the changes").
- Full type hints everywhere. `Optional[X]` / `Union[X, Y]` from typing, builtin generics (`list[str]`, `dict[str, Any]`).
- Private helpers: `_name` or `__name` prefix.
- Class body order: Properties, Initializer, Python Functions (dunders), Private Functions, Functions.
- No em dashes anywhere, in code, comments, docs, or output.
- Never break a line mid-sentence in prose/docs/comments. One sentence stays on one line, word wrap handles width.

## Utility Scripts

Scripts under `scripts/` are standalone and import nothing from `docket`, so they stay standalone.

Use `python scripts/<script_name>.py <params>` to execute them as `uv` might be able to be used in this context.

## Versioning

The version lives in exactly one place, `__version__` in `src/docket/__init__.py`. `pyproject.toml` reads it from there through `[tool.hatch.version]` and declares no version of its own, `cli.py` imports it for `--version`, and `server.py` assigns it onto the lowlevel MCP server. Never add a second literal.

Bump it with `python scripts/bumpVersion.py <#.#.#|major|minor|patch>`, never by hand. Completing a ticket earns at least a minor bump.

One pull request is one bump, no matter how many tickets it closes. Two tickets landing together is still a single minor.

## Naming across interfaces

camelCase is the repo-wide Python convention above. Two external interfaces do NOT follow it, on purpose:

- **MCP tool names and their parameters are snake_case** (`list_tickets`, `read_ticket`, `set_status`, `propose_key`, `priority_max`). That is the MCP ecosystem convention and it is what the model sees. Never expose a camelCase tool name or param.
- Ticket frontmatter keys are lowercase data keys (`id`, `title`, `status`, `priority`, `requires`).

TOML config keys stay camelCase, matching the repo style.

Keep the snake_case-to-camelCase mapping explicit in `server.py`. Neither convention leaks into the other.

## Commits

- Plain messages only. Do NOT add a `Co-Authored-By` or `Generated with` trailer unless explicitly asked.
- Short subject line expressing what was done as a short imperative.
- Subject line only. No body, no additional text.
- Never commit unprompted. Verify (compile and test), report ready for review, then wait for review.
- When presenting code for review, use the `commit-message` skill to draft the commit subject alongside it.
