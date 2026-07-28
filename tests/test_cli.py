"""
CLI Tests

Drive `main` against a real repository on disk, covering dispatch, exit codes, and output separation.
"""

# MARK: Imports

import os
from pathlib import Path
from typing import Iterator

import pytest

from docket.cli import EXIT_INVALID, EXIT_OK, EXIT_USAGE, main, parseIdList
from docket.core.config import Config, loadConfig
from docket.core.errors import InvalidIdError

# MARK: Fixtures


@pytest.fixture
def inRepo(repoDir: Path) -> Iterator[Path]:
    """
    Run inside a throwaway repository, since the CLI finds its configuration by walking up from the working directory.

    repoDir: The repository root fixture.

    Returns the repository root, restoring the previous working directory afterwards.
    """

    previous: str = os.getcwd()
    os.chdir(repoDir)
    try:
        yield repoDir
    finally:
        os.chdir(previous)


# MARK: Functions


def testNoCommandPrintsHelpAndReportsUsage(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Invoking with no subcommand is a usage error, not a silent success.
    """

    assert main([]) == EXIT_USAGE
    assert "COMMAND" in capsys.readouterr().out


def testNewCreatesATicket(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Creation allocates the id, writes the file, and reports where it landed.
    """

    assert main(["new", "--key", "CORE", "--title", "Skirmish setup", "--body", "Goal: one battle."]) == EXIT_OK

    assert "CORE-1" in capsys.readouterr().out
    assert (inRepo / "docs" / "tickets" / "todo" / "CORE-1_skirmishSetup.md").is_file()


def testNewWithADanglingDependencyWarnsOnStderrAndSucceeds(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A batch written out of order still completes, and the warning does not pollute stdout.
    """

    assert main(["new", "--key", "CORE", "--title", "Second", "--requires", "CORE-99"]) == EXIT_OK

    captured = capsys.readouterr()

    assert "CORE-99" in captured.err
    assert "CORE-99" not in captured.out


def testNewUnderAnUnknownKeyFailsAndPointsAtAddKey(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A core error surfaces as a message on stderr and a usage exit code.
    """

    assert main(["new", "--key", "NOPE", "--title", "Orphan"]) == EXIT_USAGE

    assert "add_key" in capsys.readouterr().err


def testShowResolvesBothDependencyDirections(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The raw file stores forward edges only, so `show` has to supply the reverse side and the titles.
    """

    main(["new", "--key", "CORE", "--title", "App shell"])
    main(["new", "--key", "CORE", "--title", "Skirmish setup", "--requires", "CORE-1"])
    capsys.readouterr()

    assert main(["show", "CORE-1"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert "Required by" in out
    assert "Skirmish setup" in out


def testShowDisplaysTheBody(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    `show` prints the prose along with the context, rather than the raw file.
    """

    main(["new", "--key", "CORE", "--title", "App shell", "--body", "Goal: a window that opens."])
    capsys.readouterr()

    main(["show", "CORE-1"])

    out: str = capsys.readouterr().out

    assert "Goal: a window that opens." in out
    assert "---" not in out


def testShowReportsAMissingDependency(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A broken link the reader cannot see is worse than one they can, so it is shown and marked.
    """

    main(["new", "--key", "CORE", "--title", "Dangling", "--requires", "CORE-99"])
    capsys.readouterr()

    main(["show", "CORE-1"])

    assert "missing" in capsys.readouterr().out


def testShowOnAnUnknownIdFails(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Showing a ticket that does not exist is an error.
    """

    assert main(["show", "CORE-99"]) == EXIT_USAGE
    assert "CORE-99" in capsys.readouterr().err


def testListShowsSummariesInPriorityOrder(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Listing orders by priority first, with 0 most urgent.
    """

    main(["new", "--key", "CORE", "--title", "Later", "--priority", "3"])
    main(["new", "--key", "CORE", "--title", "Sooner", "--priority", "0"])
    capsys.readouterr()

    main(["list"])

    out: str = capsys.readouterr().out

    assert out.index("Sooner") < out.index("Later")


def testListFiltersCombine(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Each supplied filter narrows the result.
    """

    main(["new", "--key", "CORE", "--title", "Core work", "--priority", "0"])
    main(["new", "--key", "GEN", "--title", "Gen work", "--priority", "4"])
    capsys.readouterr()

    main(["list", "--key", "CORE"])
    assert "Gen work" not in capsys.readouterr().out

    main(["list", "--priority-max", "0"])
    assert "Gen work" not in capsys.readouterr().out


def testListWithNoMatchesSaysSo(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    An empty result is stated rather than printed as a bare header.
    """

    assert main(["list"]) == EXIT_OK
    assert "No tickets matched." in capsys.readouterr().out


def testSetChangesFieldsWithoutRenamingTheFile(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Retitling must not rename the file, since that would break every prose cross-reference.
    """

    main(["new", "--key", "CORE", "--title", "Original title"])
    capsys.readouterr()

    assert main(["set", "CORE-1", "--title", "Renamed", "--priority", "0"]) == EXIT_OK

    path: Path = inRepo / "docs" / "tickets" / "todo" / "CORE-1_originalTitle.md"

    assert path.is_file()
    assert "title: Renamed" in path.read_text(encoding="utf-8")
    assert "priority: 0" in path.read_text(encoding="utf-8")


def testSetWithNothingToChangeIsAUsageError(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A caller who supplied no field clearly meant to change something, so this is refused rather than silently succeeding.
    """

    main(["new", "--key", "CORE", "--title", "Original"])
    capsys.readouterr()

    assert main(["set", "CORE-1"]) == EXIT_USAGE
    assert "Nothing to change" in capsys.readouterr().err


def testSetCanClearDependencies(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    An empty string clears the list, which is how "no dependencies" is expressed in a shell that can pass one.
    """

    main(["new", "--key", "CORE", "--title", "First"])
    main(["new", "--key", "CORE", "--title", "Second", "--requires", "CORE-1"])
    capsys.readouterr()

    main(["set", "CORE-2", "--requires", ""])

    path: Path = inRepo / "docs" / "tickets" / "todo" / "CORE-2_second.md"

    assert "requires: []" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("sentinel", ["none", "NONE", " None "])
def testSetClearsDependenciesWithTheSentinel(inRepo: Path, capsys: pytest.CaptureFixture[str], sentinel: str) -> None:
    """
    PowerShell discards an empty-string argument before the process sees it, so the sentinel is the form that reaches the parser in every shell. Case and surrounding space do not matter, since a user typing it is not typing an id.

    sentinel: The spelling of the clearing word under test.
    """

    main(["new", "--key", "CORE", "--title", "First"])
    main(["new", "--key", "CORE", "--title", "Second", "--requires", "CORE-1"])
    capsys.readouterr()

    assert main(["set", "CORE-2", "--requires", sentinel]) == EXIT_OK

    path: Path = inRepo / "docs" / "tickets" / "todo" / "CORE-2_second.md"

    assert "requires: []" in path.read_text(encoding="utf-8")


def testSetRejectsTheSentinelMixedWithIds(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Clearing the list and naming a dependency are contradictory, so the pair is refused rather than resolved in one direction and the ticket left unwritten.
    """

    main(["new", "--key", "CORE", "--title", "First"])
    main(["new", "--key", "CORE", "--title", "Second", "--requires", "CORE-1"])
    capsys.readouterr()

    assert main(["set", "CORE-2", "--requires", "CORE-1,none"]) == EXIT_USAGE
    assert "cannot be combined" in capsys.readouterr().err

    path: Path = inRepo / "docs" / "tickets" / "todo" / "CORE-2_second.md"

    assert "requires: [CORE-1]" in path.read_text(encoding="utf-8")


def testStatusMovesTheFile(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The frontmatter and the directory are written together, never one without the other.
    """

    main(["new", "--key", "CORE", "--title", "Skirmish setup"])
    capsys.readouterr()

    assert main(["status", "CORE-1", "done"]) == EXIT_OK

    assert not (inRepo / "docs" / "tickets" / "todo" / "CORE-1_skirmishSetup.md").exists()
    assert (inRepo / "docs" / "tickets" / "done" / "CORE-1_skirmishSetup.md").is_file()


def testStatusRejectsAnUnknownStatusAtTheParser(inRepo: Path) -> None:
    """
    The vocabulary is fixed, so argparse refuses an unrecognized status before the core is reached.
    """

    with pytest.raises(SystemExit) as excInfo:
        main(["status", "CORE-1", "blocked"])

    assert excInfo.value.code == EXIT_USAGE


def testGraphWritesBareMermaidToStdout(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Machine-readable output bypasses `rich`, so a redirect captures exactly the source with no wrapping or escape sequences.
    """

    main(["new", "--key", "CORE", "--title", "App shell"])
    capsys.readouterr()

    assert main(["graph"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert out.startswith("graph TD\n")
    assert "```" not in out
    assert "\x1b" not in out


def testGraphIsNotWrappedForALongTitle(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A long node label must stay on one line, which is exactly what a styled console would have broken.
    """

    main(["new", "--key", "CORE", "--title", "A" * 200])
    capsys.readouterr()

    main(["graph"])

    assert "A" * 200 in capsys.readouterr().out


def testGraphWritesToAFile(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The file receives the same bare source that stdout would have.
    """

    main(["new", "--key", "CORE", "--title", "App shell"])
    capsys.readouterr()

    target: Path = inRepo / "out" / "graph.mmd"

    assert main(["graph", "--out", str(target)]) == EXIT_OK
    assert target.read_text(encoding="utf-8").startswith("graph TD\n")


def testGraphScopesAreMutuallyExclusive(inRepo: Path) -> None:
    """
    Scoping to a ticket and to a key at once is ambiguous, so the parser refuses it.
    """

    with pytest.raises(SystemExit) as excInfo:
        main(["graph", "--id", "CORE-1", "--key", "CORE"])

    assert excInfo.value.code == EXIT_USAGE


def testGraphScopedToAKeyMarksNeighbors(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A key-scoped graph shows where the key ends.
    """

    main(["new", "--key", "CORE", "--title", "App shell"])
    main(["new", "--key", "GEN", "--title", "Battlescape", "--requires", "CORE-1"])
    capsys.readouterr()

    main(["graph", "--key", "GEN"])

    assert "external" in capsys.readouterr().out


def testKeyListShowsTheRegisteredKeys(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Every key a ticket may use is listed with its description.
    """

    assert main(["key", "list"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert "CORE" in out
    assert "tactical-sim core" in out
    assert "META" in out


def testKeyAddRegistersTheKeyWithItsRationale(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Adding a key persists immediately, with the rationale kept as a comment above it.
    """

    assert main(["key", "add", "SIM", "simulation layer", "--rationale", "the tick loop is its own area"]) == EXIT_OK

    config: Config = loadConfig(inRepo / ".docket.toml")

    assert config.registeredKeys["SIM"] == "simulation layer"
    assert "# the tick loop is its own area" in (inRepo / ".docket.toml").read_text(encoding="utf-8")


def testKeyAddRefusesADuplicate(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Re-adding a key would silently rewrite its description, so it fails instead.
    """

    assert main(["key", "add", "CORE", "duplicate"]) == EXIT_USAGE
    assert "CORE" in capsys.readouterr().err


def testKeyRemoveRefusesWhileTicketsUseIt(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Removing a key in use would strand those tickets, so it fails loudly and names them.
    """

    main(["new", "--key", "META", "--title", "Campaign layer"])
    capsys.readouterr()

    assert main(["key", "remove", "META"]) == EXIT_USAGE
    assert "META-1" in capsys.readouterr().err


def testKeyRemoveDropsAnUnusedKey(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    With nothing standing in the way the key and its comment both go.
    """

    assert main(["key", "remove", "META"]) == EXIT_OK
    assert "META" not in (inRepo / ".docket.toml").read_text(encoding="utf-8")


def testValidateExitsNonZeroOnErrors(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    An error changes the exit code, which is what makes the command usable in CI.
    """

    main(["new", "--key", "CORE", "--title", "Dangling", "--requires", "CORE-99"])
    capsys.readouterr()

    assert main(["validate"]) == EXIT_INVALID
    assert "CORE-99" in capsys.readouterr().out


def testValidateOnACleanRepositorySaysNothingIsWrong(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A well-formed repository reports nothing at all.
    """

    assert main(["validate"]) == EXIT_OK
    assert "No findings." in capsys.readouterr().out


def testAMissingConfigurationIsReportedClearly(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Running outside a deployed repository names the recovery command rather than raising a traceback.
    """

    (tmp_path / ".git").mkdir()

    previous: str = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert main(["list"]) == EXIT_USAGE
    finally:
        os.chdir(previous)

    assert "docket deploy" in capsys.readouterr().err


def testCommandsWorkFromASubdirectory(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Configuration is found by walking up, so a command run deep inside the repository still works.
    """

    main(["new", "--key", "CORE", "--title", "App shell"])
    capsys.readouterr()

    previous: str = os.getcwd()
    os.chdir(inRepo / "docs" / "tickets" / "todo")
    try:
        assert main(["list"]) == EXIT_OK
    finally:
        os.chdir(previous)

    assert "App shell" in capsys.readouterr().out


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", []),
        ("CORE-9", ["CORE-9"]),
        ("CORE-9,GEN-3", ["CORE-9", "GEN-3"]),
        (" CORE-9 , GEN-3 ", ["CORE-9", "GEN-3"]),
        ("CORE-9,,GEN-3", ["CORE-9", "GEN-3"]),
        ("none", []),
        ("NONE", []),
        (" None ", []),
    ],
)
def testIdListParsing(value, expected) -> None:
    """
    A comma-separated list tolerates spacing and empty entries, and both an empty string and the sentinel clear rather than meaning absent.
    """

    assert parseIdList(value) == expected


def testIdListParsingRejectsTheSentinelMixedWithIds() -> None:
    """
    The sentinel clears the whole list, so it can never travel alongside an id it would discard.
    """

    with pytest.raises(InvalidIdError):
        parseIdList("CORE-9,none")
