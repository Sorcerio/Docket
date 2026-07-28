---
id: FEAT-2
title: Set up and publish to PyPI
status: todo
priority: 2
requires: [FEAT-1]
---

# Set up and publish to PyPI

Get Docket published on PyPI as an installable package.

Depends on FEAT-1 (demo GIF) being done first, since the README should look finished before it's the thing people see on the PyPI project page.

Covers:
- Confirm `docket` is available as a package name on PyPI (fallback name if not, e.g. `python-docket`)
- Add a LICENSE file and pick a license (MIT or Apache-2.0), reflect it in `pyproject.toml`
- Fill in missing `pyproject.toml` metadata: `authors`, `license`, `classifiers`, `keywords`, `[project.urls]` (Homepage/Repository/Issues)
- Verify package data is included correctly in the build, especially non-`.py` files like `src/docket/templates/CLAUDE.md`
- Build with `uv build`, sanity check with `twine check dist/*`
- Dry run: upload to TestPyPI, install in a clean venv, confirm `docket` and `docket-mcp` entry points both work
- Real upload to PyPI via `twine upload dist/*` (needs a PyPI account and API token)
- Tag the release in git matching the published version

Also a prerequisite for making the repo public: needs a LICENSE file before that happens regardless of PyPI timing.
