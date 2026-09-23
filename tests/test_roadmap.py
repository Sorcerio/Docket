"""
Roadmap Tests

Cover the rendered document's shape, its scoped heading, its legend, and what the node ceiling costs it.
"""

# MARK: Imports

import pytest

from docket.core.roadmap import ROADMAP_TEMPLATE, Roadmap, buildRoadmap
from docket.core.store import Store
from docket.core.templating import readDocument
from docket.core.ticket import Ticket

# MARK: Constants

# The fence a markdown renderer needs in order to draw the diagram rather than print it.
MERMAID_FENCE: str = "```mermaid\n"

# MARK: Functions


def seed(store: Store) -> None:
    """
    Create a small set of tickets with a dependency crossing between two keys.

    store: The store to create them in.
    """

    store.create(key="CORE", title="App Shell")
    store.create(key="GEN", title="Map Generation", requires=["CORE-1"])


def testDocumentFencesTheDiagram(store: Store) -> None:
    """
    The whole point of the document over bare mermaid source is that a markdown renderer draws the diagram, which takes a fence the renderer itself never emits.
    """

    seed(store)

    document: str = buildRoadmap(store).document

    assert document.startswith("# Roadmap\n")
    assert MERMAID_FENCE in document

    # The diagram sits inside the fence rather than beside it, and the fence closes.
    body: str = document.split(MERMAID_FENCE, 1)[1]

    assert body.startswith("graph TD\n")
    assert "\n```\n" in body


def testDocumentCarriesTheLegend(store: Store) -> None:
    """
    A renderer that ignores `classDef` drops every fill and border, so the shapes have to be explained in text that survives anywhere.
    """

    seed(store)

    document: str = buildRoadmap(store).document

    assert "## Legend" in document

    for shape in ("`[ ]`", "`{ }`", "`( )`"):
        assert shape in document


def testDocumentIsUnchangedBetweenRuns(store: Store) -> None:
    """
    The document is committed, so anything that differed between two runs over the same tickets would show up as a diff that means nothing.
    """

    seed(store)

    assert buildRoadmap(store).document == buildRoadmap(store).document


def testUnscopedDocumentNamesNoScope(store: Store) -> None:
    """
    The plain heading is what says the document covers the whole repository.
    """

    seed(store)

    assert buildRoadmap(store).document.startswith("# Roadmap\n")


@pytest.mark.parametrize(
    ("kwargs", "heading"),
    [
        ({"key": "CORE"}, "# Roadmap: CORE\n"),
        ({"status": "todo"}, "# Roadmap: todo\n"),
        ({"ticketId": "CORE-1"}, "# Roadmap: CORE-1\n"),
    ],
)
def testScopedDocumentNamesItsScope(store: Store, kwargs: dict[str, str], heading: str) -> None:
    """
    A scoped roadmap says so in its own heading, so it cannot be mistaken for the whole project.

    kwargs: The scope to build with.
    heading: The heading the scope should produce.
    """

    seed(store)

    assert buildRoadmap(store, **kwargs).document.startswith(heading)


def testLegendExplainsABorrowedTicketOnlyWhenOneIsShown(store: Store) -> None:
    """
    A key is the one scope that borrows from outside itself, so the dashed border is explained there and nowhere else.
    """

    seed(store)

    assert "A dashed border" in buildRoadmap(store, key="CORE").document
    assert "A dashed border" not in buildRoadmap(store).document


def testCeilingDropsFinishedWorkAndIsReported(store: Store) -> None:
    """
    The document deliberately says nothing about what was dropped, so the count has to leave through the result for the caller to report instead.
    """

    seed(store)

    # Finish the dependency, leaving one open ticket and one completed one.
    finished: Ticket = store.setStatus("CORE-1", "done")

    assert finished.isDone

    roadmap: Roadmap = buildRoadmap(store, maxNodes=1)

    assert roadmap.dropped == 1
    assert "CORE-1" not in roadmap.document
    assert "GEN-1" in roadmap.document

    # Nothing in the file admits to the omission, which is the whole reason the count travels beside it.
    assert "omitted" not in roadmap.document


def testNoCeilingKeepsEverything(store: Store) -> None:
    """
    Zero is the documented way to ask for the whole graph, which is also the default every caller passes when no ceiling is configured.
    """

    seed(store)

    roadmap: Roadmap = buildRoadmap(store, maxNodes=0)

    assert roadmap.dropped == 0
    assert "CORE-1" in roadmap.document
    assert "GEN-1" in roadmap.document


def testAnEmptyRepositoryStillRenders(store: Store) -> None:
    """
    A freshly deployed repository has no tickets, and a roadmap run there is a reasonable thing to do rather than an error.
    """

    document: str = buildRoadmap(store).document

    assert document.startswith("# Roadmap\n")
    assert MERMAID_FENCE in document


def testTemplateHoldsNoEmDash() -> None:
    """
    The repository writes no em dash anywhere, and a shipped document is read by more people than the source is.
    """

    assert "—" not in readDocument(ROADMAP_TEMPLATE)
