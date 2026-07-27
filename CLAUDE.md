# CLAUDE.md

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
