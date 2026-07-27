"""
Ticket Tests

Cover frontmatter parsing, serialization, field ordering, unknown-key preservation, and body assembly.
"""

# MARK: Imports

from pathlib import Path
from typing import Any

import pytest

from docket.core.errors import TicketParseError
from docket.core.ticket import Ticket, buildBody, parseTicket, serializeTicket, splitFrontmatter

# MARK: Constants

SAMPLE_TICKET: str = """\
---
id: CORE-14
title: Skirmish setup
status: todo
priority: 1
requires: [CORE-9, GEN-3]
---

# Skirmish setup

Goal: a screen where the player sets up one battle and plays it.

Prose continues here, unparsed and unconstrained.
"""

# MARK: Functions


def testParseReadsEveryField() -> None:
    """
    All five recognized fields come back with their expected types.
    """

    ticket: Ticket = parseTicket(SAMPLE_TICKET, path=Path("CORE-14_skirmishSetup.md"))

    assert ticket.id == "CORE-14"
    assert ticket.title == "Skirmish setup"
    assert ticket.status == "todo"
    assert ticket.priority == 1
    assert ticket.requires == ["CORE-9", "GEN-3"]
    assert ticket.key == "CORE"
    assert not ticket.isDone


def testParsePreservesTheBodyVerbatim() -> None:
    """
    The body is prose owned by whoever wrote it, so nothing about it is reinterpreted.
    """

    ticket: Ticket = parseTicket(SAMPLE_TICKET)

    assert ticket.body.startswith("\n# Skirmish setup\n")
    assert "unparsed and unconstrained." in ticket.body


def testRoundTripIsByteStable() -> None:
    """
    Parsing and reserializing an untouched ticket reproduces the file exactly.

    This is the test that catches field reordering, quoting drift, and lost blank lines.
    """

    assert serializeTicket(parseTicket(SAMPLE_TICKET)) == SAMPLE_TICKET


def testEmptyRequiresRendersInline() -> None:
    """
    A ticket with no dependencies reads as `requires: []` on one line rather than as a block.
    """

    ticket: Ticket = Ticket(id="CORE-1", title="App shell", status="todo", priority=2)

    assert "requires: []\n" in serializeTicket(ticket)


def testRequiresRendersInFlowStyle() -> None:
    """
    Dependencies stay on one line, matching the documented format.
    """

    ticket: Ticket = Ticket(id="CORE-1", title="App shell", status="todo", priority=2, requires=["CORE-9", "GEN-3"])

    assert "requires: [CORE-9, GEN-3]\n" in serializeTicket(ticket)


def testFieldOrderIsCanonicalRegardlessOfSourceOrder() -> None:
    """
    A hand-written ticket with shuffled fields is normalized to the documented order on rewrite.
    """

    shuffled: str = "---\npriority: 3\nrequires: []\ntitle: Backwards\nstatus: wip\nid: GEN-2\n---\n\n# Backwards\n"

    text: str = serializeTicket(parseTicket(shuffled))
    lines: list[str] = text.split("\n")

    assert lines[1].startswith("id:")
    assert lines[2].startswith("title:")
    assert lines[3].startswith("status:")
    assert lines[4].startswith("priority:")
    assert lines[5].startswith("requires:")


def testUnknownFieldsSurviveARewrite() -> None:
    """
    A consumer repository may add its own fields, so anything unrecognized round-trips untouched.
    """

    extended: str = (
        "---\n"
        "id: CORE-14\n"
        "title: Skirmish setup\n"
        "status: todo\n"
        "priority: 1\n"
        "requires: []\n"
        "owner: brody\n"
        "tags:\n"
        "- ui\n"
        "- combat\n"
        "---\n"
        "\n"
        "# Skirmish setup\n"
    )

    ticket: Ticket = parseTicket(extended)

    assert ticket.extra == {"owner": "brody", "tags": ["ui", "combat"]}
    assert serializeTicket(ticket) == extended


def testUnknownFieldsKeepTheirReadOrderAfterTheKnownOnes() -> None:
    """
    Preserved fields are appended in the order they were read, never interleaved with the canonical ones.
    """

    extended: str = "---\nowner: brody\nid: CORE-1\nzeta: 1\ntitle: T\nalpha: 2\nstatus: todo\npriority: 0\nrequires: []\n---\n\n# T\n"

    text: str = serializeTicket(parseTicket(extended))
    lines: list[str] = text.split("\n")

    assert [line.split(":")[0] for line in lines[1:9]] == ["id", "title", "status", "priority", "requires", "owner", "zeta", "alpha"]


def testCrlfInputParsesAndIsWrittenBackAsLf() -> None:
    """
    A CRLF checkout parses identically, and the rewrite normalizes to LF so the file does not churn.
    """

    ticket: Ticket = parseTicket(SAMPLE_TICKET.replace("\n", "\r\n"))

    assert ticket.title == "Skirmish setup"
    assert "\r" not in serializeTicket(ticket)


def testAbsentRequiresIsTreatedAsEmpty() -> None:
    """
    A ticket with no dependencies may omit the field entirely rather than being refused.
    """

    minimal: str = "---\nid: CORE-1\ntitle: T\nstatus: todo\npriority: 0\n---\n\n# T\n"

    assert parseTicket(minimal).requires == []


def testALongTitleIsNotWrapped() -> None:
    """
    A long title stays on one line, since wrapping it would break the file's own style rule.
    """

    ticket: Ticket = Ticket(id="CORE-1", title="A" * 300, status="todo", priority=2)

    assert f"title: {'A' * 300}\n" in serializeTicket(ticket)


def testUnicodeTitleIsNotEscaped() -> None:
    """
    A non-ASCII title is written as itself rather than as escape sequences.
    """

    ticket: Ticket = Ticket(id="CORE-1", title="Café résumé", status="todo", priority=2)

    assert "title: Café résumé\n" in serializeTicket(ticket)


@pytest.mark.parametrize(
    "text",
    [
        "# No frontmatter at all\n",
        "\n---\nid: CORE-1\n---\n",
        "---\nid: CORE-1\ntitle: T\nstatus: todo\npriority: 0\n",
        "---\n---\n\n# T\n",
        "---\nnot a mapping\n---\n\n# T\n",
        "---\nid: [unclosed\n---\n\n# T\n",
    ],
)
def testStructurallyBrokenFilesAreRejected(text: str) -> None:
    """
    A missing, unclosed, empty, or non-mapping frontmatter block is a parse failure.
    """

    with pytest.raises(TicketParseError):
        parseTicket(text)


@pytest.mark.parametrize("missing", ["id", "title", "status", "priority"])
def testAMissingRequiredFieldIsRejected(missing: str) -> None:
    """
    Every field except `requires` is mandatory, since a ticket cannot be identified without them.
    """

    fields: dict[str, Any] = {"id": "CORE-1", "title": "T", "status": "todo", "priority": "0"}
    del fields[missing]

    text: str = "---\n" + "".join(f"{name}: {value}\n" for name, value in fields.items()) + "---\n\n# T\n"

    with pytest.raises(TicketParseError):
        parseTicket(text)


@pytest.mark.parametrize(
    "text",
    [
        "---\nid: 14\ntitle: T\nstatus: todo\npriority: 0\n---\n\n# T\n",
        "---\nid: CORE-1\ntitle: T\nstatus: todo\npriority: high\n---\n\n# T\n",
        "---\nid: CORE-1\ntitle: T\nstatus: todo\npriority: true\n---\n\n# T\n",
        "---\nid: CORE-1\ntitle: T\nstatus: todo\npriority: 0\nrequires: CORE-2\n---\n\n# T\n",
        "---\nid: CORE-1\ntitle: T\nstatus: todo\npriority: 0\nrequires: [1, 2]\n---\n\n# T\n",
    ],
)
def testWrongFieldTypesAreRejected(text: str) -> None:
    """
    A field of the wrong type fails at parse, including `true` for an integer field.
    """

    with pytest.raises(TicketParseError):
        parseTicket(text)


def testRuleViolationsAreNotParseErrors() -> None:
    """
    An unrecognized status and an out-of-range priority parse fine, because reporting those belongs to `validate` and it needs the ticket loaded.
    """

    text: str = "---\nid: CORE-1\ntitle: T\nstatus: blocked\npriority: 99\nrequires: []\n---\n\n# T\n"
    ticket: Ticket = parseTicket(text)

    assert ticket.status == "blocked"
    assert ticket.priority == 99


def testSplitFrontmatterStopsAtTheFirstClosingDelimiter() -> None:
    """
    A horizontal rule later in the body does not confuse the split.
    """

    text: str = "---\nid: CORE-1\n---\n\n# T\n\n---\n\nMore prose.\n"
    frontmatterText, body = splitFrontmatter(text)

    assert frontmatterText == "id: CORE-1"
    assert body == "\n# T\n\n---\n\nMore prose.\n"


def testSummaryOmitsTheBody() -> None:
    """
    A listing must never pay for bodies, so the summary form carries none.
    """

    summary: dict[str, Any] = parseTicket(SAMPLE_TICKET).summary()

    assert summary == {"id": "CORE-14", "title": "Skirmish setup", "status": "todo", "priority": 1, "key": "CORE"}
    assert "body" not in summary


def testBuildBodyInjectsAHeading() -> None:
    """
    A body with no heading of its own gets one built from the title.
    """

    assert buildBody("Skirmish setup", "Goal: one battle.") == "\n# Skirmish setup\n\nGoal: one battle.\n"


def testBuildBodyWithNoProseIsJustTheHeading() -> None:
    """
    Creating a ticket without prose still produces a well-formed document.
    """

    assert buildBody("Skirmish setup") == "\n# Skirmish setup\n"
    assert buildBody("Skirmish setup", "") == "\n# Skirmish setup\n"


def testBuildBodyDoesNotDoubleAnExistingHeading() -> None:
    """
    A caller supplying a complete document owns its own structure.
    """

    assert buildBody("Skirmish setup", "# My own heading\n\nProse.") == "\n# My own heading\n\nProse.\n"


def testBuildBodyOutputParsesBackCleanly() -> None:
    """
    A built body slots into a serialized ticket that round-trips.
    """

    ticket: Ticket = Ticket(id="CORE-1", title="App shell", status="todo", priority=2, body=buildBody("App shell", "Prose."))
    text: str = serializeTicket(ticket)

    assert text == "---\nid: CORE-1\ntitle: App shell\nstatus: todo\npriority: 2\nrequires: []\n---\n\n# App shell\n\nProse.\n"
    assert serializeTicket(parseTicket(text)) == text
