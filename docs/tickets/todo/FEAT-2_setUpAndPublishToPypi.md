---
id: FEAT-2
title: Set up and publish to PyPI
status: todo
priority: 3
requires: [BUG-1, BUG-2, FEAT-4, FEAT-5, FEAT-7, BUG-3, BUG-4, FEAT-10, BUG-5]
metadata: {}
---

# Set up and publish to PyPI

Get Docket published on PyPI as an installable package.

Depends on FEAT-1 (demo GIF) being done first, since the README should look finished before it's the thing people see on the PyPI project page.

Covers:
- Update the `README.md` to convey that _this very repo_ uses Docket to manage its own development
- Confirm `docket` is available as a package name on PyPI (fallback name if not, e.g. `python-docket`)
- Add a LICENSE file and pick a license (MIT or Apache-2.0), reflect it in `pyproject.toml`
- Fill in missing `pyproject.toml` metadata: `authors`, `license`, `classifiers`, `keywords`, `[project.urls]` (Homepage/Repository/Issues)
- Verify package data is included correctly in the build, especially non-`.py` files like `src/docket/templates/CLAUDE.md`
- Build with `uv build`, sanity check with `twine check dist/*`
- Dry run: upload to TestPyPI, install in a clean venv, confirm `docket` and `docket-mcp` entry points both work
- Real upload to PyPI via `twine upload dist/*` (needs a PyPI account and API token)
- Tag the release in git matching the published version

Also a prerequisite for making the repo public: needs a LICENSE file before that happens regardless of PyPI timing.
