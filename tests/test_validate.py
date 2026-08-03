"""
Validation Tests

One fixture per rule, plus the clean case and the severity split.
"""

# MARK: Imports

from pathlib import Path

import pytest

from docket.core.config import Config
from docket.core.store import Store
from docket.core.validate import (
    RULE_CYCLE,
    RULE_DUPLICATE_ID,
    RULE_FILENAME_MISMATCH,
    RULE_MISSING_DEPENDENCY,
    RULE_PRIORITY_RANGE,
    RULE_STATUS_DIRECTORY,
    RULE_UNKNOWN_KEY,
    RULE_UNKNOWN_STATUS,
    RULE_UNREADABLE,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    Finding,
    ValidationReport,
    validate,
)

# MARK: Fixtures


@pytest.fixture
def store(config: Config) -> Store:
    """
    Build a store over a throwaway repository.

    config: The configuration fixture.

    Returns the store.
    """

    return Store(config)


# MARK: Functions


def writeRaw(config: Config, directory: str, filename: str, text: str) -> Path:
    """
    Drop a file straight into a status directory, bypassing the store.

    config: The configuration naming the ticket root.
    directory: The status directory name.
    filename: The filename to write.
    text: The file contents.

    Returns the written path.
    """

    path: Path = config.rootPath / directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")

    return path


def makeText(ticketId: str, title: str = "T", status: str = "todo", priority: int = 2, requires: str = "[]") -> str:
    """
    Build minimal ticket file text.

    ticketId: The id to record.
    title: The title to record.
    status: The status to record.
    priority: The priority to record.
    requires: The dependency list, written as YAML flow style.

    Returns the file text.
    """

    return f"---\nid: {ticketId}\ntitle: {title}\nstatus: {status}\npriority: {priority}\nrequires: {requires}\n---\n\n# {title}\n"


def rules(report: ValidationReport) -> list[str]:
    """
    List the rules a report fired, in order.

    report: The report to read.

    Returns the rule identifiers.
    """

    return [finding.rule for finding in report.findings]


def testACleanRepositoryHasNoErrors(store: Store, config: Config) -> None:
    """
    A well-formed set produces nothing at all, not merely no errors.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))
    writeRaw(config, "done", "CORE-2_b.md", makeText("CORE-2", status="done", requires="[CORE-1]"))

    report: ValidationReport = validate(store)

    assert report.isValid
    assert report.findings == []


def testAnEmptyRepositoryIsValid(store: Store) -> None:
    """
    A freshly deployed repository with no tickets is valid.
    """

    assert validate(store).isValid


def testAMissingDependencyIsAnError(store: Store, config: Config) -> None:
    """
    A `requires` entry naming an id that does not exist is an error, even though it is only a warning at creation time.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", requires="[CORE-99]"))

    report: ValidationReport = validate(store)

    assert not report.isValid
    assert RULE_MISSING_DEPENDENCY in rules(report)
    assert "CORE-99" in report.errors[0].message
    assert report.errors[0].ticketId == "CORE-1"


def testACycleIsAnError(store: Store, config: Config) -> None:
    """
    A dependency cycle is reported once for the whole component, naming its members.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", requires="[CORE-2]"))
    writeRaw(config, "todo", "CORE-2_b.md", makeText("CORE-2", requires="[CORE-1]"))

    report: ValidationReport = validate(store)

    cycles = [finding for finding in report.findings if finding.rule == RULE_CYCLE]

    assert len(cycles) == 1
    assert "CORE-1" in cycles[0].message
    assert "CORE-2" in cycles[0].message


def testASelfDependencyReadsPlainly(store: Store, config: Config) -> None:
    """
    A ticket requiring itself is stated directly rather than as a one-member cycle.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", requires="[CORE-1]"))

    cycles = [finding for finding in validate(store).findings if finding.rule == RULE_CYCLE]

    assert cycles[0].message == "Ticket 'CORE-1' requires itself."


def testADuplicateIdIsAnError(store: Store, config: Config) -> None:
    """
    Two branches minting under one key collide, and the finding names both files.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", title="First"))
    writeRaw(config, "todo", "CORE-1_b.md", makeText("CORE-1", title="Second"))

    report: ValidationReport = validate(store)

    assert RULE_DUPLICATE_ID in rules(report)
    assert "CORE-1_a.md" in report.errors[0].message
    assert "CORE-1_b.md" in report.errors[0].message


def testAnUnknownKeyIsAnError(store: Store, config: Config) -> None:
    """
    A key that is neither registered nor proposed is an error, which is what stops a typo spawning an orphan group.
    """

    writeRaw(config, "todo", "NOPE-1_a.md", makeText("NOPE-1"))

    report: ValidationReport = validate(store)

    assert RULE_UNKNOWN_KEY in rules(report)


def testAFilenameMismatchIsAnError(store: Store, config: Config) -> None:
    """
    The id must match the filename prefix, since the prefix is what makes the filename unique.
    """

    writeRaw(config, "todo", "CORE-2_a.md", makeText("CORE-1"))

    report: ValidationReport = validate(store)

    assert RULE_FILENAME_MISMATCH in rules(report)


def testAStaleSlugIsNotAMismatch(store: Store, config: Config) -> None:
    """
    Filenames are frozen at creation, so a retitled ticket has a stale slug by design and that is not a finding.
    """

    writeRaw(config, "todo", "CORE-1_completelyDifferentSlug.md", makeText("CORE-1", title="A new title"))

    assert validate(store).isValid


def testAStatusDirectoryMismatchIsAnError(store: Store, config: Config) -> None:
    """
    The status is the truth and the directory is a projection, so a file moved by hand is caught.
    """

    writeRaw(config, "done", "CORE-1_a.md", makeText("CORE-1", status="todo"))

    report: ValidationReport = validate(store)

    assert RULE_STATUS_DIRECTORY in rules(report)
    assert "docket CORE-1 todo" in report.errors[0].message


def testWipBelongsInTheTodoDirectory(store: Store, config: Config) -> None:
    """
    Only `done` moves a file, so `wip` sitting in the todo directory is correct.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", status="wip"))

    assert validate(store).isValid


def testWipInTheDoneDirectoryIsAnError(store: Store, config: Config) -> None:
    """
    The other half of the same rule, since only `done` belongs in the done directory.
    """

    writeRaw(config, "done", "CORE-1_a.md", makeText("CORE-1", status="wip"))

    assert RULE_STATUS_DIRECTORY in rules(validate(store))


def testAnOutOfRangePriorityIsAnError(store: Store, config: Config) -> None:
    """
    The ceiling is configurable and enforced here, and a negative priority is caught too.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", priority=99))
    writeRaw(config, "todo", "CORE-2_b.md", makeText("CORE-2", priority=-1))

    report: ValidationReport = validate(store)

    assert [finding.rule for finding in report.errors] == [RULE_PRIORITY_RANGE, RULE_PRIORITY_RANGE]


def testTheCeilingItselfIsAllowed(store: Store, config: Config) -> None:
    """
    The band is inclusive at both ends.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", priority=0))
    writeRaw(config, "todo", "CORE-2_b.md", makeText("CORE-2", priority=config.maxPriority))

    assert validate(store).isValid


def testAnUnknownStatusIsAnError(store: Store, config: Config) -> None:
    """
    The vocabulary is fixed, so a hand-edited status outside it is caught.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", status="blocked"))

    report: ValidationReport = validate(store)

    assert RULE_UNKNOWN_STATUS in rules(report)

    # It does not also fire the directory rule, since an unrecognized status has no directory to agree with.
    assert RULE_STATUS_DIRECTORY not in rules(report)


def testAnUnreadableFileIsAnError(store: Store, config: Config) -> None:
    """
    A file under a status directory that is not a ticket is reported rather than silently skipped.
    """

    writeRaw(config, "todo", "broken.md", "no frontmatter here\n")

    report: ValidationReport = validate(store)

    assert RULE_UNREADABLE in rules(report)
    assert report.errors[0].path.name == "broken.md"


def testOneBrokenFileDoesNotHideTheRest(store: Store, config: Config) -> None:
    """
    Loading collects failures rather than raising, so every other rule still runs.
    """

    writeRaw(config, "todo", "broken.md", "no frontmatter here\n")
    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", requires="[CORE-99]"))

    firedRules: list[str] = rules(validate(store))

    assert RULE_UNREADABLE in firedRules
    assert RULE_MISSING_DEPENDENCY in firedRules


def testWarningsAloneStillCountAsValid() -> None:
    """
    A pre-commit hook must not fail on a warning, so only errors invalidate.

    No rule emits a warning today, so the split is asserted against a constructed report rather than a fixture.
    """

    report: ValidationReport = ValidationReport(findings=[Finding(severity=SEVERITY_WARNING, rule="somethingSoft", message="soft.")])

    assert report.warnings
    assert report.errors == []
    assert report.isValid


def testTheReportSerializesForTheMcpSurface(store: Store, config: Config) -> None:
    """
    Findings cross the MCP boundary as plain data, so the serialized shape is fixed.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", requires="[CORE-99]"))

    payload = validate(store).toDict()

    assert payload["valid"] is False
    assert payload["errorCount"] == 1
    assert payload["warningCount"] == 0

    finding = payload["findings"][0]
    assert set(finding) == {"severity", "rule", "message", "id", "path"}
    assert finding["severity"] == SEVERITY_ERROR
    assert finding["id"] == "CORE-1"


def testAnAlreadyLoadedSetIsReused(store: Store, config: Config) -> None:
    """
    Validation may be handed a set that is already in memory, so a caller does not pay to load it twice.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))

    loaded = store.loadAll()

    assert validate(store, loaded).isValid


def testFindingsAreOrderedByTicket(store: Store, config: Config) -> None:
    """
    Per-ticket rules walk in sorted order, so repeated runs produce the same output for a diff or a CI log.
    """

    writeRaw(config, "todo", "CORE-10_c.md", makeText("CORE-10", requires="[NOPE-1]"))
    writeRaw(config, "todo", "CORE-2_b.md", makeText("CORE-2", requires="[NOPE-1]"))

    report: ValidationReport = validate(store)

    assert [finding.ticketId for finding in report.errors] == ["CORE-2", "CORE-10"]
