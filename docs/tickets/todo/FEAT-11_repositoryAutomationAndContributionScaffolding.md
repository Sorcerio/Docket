---
id: FEAT-11
title: Repository automation and contribution scaffolding
status: todo
priority: 3
requires: [FEAT-2]
metadata: {}
---

# Repository automation and contribution scaffolding

Now that the repository is public and `ticket-docket` is on PyPI, set up the GitHub-side scaffolding that a public repository is expected to have, and take the release token out of a human's hands.

## Trusted Publishing

Replace the manual API token upload with GitHub's OIDC trusted publishing, so no long-lived PyPI credential exists anywhere.

- Register the publisher on PyPI under the `ticket-docket` project, pointing at this repository, the release workflow filename, and a `pypi` environment
- Add `.github/workflows/release.yml`, triggered on a `v*` tag, building with `uv build` and publishing with `uv publish` and no token
- Grant the job `id-token: write`, which is what makes the OIDC exchange work
- Delete the account-scoped PyPI token once a tagged release has published through the workflow

The release sequence today is documented in FEAT-2. This turns steps 2 through 7 of it into pushing a tag.

## Continuous Integration

- Add `.github/workflows/test.yml` running `uv run pytest` on push and pull request
- The suite is Windows-developed but has no platform-specific assertions, so run the matrix on at least Ubuntu and Windows to find out whether that holds
- Gate the release workflow on the test workflow passing

## Contribution Scaffolding

- `.github/pull_request_template.md`, prompting for the ticket id the change closes and a note on whether the version was bumped, since this repository's rule is one bump per pull request no matter how many tickets land
- `.github/ISSUE_TEMPLATE/bug_report.md` and `feature_request.md`, shaped to match the `BUG` and `FEAT` keys so an issue converts into a ticket without rewriting it
- `CONTRIBUTING.md` covering the camelCase convention, the `MARK` section headers, the single-source version rule, and the fact that tickets live in `docs/tickets/` rather than in GitHub Issues
- Decide whether GitHub Issues stays open at all, given the board is the real tracker. A closed tracker pointing at the board is defensible, and so is treating Issues as the intake that becomes a ticket. Pick one and say so in `CONTRIBUTING.md`

## Notes

The demo GIF is served to PyPI from `raw.githubusercontent.com` on the `master` branch. Renaming that branch or moving `docs/demo/docket.gif` breaks the image on every already-published release, permanently, because a published release's README can never be edited.
