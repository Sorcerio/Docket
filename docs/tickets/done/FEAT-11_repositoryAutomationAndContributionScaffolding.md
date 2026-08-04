---
id: FEAT-11
title: Repository automation and contribution scaffolding
status: done
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

## Decisions Made During Implementation

**Tags are bare numeric, not `v` prefixed.** This ticket asked for a `v*` trigger, but `1.0.0` was already tagged and published without a prefix, and a `v*` glob would never have matched it. `release.yml` triggers on `[0-9]*.[0-9]*.[0-9]*` so the tag history stays one convention rather than two. `CONTRIBUTING.md` states this.

**The matrix is Ubuntu and Windows on Python 3.12.** The ticket asked for at least those two operating systems. macOS and 3.13 were considered and dropped as breadth without a specific question behind them.

**The gate is a reusable workflow, not `workflow_run`.** `test.yml` carries a `workflow_call` trigger and `release.yml` calls it as a job that the publish job `needs`. One definition of the suite, and a tag cannot publish without it passing on that exact commit.

**Issues stay open as intake.** The board in `docs/tickets/` remains the tracker. The issue templates are shaped to the `BUG` and `FEAT` keys so an accepted issue converts into a ticket without being rewritten, and an issue closes when its ticket does.

**The release job verifies the tag against `__version__` before building.** A version number is spent the moment PyPI accepts it, so a mismatch has to fail before the upload rather than after.

**This is a patch bump, not a minor.** Nothing under `src/` changed.

**Dependabot was added beyond the ticket's scope.** The action pins written for this ticket were already two majors behind the day they were written, which is the argument for the file rather than against it. `.github/dependabot.yml` watches the `github-actions` and `uv` ecosystems weekly. Actions are pinned to a major tag, so a pull request only appears on a new major rather than on every patch.

## What the Matrix Found

The suite was believed to have no platform specific assertions. It had one, and the Ubuntu leg found it on the first run.

`testAMissingConfigurationIsReportedClearly` asserted `"docket deploy"` appeared in stderr. The message names the recovery command correctly on both platforms, but `rich` falls back to eighty columns when its output is not a terminal, and the message embeds the temporary directory path. That path is longer on Linux than on Windows, so the wrap landed mid phrase and split `docket deploy` across two lines on Ubuntu only.

The assertion was about content and the failure was about layout, so the fix was to make layout deterministic rather than to loosen the assertion. `tests/conftest.py` gained an autouse fixture pinning `COLUMNS` to 400 for every test, which is wider than any message this suite asserts against. That removes the whole class of latent breakage, not just the one instance, since roughly a dozen other assertions look for multi word phrases that a differently sized path could have split the same way.

Nothing under `src/` changed. The message was always correct.
