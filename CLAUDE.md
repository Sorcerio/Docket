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

## Naming across interfaces

camelCase is the repo-wide Python convention above. Two external interfaces do NOT follow it, on purpose:

- **MCP tool names and their parameters are snake_case** (`list_tickets`, `read_ticket`, `set_status`, `propose_key`, `priority_max`). That is the MCP ecosystem convention and it is what the model sees. Never expose a camelCase tool name or param.
- Ticket frontmatter keys are lowercase data keys (`id`, `title`, `status`, `priority`, `requires`).

TOML config keys stay camelCase, matching the repo style.

Keep the snake_case-to-camelCase mapping explicit in `server.py`. Neither convention leaks into the other.
