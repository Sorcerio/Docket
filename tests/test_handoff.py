"""
Handoff Tests

Render the offsite authoring brief, and hold the document to the rules it teaches.

The brief is read by something that cannot ask a question, so a claim it makes that the code no longer honors is a silent failure. These tests are what keep the two together.
"""

# MARK: Imports

import re

import pytest

from docket.core.config import Config
from docket.core.handoff import HANDOFF_TEMPLATE, KeyBriefing, buildContext, buildKeyBriefings, readDocument, renderHandoff
from docket.core.ids import buildFilename, isValidId
from docket.core.store import Store
from docket.core.ticket import STATUSES, Ticket, parseTicket
from docket.core.titles import isTitleCase

# MARK: Constants

# Every fenced markdown block in the brief, which is where its worked examples live.
EXAMPLE_PATTERN: re.Pattern[str] = re.compile(r"```markdown\n(.*?)\n```", re.DOTALL)

# The filename the brief shows beside its example, and the pieces it claims to be built from.
EXAMPLE_FILENAME: str = "CORE-1_skirmishSetup.md"
EXAMPLE_ID: str = "CORE-1"
EXAMPLE_TITLE: str = "Skirmish Setup"

# MARK: Functions


def testRenderNamesEveryRegisteredKeyWithTheNextIdFreeUnderIt(store: Store) -> None:
    """
    The key table is the whole reason the brief is rendered rather than shipped flat, so it has to carry the description and the number a reader starts at.
    """

    store.create("CORE", "Skirmish Setup")
    store.create("CORE", "Fog of War")

    rendered: str = renderHandoff(store)

    # Two tickets exist under CORE, so the reader is sent to the third number, while an untouched key still starts at one.
    assert "| `CORE` | tactical-sim core | `CORE-3` |" in rendered
    assert "| `GEN` | map generation | `GEN-1` |" in rendered


def testKeyBriefingsAllocateAgainstOneSnapshot(store: Store) -> None:
    """
    Every key allocates from the same loaded set, so two keys can never be described from two different views of the repository.
    """

    store.create("CORE", "Skirmish Setup")

    briefings: list[KeyBriefing] = buildKeyBriefings(store)

    assert [briefing.key for briefing in briefings] == ["CORE", "GEN", "HEAD", "META"]
    assert [briefing.nextId for briefing in briefings] == ["CORE-2", "GEN-1", "HEAD-1", "META-1"]


def testRenderReadsThePriorityBandFromTheConfiguration(store: Store) -> None:
    """
    A brief naming a band the repository does not use would produce tickets `validate` rejects, so the numbers come from the configuration rather than from the document.
    """

    store.config.maxPriority = 6
    store.config.defaultPriority = 5

    rendered: str = renderHandoff(store)

    assert "0 through 6" in rendered
    assert "Use 5 unless" in rendered


def testRenderNamesTheConfiguredTicketDirectory(store: Store, config: Config) -> None:
    """
    The closing steps tell a person where to save what they were handed, which is a path only the configuration knows.
    """

    assert f"{config.root}/{config.todoDir}/" in renderHandoff(store)


def testRenderWithoutAConfigurationTeachesTheReaderToProposeKeys(store: Store) -> None:
    """
    Run outside a repository there is no registry to choose from, so the brief switches to proposing keys rather than failing or rendering an empty table.
    """

    rendered: str = renderHandoff(None)

    assert "No keys were available" in rendered
    assert "Start numbering at" not in rendered

    # The fallback still has to name somewhere to put the files, which is what a freshly deployed repository would use.
    assert "docs/tickets/todo/" in rendered

    # And it must not quietly borrow the keys of whatever repository the command happened to run in.
    assert "tactical-sim core" not in rendered
    assert "tactical-sim core" in renderHandoff(store)


def testContextCarriesNoKeysWithoutAStore() -> None:
    """
    The no-configuration branch is a real context rather than a second document, so it carries the same names with empty and default values.
    """

    context: dict[str, object] = buildContext(None)

    assert context["keys"] == []
    assert context["maxPriority"] == 4
    assert context["defaultPriority"] == 2


@pytest.mark.parametrize("example", EXAMPLE_PATTERN.findall(readDocument(HANDOFF_TEMPLATE)))
def testEveryWorkedExampleParsesAsATicket(example: str) -> None:
    """
    The brief teaches a file format by showing it, so every example it shows is run through the parser that will actually read what the reader writes.

    example: One fenced markdown block lifted from the document.
    """

    ticket: Ticket = parseTicket(example)

    assert isValidId(ticket.id)
    assert ticket.status in STATUSES
    assert isTitleCase(ticket.title)
    assert ticket.body.strip()


def testTheExampleFilenameIsTheOneDocketWouldBuild() -> None:
    """
    The brief spells out a filename convention and then shows one, so the shown one is derived here rather than trusted.
    """

    assert buildFilename(EXAMPLE_ID, EXAMPLE_TITLE) == EXAMPLE_FILENAME
    assert EXAMPLE_FILENAME in readDocument(HANDOFF_TEMPLATE)


def testTheBriefCarriesNoEmDash() -> None:
    """
    House style forbids them, and this document is output as much as it is source.
    """

    assert "—" not in readDocument(HANDOFF_TEMPLATE)
