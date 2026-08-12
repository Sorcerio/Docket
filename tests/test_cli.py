"""
CLI Tests

Drive `main` against a real repository on disk, covering dispatch, exit codes, and output separation.
"""

# MARK: Imports

import os
from pathlib import Path
from typing import Iterator, Optional

import pytest

from docket.cli import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    TICKET_COMMAND,
    TOKEN_ID,
    TOKEN_KEY,
    TOKEN_PRIORITY,
    TOKEN_STATUS,
    classifyToken,
    describeKeys,
    describePriorities,
    main,
    parseIdList,
    resolveGraphScope,
    resolveListFilters,
    rewriteIdFirst,
    tryDiscoverConfig,
)
from docket.core.config import Config, loadConfig
from docket.core.errors import ConflictingArgumentsError, InvalidArgumentError, InvalidIdError

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

    The key and the title are positional, since both are required and a required flag is a flag that should have been an argument.
    """

    assert main(["new", "CORE", "Skirmish Setup", "--body", "Goal: one battle."]) == EXIT_OK

    assert "CORE-1" in capsys.readouterr().out
    assert (inRepo / "docs" / "tickets" / "todo" / "CORE-1_skirmishSetup.md").is_file()


def testNewWithADanglingDependencyWarnsOnStderrAndSucceeds(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A batch written out of order still completes, and the warning does not pollute stdout.
    """

    assert main(["new", "CORE", "Second", "--requires", "CORE-99"]) == EXIT_OK

    captured = capsys.readouterr()

    assert "CORE-99" in captured.err
    assert "CORE-99" not in captured.out


def testNewUnderAnUnknownKeyFailsAndPointsAtAddKey(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A core error surfaces as a message on stderr and a usage exit code.
    """

    assert main(["new", "NOPE", "Orphan"]) == EXIT_USAGE

    assert "add_key" in capsys.readouterr().err


def testABareIdShowsTheTicket(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Naming a ticket and nothing else means showing it, since that is what naming one almost always means.
    """

    main(["new", "CORE", "App Shell"])
    capsys.readouterr()

    assert main(["CORE-1"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert "App Shell" in out
    assert "Requires" in out


def testShowIsTheSpelledOutFormOfABareId(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The default action has a name, so it can be documented and typed rather than only implied.
    """

    main(["new", "CORE", "App Shell"])
    capsys.readouterr()

    main(["CORE-1"])
    bare: str = capsys.readouterr().out

    assert main(["CORE-1", "show"]) == EXIT_OK
    assert capsys.readouterr().out == bare


def testShowResolvesBothDependencyDirections(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The raw file stores forward edges only, so `show` has to supply the reverse side and the titles.
    """

    main(["new", "CORE", "App Shell"])
    main(["new", "CORE", "Skirmish Setup", "--requires", "CORE-1"])
    capsys.readouterr()

    assert main(["CORE-1", "show"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert "Required by" in out
    assert "Skirmish Setup" in out


def testShowDisplaysTheBody(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    `show` prints the prose along with the context, rather than the raw file.
    """

    main(["new", "CORE", "App Shell", "--body", "Goal: a window that opens."])
    capsys.readouterr()

    main(["CORE-1", "show"])

    out: str = capsys.readouterr().out

    assert "Goal: a window that opens." in out
    assert "---" not in out


def testShowReportsAMissingDependency(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A broken link the reader cannot see is worse than one they can, so it is shown and marked.
    """

    main(["new", "CORE", "Dangling", "--requires", "CORE-99"])
    capsys.readouterr()

    main(["CORE-1", "show"])

    assert "missing" in capsys.readouterr().out


def testShowOnAnUnknownIdFails(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Showing a ticket that does not exist is an error.
    """

    assert main(["CORE-99"]) == EXIT_USAGE
    assert "CORE-99" in capsys.readouterr().err


def testListShowsSummariesInPriorityOrder(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Listing orders by priority first, with 0 most urgent.
    """

    main(["new", "CORE", "Later", "--priority", "3"])
    main(["new", "CORE", "Sooner", "--priority", "0"])
    capsys.readouterr()

    main(["list"])

    out: str = capsys.readouterr().out

    assert out.index("Sooner") < out.index("Later")


def testListFiltersCombine(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Each supplied filter narrows the result.
    """

    main(["new", "CORE", "Core Work", "--priority", "0"])
    main(["new", "GEN", "Gen Work", "--priority", "4"])
    capsys.readouterr()

    main(["list", "--key", "CORE"])
    assert "Gen Work" not in capsys.readouterr().out

    main(["list", "--priority-max", "0"])
    assert "Gen Work" not in capsys.readouterr().out


def testListFiltersFromBareTokens(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A token says which filter it is by its own shape, so the three can be typed in any order with no flags between them.
    """

    main(["new", "CORE", "Core Work", "--priority", "0"])
    main(["new", "GEN", "Gen Work", "--priority", "4"])
    capsys.readouterr()

    assert main(["list", "todo", "CORE", "0"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert "Core Work" in out
    assert "Gen Work" not in out

    # Order carries no meaning, since each token is classified on its own.
    assert main(["list", "0", "todo", "CORE"]) == EXIT_OK
    assert capsys.readouterr().out == out


def testListTakesTokensAndFlagsTogether(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The flags remain the explicit form of the same three filters, so mixing the two spellings is fine as long as they name different filters.
    """

    main(["new", "CORE", "Core Work", "--priority", "0"])
    main(["new", "GEN", "Gen Work", "--priority", "4"])
    capsys.readouterr()

    assert main(["list", "CORE", "--status", "todo"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert "Core Work" in out
    assert "Gen Work" not in out


def testListRefusesATokenItCannotRead(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A token matching none of the classes is named rather than ignored, since ignoring it would answer a question nobody asked.
    """

    assert main(["list", "nonsense"]) == EXIT_USAGE

    err: str = capsys.readouterr().err

    assert "nonsense" in err
    assert "priority number" in err


def testListNamesTheCommandForATicketId(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    An id is a whole other command rather than a filter, so the error names that command instead of calling the token unreadable.
    """

    assert main(["list", "CORE-1"]) == EXIT_USAGE
    assert "docket CORE-1" in capsys.readouterr().err


@pytest.mark.parametrize("command", [["list", "todo", "wip"], ["list", "todo", "--status", "wip"], ["list", "CORE", "GEN"], ["list", "1", "2"]])
def testListRefusesTheSameFilterTwice(inRepo: Path, capsys: pytest.CaptureFixture[str], command: list[str]) -> None:
    """
    Naming one filter twice is refused rather than quietly resolved in whichever direction the code happens to read, whichever pair of spellings was used.

    command: The invocation under test.
    """

    assert main(command) == EXIT_USAGE
    assert "twice" in capsys.readouterr().err


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

    main(["new", "CORE", "Original Title"])
    capsys.readouterr()

    assert main(["CORE-1", "set", "--title", "Renamed", "--priority", "0"]) == EXIT_OK

    path: Path = inRepo / "docs" / "tickets" / "todo" / "CORE-1_originalTitle.md"

    assert path.is_file()
    assert "title: Renamed" in path.read_text(encoding="utf-8")
    assert "priority: 0" in path.read_text(encoding="utf-8")


def testSetWithNothingToChangeIsAUsageError(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A caller who supplied no field clearly meant to change something, so this is refused rather than silently succeeding.
    """

    main(["new", "CORE", "Original"])
    capsys.readouterr()

    assert main(["CORE-1", "set"]) == EXIT_USAGE
    assert "Nothing to change" in capsys.readouterr().err


def testSetCanClearDependencies(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    An empty string clears the list, which is how "no dependencies" is expressed in a shell that can pass one.
    """

    main(["new", "CORE", "First"])
    main(["new", "CORE", "Second", "--requires", "CORE-1"])
    capsys.readouterr()

    main(["CORE-2", "set", "--requires", ""])

    path: Path = inRepo / "docs" / "tickets" / "todo" / "CORE-2_second.md"

    assert "requires: []" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("sentinel", ["none", "NONE", " None "])
def testSetClearsDependenciesWithTheSentinel(inRepo: Path, capsys: pytest.CaptureFixture[str], sentinel: str) -> None:
    """
    PowerShell discards an empty-string argument before the process sees it, so the sentinel is the form that reaches the parser in every shell. Case and surrounding space do not matter, since a user typing it is not typing an id.

    sentinel: The spelling of the clearing word under test.
    """

    main(["new", "CORE", "First"])
    main(["new", "CORE", "Second", "--requires", "CORE-1"])
    capsys.readouterr()

    assert main(["CORE-2", "set", "--requires", sentinel]) == EXIT_OK

    path: Path = inRepo / "docs" / "tickets" / "todo" / "CORE-2_second.md"

    assert "requires: []" in path.read_text(encoding="utf-8")


def testSetRejectsTheSentinelMixedWithIds(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Clearing the list and naming a dependency are contradictory, so the pair is refused rather than resolved in one direction and the ticket left unwritten.
    """

    main(["new", "CORE", "First"])
    main(["new", "CORE", "Second", "--requires", "CORE-1"])
    capsys.readouterr()

    assert main(["CORE-2", "set", "--requires", "CORE-1,none"]) == EXIT_USAGE
    assert "cannot be combined" in capsys.readouterr().err

    path: Path = inRepo / "docs" / "tickets" / "todo" / "CORE-2_second.md"

    assert "requires: [CORE-1]" in path.read_text(encoding="utf-8")


def testSetAddsAndRemovesDependenciesInPlace(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Editing the list in place is what spares a caller from retyping a long one to change a single entry.
    """

    main(["new", "CORE", "First"])
    main(["new", "CORE", "Second"])
    main(["new", "CORE", "Third", "--requires", "CORE-1"])
    capsys.readouterr()

    path: Path = inRepo / "docs" / "tickets" / "todo" / "CORE-3_third.md"

    assert main(["CORE-3", "set", "--requires-add", "CORE-2"]) == EXIT_OK
    assert "requires: [CORE-1, CORE-2]" in path.read_text(encoding="utf-8")

    assert main(["CORE-3", "set", "--requires-remove", "CORE-1"]) == EXIT_OK
    assert "requires: [CORE-2]" in path.read_text(encoding="utf-8")


def testSetRefusesReplacingAndEditingAtOnce(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Replacing the list and editing it in one call is contradictory, so the ticket is left as it was.
    """

    main(["new", "CORE", "First"])
    main(["new", "CORE", "Second", "--requires", "CORE-1"])
    capsys.readouterr()

    assert main(["CORE-2", "set", "--requires", "CORE-1", "--requires-add", "CORE-1"]) == EXIT_USAGE
    assert "cannot be combined" in capsys.readouterr().err

    path: Path = inRepo / "docs" / "tickets" / "todo" / "CORE-2_second.md"

    assert "requires: [CORE-1]" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("flag", ["--requires-add", "--requires-remove"])
def testSetRefusesAnEmptyEditList(inRepo: Path, capsys: pytest.CaptureFixture[str], flag: str) -> None:
    """
    An edit naming nothing to do is a usage error, since clearing the list is what `--requires` is for.

    flag: The editing flag under test.
    """

    main(["new", "CORE", "First"])
    capsys.readouterr()

    assert main(["CORE-1", "set", flag, "none"]) == EXIT_USAGE
    assert "needs at least one id" in capsys.readouterr().err


@pytest.mark.parametrize("command", [["new", "CORE", ""], ["CORE-1", "set", "--title", "   "]])
def testEmptyTitleIsRefused(inRepo: Path, capsys: pytest.CaptureFixture[str], command: list[str]) -> None:
    """
    A POSIX shell passes an empty string through, so an empty title would otherwise be written and frozen into the filename as `untitled`.

    command: The invocation under test.
    """

    main(["new", "CORE", "Original"])
    capsys.readouterr()

    assert main(command) == EXIT_USAGE
    assert "title cannot be empty" in capsys.readouterr().err

    # Nothing was written, so the only ticket is still the one created above.
    assert len(list((inRepo / "docs" / "tickets" / "todo").glob("*.md"))) == 1


def testEmptyKeyDescriptionIsRefused(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The description is the whole of what a key registry tells a later reader, so registering one without it is refused.
    """

    assert main(["key", "add", "NEW", ""]) == EXIT_USAGE
    assert "description cannot be empty" in capsys.readouterr().err

    assert main(["key", "list"]) == EXIT_OK
    assert "NEW" not in capsys.readouterr().out


def testGraphRefusesAnUnwritableOutPath(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    An empty path used to resolve to the working directory and reach `write_text` as a directory, surfacing as a traceback rather than as a message.
    """

    main(["new", "CORE", "Skirmish Setup"])
    capsys.readouterr()

    assert main(["graph", "--out", ""]) == EXIT_USAGE
    assert "cannot be empty" in capsys.readouterr().err

    assert main(["graph", "--out", str(inRepo)]) == EXIT_USAGE
    assert "is a directory" in capsys.readouterr().err


def testGraphWritesToANestedOutPath(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A destination under directories that do not exist yet is created on the way, which the check must not have broken.
    """

    main(["new", "CORE", "Skirmish Setup"])
    capsys.readouterr()

    target: Path = inRepo / "build" / "graphs" / "docket.mmd"

    assert main(["graph", "--out", str(target)]) == EXIT_OK
    assert "graph TD" in target.read_text(encoding="utf-8")


def testMetaSetsAKeyAndReadsTheMapBack(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A set key is visible in the map, the round trip an agent or a human actually uses.
    """

    main(["new", "CORE", "Skirmish Setup"])
    capsys.readouterr()

    assert main(["CORE-1", "meta", "video", "2026-01-devlog"]) == EXIT_OK
    capsys.readouterr()

    assert main(["CORE-1", "meta"]) == EXIT_OK
    out: str = capsys.readouterr().out

    assert "video" in out
    assert "2026-01-devlog" in out


def testMetaWithAKeyPrintsOnlyTheValue(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A key on its own reads that one entry raw, for the same reason `status` does, so a shell can take the answer as readily as a person.
    """

    main(["new", "CORE", "Skirmish Setup"])
    main(["CORE-1", "meta", "video", "2026-01-devlog"])
    capsys.readouterr()

    assert main(["CORE-1", "meta", "video"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert out == "2026-01-devlog\n"
    assert "\x1b" not in out


def testMetaReadingAnUnsetKeyFails(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    An absent key prints nothing on stdout, since a caller reading a value must not receive an explanation where the value would have been.
    """

    main(["new", "CORE", "Skirmish Setup"])
    capsys.readouterr()

    assert main(["CORE-1", "meta", "video"]) == EXIT_USAGE

    captured = capsys.readouterr()

    assert captured.out == ""
    assert "video" in captured.err


def testMetaWithNoMetadataSaysSo(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A ticket with an empty metadata map is stated rather than printed as a bare table.
    """

    main(["new", "CORE", "Skirmish Setup"])
    capsys.readouterr()

    assert main(["CORE-1", "meta"]) == EXIT_OK
    assert "No metadata." in capsys.readouterr().out


def testMetaClearsAKeyWithTheFlag(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    `-c/--clear` removes the key rather than requiring a sentinel value.
    """

    main(["new", "CORE", "Skirmish Setup"])
    main(["CORE-1", "meta", "video", "2026-01-devlog"])
    capsys.readouterr()

    assert main(["CORE-1", "meta", "video", "-c"]) == EXIT_OK
    capsys.readouterr()

    main(["CORE-1", "meta"])
    assert "No metadata." in capsys.readouterr().out


def testMetaRejectsAValueTogetherWithClear(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Passing both a value and --clear is contradictory, so it is refused rather than resolved silently.
    """

    main(["new", "CORE", "Skirmish Setup"])
    capsys.readouterr()

    assert main(["CORE-1", "meta", "video", "x", "--clear"]) == EXIT_USAGE
    assert "Cannot pass a value" in capsys.readouterr().err


def testMetaClearWithNoKeyIsAUsageError(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Clearing has to know what to clear, and the whole map is not it.
    """

    main(["new", "CORE", "Skirmish Setup"])
    main(["CORE-1", "meta", "video", "2026-01-devlog"])
    capsys.readouterr()

    assert main(["CORE-1", "meta", "--clear"]) == EXIT_USAGE
    assert "Name the metadata key" in capsys.readouterr().err

    # The map is untouched, which is the whole point of refusing.
    main(["CORE-1", "meta"])
    assert "video" in capsys.readouterr().out


def testMetaOnAnUnknownIdFails(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Setting metadata on a ticket that does not exist is an error.
    """

    assert main(["CORE-99", "meta", "video", "x"]) == EXIT_USAGE
    assert "CORE-99" in capsys.readouterr().err


def testAStatusWordMovesTheFile(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The frontmatter and the directory are written together, never one without the other. The status word is the whole command rather than a value handed to one.
    """

    main(["new", "CORE", "Skirmish Setup"])
    capsys.readouterr()

    assert main(["CORE-1", "done"]) == EXIT_OK

    assert not (inRepo / "docs" / "tickets" / "todo" / "CORE-1_skirmishSetup.md").exists()
    assert (inRepo / "docs" / "tickets" / "done" / "CORE-1_skirmishSetup.md").is_file()


def testEveryStatusIsItsOwnCommand(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The vocabulary is fixed, so each word in it reaches the same write.
    """

    main(["new", "CORE", "Skirmish Setup"])
    capsys.readouterr()

    for status in ("wip", "done", "todo"):
        assert main(["CORE-1", status]) == EXIT_OK
        capsys.readouterr()

        main(["CORE-1", "status"])
        assert capsys.readouterr().out == f"{status}\n"


def testStatusPrintsOnlyTheStatus(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Reading a status yields the bare word and nothing else, so a shell can read the answer as easily as a person can.
    """

    main(["new", "CORE", "Skirmish Setup"])
    main(["CORE-1", "wip"])
    capsys.readouterr()

    assert main(["CORE-1", "status"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert out == "wip\n"
    assert "\x1b" not in out


def testReadyPrintsOnlyTheAnswer(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Readiness reads bare for the same reason a status does, so a shell can take the answer as readily as a person.
    """

    main(["new", "CORE", "Skirmish Setup"])
    capsys.readouterr()

    assert main(["CORE-1", "ready"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert out == "true\n"
    assert "\x1b" not in out


def testReadyIsFalseWhileADependencyIsOpen(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    An open prerequisite is the case the check exists for, and closing it has to flip the answer.
    """

    main(["new", "CORE", "Skirmish Setup"])
    main(["new", "CORE", "Deployment", "--requires", "CORE-1"])
    capsys.readouterr()

    assert main(["CORE-2", "ready"]) == EXIT_OK
    assert capsys.readouterr().out == "false\n"

    main(["CORE-1", "done"])
    capsys.readouterr()

    assert main(["CORE-2", "ready"]) == EXIT_OK
    assert capsys.readouterr().out == "true\n"


def testReadyExitsZeroWhenNotReady(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The exit code reports whether the question could be answered, not what the answer was, so a false is a successful read rather than a failure.
    """

    main(["new", "CORE", "Skirmish Setup"])
    main(["new", "CORE", "Deployment", "--requires", "CORE-1"])
    capsys.readouterr()

    assert main(["CORE-2", "ready"]) == EXIT_OK


def testReadyOnAnUnknownTicketFails(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A ticket that does not exist has no readiness to report, so it fails the way naming an unknown ticket always does rather than answering false.
    """

    assert main(["CORE-99", "ready"]) == EXIT_USAGE
    assert "CORE-99" in capsys.readouterr().err


def testListReadyKeepsOnlyUnblockedTickets(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The filter answers "what can I pick up right now", so a blocked ticket and a finished one both fall out of it.
    """

    main(["new", "CORE", "Skirmish Setup"])
    main(["new", "CORE", "Deployment", "--requires", "CORE-1"])
    main(["new", "CORE", "Shipped"])
    main(["CORE-3", "done"])
    capsys.readouterr()

    assert main(["list", "--ready"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert "Skirmish Setup" in out
    assert "Deployment" not in out
    assert "Shipped" not in out


def testListReadyComposesWithTheOtherFilters(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Readiness narrows what the other filters already selected rather than replacing them.
    """

    main(["new", "CORE", "Core Work"])
    main(["new", "GEN", "Gen Work"])
    capsys.readouterr()

    assert main(["list", "CORE", "--ready"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert "Core Work" in out
    assert "Gen Work" not in out


def testListReadyJudgesAgainstTheWholeSet(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A dependency filtered out of the listing still counts, since readiness is a fact about the set rather than about what was displayed.
    """

    main(["new", "GEN", "Groundwork"])
    main(["new", "CORE", "Skirmish Setup", "--requires", "GEN-1"])
    capsys.readouterr()

    assert main(["list", "CORE", "--ready"]) == EXIT_OK
    assert "No tickets matched" in capsys.readouterr().out


def testAnUnknownStatusIsRejectedAtTheParser(inRepo: Path) -> None:
    """
    The vocabulary is fixed, so argparse refuses an unrecognized word before the core is reached.
    """

    with pytest.raises(SystemExit) as excInfo:
        main(["CORE-1", "blocked"])

    assert excInfo.value.code == EXIT_USAGE


@pytest.mark.parametrize("command", [["show", "CORE-1"], ["set", "CORE-1", "-p", "1"], ["status", "CORE-1", "done"], ["meta", "get", "CORE-1"]])
def testTheOldFlatCommandsAreGone(inRepo: Path, command: list[str]) -> None:
    """
    Every ticket command moved under the id, so the flat spelling is refused rather than kept alive as a second way to say the same thing.

    command: The retired invocation under test.
    """

    with pytest.raises(SystemExit) as excInfo:
        main(command)

    assert excInfo.value.code == EXIT_USAGE


def testGraphWritesBareMermaidToStdout(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Machine-readable output bypasses `rich`, so a redirect captures exactly the source with no wrapping or escape sequences.
    """

    main(["new", "CORE", "App Shell"])
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

    main(["new", "CORE", "A" * 200])
    capsys.readouterr()

    main(["graph"])

    assert "A" * 200 in capsys.readouterr().out


def testGraphWritesToAFile(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The file receives the same bare source that stdout would have.
    """

    main(["new", "CORE", "App Shell"])
    capsys.readouterr()

    target: Path = inRepo / "out" / "graph.mmd"

    assert main(["graph", "--out", str(target)]) == EXIT_OK
    assert target.read_text(encoding="utf-8").startswith("graph TD\n")


def testGraphScopeFlagsAreMutuallyExclusive(inRepo: Path) -> None:
    """
    Scoping to a ticket and to a key at once is ambiguous, so the parser refuses it.
    """

    with pytest.raises(SystemExit) as excInfo:
        main(["graph", "--id", "CORE-1", "--key", "CORE"])

    assert excInfo.value.code == EXIT_USAGE


def testGraphScopesFromABareToken(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    An id and a key are told apart by shape, so one positional covers both scopes the flags spell out.
    """

    main(["new", "CORE", "App Shell"])
    main(["new", "GEN", "Battlescape", "--requires", "CORE-1"])
    capsys.readouterr()

    assert main(["graph", "GEN"]) == EXIT_OK
    assert "external" in capsys.readouterr().out

    assert main(["graph", "CORE-1"]) == EXIT_OK
    assert "CORE_1" in capsys.readouterr().out


def testGraphRefusesAScopeItCannotRead(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A token that is neither an id nor a key would otherwise scope to nothing, which reads as an answer rather than a mistake.
    """

    assert main(["graph", "nonsense"]) == EXIT_USAGE
    assert "nonsense" in capsys.readouterr().err


def testGraphRefusesATokenBesideAFlag(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Argparse can make the two flags exclude each other but cannot reach across to a positional, so the pairing is refused here instead.
    """

    assert main(["graph", "CORE", "--key", "GEN"]) == EXIT_USAGE
    assert "already scopes the graph" in capsys.readouterr().err


def testGraphScopedToAKeyMarksNeighbors(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A key-scoped graph shows where the key ends.
    """

    main(["new", "CORE", "App Shell"])
    main(["new", "GEN", "Battlescape", "--requires", "CORE-1"])
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

    main(["new", "META", "Campaign layer"])
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

    main(["new", "CORE", "Dangling", "--requires", "CORE-99"])
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

    main(["new", "CORE", "App Shell"])
    capsys.readouterr()

    previous: str = os.getcwd()
    os.chdir(inRepo / "docs" / "tickets" / "todo")
    try:
        assert main(["list"]) == EXIT_OK
    finally:
        os.chdir(previous)

    assert "App Shell" in capsys.readouterr().out


def testKeyDescriptionNamesTheRegistry(config: Config) -> None:
    """
    The registry is per-repository, so the help text lists what this one actually accepts.
    """

    assert describeKeys(config) == "One of: CORE, GEN, HEAD, META."


def testKeyDescriptionWithoutAConfiguration() -> None:
    """
    With no configuration there is no registry to read, so the description stays general rather than guessing.
    """

    assert describeKeys(None) == "Must be registered."


def testKeyDescriptionWithAnEmptyRegistry(tmp_path: Path) -> None:
    """
    A registry with nothing in it is the state right after a deploy, so it is named rather than printed as an empty list.
    """

    configPath: Path = tmp_path / ".docket.toml"
    configPath.write_text("root = \"docs/tickets\"\n", encoding="utf-8", newline="\n")

    assert "docket key add" in describeKeys(loadConfig(configPath))


def testPriorityDescriptionNamesTheBand(config: Config) -> None:
    """
    The band runs from 0 through the configured maxPriority, which is 4 in the sample configuration.
    """

    assert describePriorities(config) == "One of: 0, 1, 2, 3, 4. 0 is most urgent."


def testPriorityDescriptionWithoutAConfiguration() -> None:
    """
    Without a configuration the band is unknown, so only the direction is stated.
    """

    assert describePriorities(None) == "0 is most urgent."


def testHelpNamesTheRegisteredKeys(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Help for an argument taking a key lists the keys, so the options are visible without a second command.
    """

    with pytest.raises(SystemExit):
        main(["new", "--help"])

    out: str = capsys.readouterr().out

    assert "CORE" in out
    assert "META" in out


def testTopLevelHelpNamesTheIdBranch(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The branch is registered under a placeholder rather than hidden, so argparse lists it like any other command and the id form needs no separate documentation.
    """

    with pytest.raises(SystemExit):
        main(["--help"])

    assert TICKET_COMMAND in capsys.readouterr().out


def testIdBranchHelpNamesWhatWasTyped(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The id is added before the branch's subcommands, so argparse derives a usage line describing the invocation the user actually made rather than the placeholder behind it.
    """

    with pytest.raises(SystemExit) as excInfo:
        main(["CORE-1", "--help"])

    out: str = capsys.readouterr().out

    assert excInfo.value.code == EXIT_OK
    assert "docket [-h] ID COMMAND" in out
    assert TICKET_COMMAND not in out


def testHelpWorksOutsideARepository(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Help is built before any command runs, so a missing configuration must degrade the text rather than stop the parser.
    """

    (tmp_path / ".git").mkdir()

    previous: str = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert tryDiscoverConfig() is None

        with pytest.raises(SystemExit) as excInfo:
            main(["new", "--help"])
    finally:
        os.chdir(previous)

    assert excInfo.value.code == EXIT_OK
    assert "Must be registered." in capsys.readouterr().out


def testShorthandFlagsDriveNewAndSet(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Every short flag reaches the same handler its long form does.
    """

    assert main(["new", "CORE", "Skirmish Setup", "-p", "1", "-b", "Goal: one battle."]) == EXIT_OK
    assert main(["new", "GEN", "Battlescape", "-r", "CORE-1", "-p", "0"]) == EXIT_OK
    assert main(["GEN-1", "set", "-t", "Renamed", "-p", "3", "-r", "none"]) == EXIT_OK

    # The multi-character shorthands are exact option strings, so neither is read as `-r` carrying a value.
    assert main(["GEN-1", "set", "-ra", "CORE-1"]) == EXIT_OK
    assert main(["GEN-1", "set", "-rr", "CORE-1"]) == EXIT_OK

    capsys.readouterr()

    main(["GEN-1"])
    out: str = capsys.readouterr().out

    assert "Renamed" in out
    assert "priority 3" in out


def testShorthandFlagsDriveListAndGraph(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The read commands take the same shorthands, including the file destination.
    """

    main(["new", "CORE", "App Shell", "-p", "0"])
    main(["new", "GEN", "Battlescape", "-p", "4"])
    capsys.readouterr()

    assert main(["list", "-s", "todo", "-k", "CORE", "-m", "0"]) == EXIT_OK

    out: str = capsys.readouterr().out

    assert "App Shell" in out
    assert "Battlescape" not in out

    target: Path = inRepo / "out" / "graph.mmd"

    assert main(["graph", "-k", "CORE", "-o", str(target)]) == EXIT_OK
    assert target.read_text(encoding="utf-8").startswith("graph TD\n")


def testListRejectsAnUnregisteredKey(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    An unregistered key cannot match a ticket, so it is named rather than reported as an empty result.
    """

    assert main(["list", "-k", "NOPE"]) == EXIT_USAGE
    assert "not registered" in capsys.readouterr().err

    # The bare token reaches the same check, since classification only decides which filter a token is, never whether the key exists.
    assert main(["list", "NOPE"]) == EXIT_USAGE
    assert "not registered" in capsys.readouterr().err


def testGraphRejectsAnUnregisteredKey(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    Scoping the graph to a key that does not exist would render an empty graph, which reads as an answer rather than a mistake.
    """

    assert main(["graph", "-k", "NOPE"]) == EXIT_USAGE
    assert "not registered" in capsys.readouterr().err

    assert main(["graph", "NOPE"]) == EXIT_USAGE
    assert "not registered" in capsys.readouterr().err


def testListAcceptsAPriorityMaxAboveTheBand(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A ceiling above the band still describes the right set, so it is answered rather than refused.
    """

    main(["new", "CORE", "App Shell"])
    capsys.readouterr()

    assert main(["list", "-m", "99"]) == EXIT_OK
    assert "App Shell" in capsys.readouterr().out


def testVersionShorthand(inRepo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """
    The version is reachable by its short flag as well as its long one.
    """

    with pytest.raises(SystemExit):
        main(["-V"])

    assert "docket" in capsys.readouterr().out


@pytest.mark.parametrize(
    "token,expected",
    [
        ("CORE-14", TOKEN_ID),
        ("C1-2", TOKEN_ID),
        ("CORE", TOKEN_KEY),
        ("C1", TOKEN_KEY),
        ("todo", TOKEN_STATUS),
        ("wip", TOKEN_STATUS),
        ("done", TOKEN_STATUS),
        ("0", TOKEN_PRIORITY),
        ("99", TOKEN_PRIORITY),
        ("list", None),
        ("core", None),
        ("TODO", TOKEN_KEY),
        ("CORE-0", None),
        ("-1", None),
        ("1.5", None),
        ("", None),
    ],
)
def testTokenClassification(token: str, expected: Optional[str]) -> None:
    """
    Every class is decided by the token's own shape, and the four cannot overlap, which is what makes a bare filter unambiguous.

    An uppercase word is a key even when it spells a status, since a status is lowercase by definition and a key is uppercase by definition.

    token: The token under test.
    expected: The class it should fall into, or `None` for none of them.
    """

    assert classifyToken(token) == expected


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["CORE-14"], [TICKET_COMMAND, "CORE-14"]),
        (["CORE-14", "done"], [TICKET_COMMAND, "CORE-14", "done"]),
        (["CORE-14", "set", "-p", "1"], [TICKET_COMMAND, "CORE-14", "set", "-p", "1"]),
        (["CORE-14", "--help"], [TICKET_COMMAND, "CORE-14", "--help"]),
        (["list"], ["list"]),
        (["list", "CORE-14"], ["list", "CORE-14"]),
        (["new", "CORE", "Title"], ["new", "CORE", "Title"]),
        (["--version"], ["--version"]),
        ([], []),
    ],
)
def testIdFirstRewriting(argv: list[str], expected: list[str]) -> None:
    """
    Naming the branch is the whole of the transform, so every other invocation reaches the parser exactly as it was typed.

    argv: The raw argument list.
    expected: What should be handed to the parser.
    """

    assert rewriteIdFirst(argv) == expected


def testFilterResolutionMergesTokensAndFlags() -> None:
    """
    A token and a flag naming different filters combine, since they are two spellings of one set rather than two competing sets.
    """

    assert resolveListFilters(["todo", "CORE"], None, None, 2) == ("todo", "CORE", 2)
    assert resolveListFilters([], "wip", "GEN", None) == ("wip", "GEN", None)
    assert resolveListFilters(["3"], "wip", None, None) == ("wip", None, 3)


def testFilterResolutionRefusesADuplicateSlot() -> None:
    """
    Naming one filter twice asks for two answers to one question.
    """

    with pytest.raises(ConflictingArgumentsError):
        resolveListFilters(["todo"], "wip", None, None)


def testFilterResolutionRefusesAnUnreadableToken() -> None:
    """
    A token matching no class cannot be silently dropped, since dropping it would widen the result the caller asked to narrow.
    """

    with pytest.raises(InvalidArgumentError):
        resolveListFilters(["nonsense"], None, None, None)


def testScopeResolutionReadsTheTokenShape() -> None:
    """
    One positional covers both scopes, because an id and a key cannot be confused for one another.
    """

    assert resolveGraphScope("CORE-14", None, None) == ("CORE-14", None)
    assert resolveGraphScope("CORE", None, None) == (None, "CORE")
    assert resolveGraphScope(None, "CORE-14", None) == ("CORE-14", None)
    assert resolveGraphScope(None, None, None) == (None, None)


def testScopeResolutionRefusesATokenBesideAFlag() -> None:
    """
    The positional and the flags are two spellings of one scope, so supplying both asks for two.
    """

    with pytest.raises(ConflictingArgumentsError):
        resolveGraphScope("CORE", None, "GEN")


def testScopeResolutionRefusesAnUnreadableToken() -> None:
    """
    A scope that is neither an id nor a key would render an empty graph, which reads as an answer rather than a mistake.
    """

    with pytest.raises(InvalidArgumentError):
        resolveGraphScope("nonsense", None, None)


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
