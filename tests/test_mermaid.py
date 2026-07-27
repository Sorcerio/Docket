"""
Mermaid Tests

Cover node and edge rendering, subgraph grouping, class assignment, and label escaping.
"""

# MARK: Imports

from docket.core.graph import ResolvedGraph, resolveGraph, subgraphForKey
from docket.core.mermaid import escapeLabel, renderGraph, sanitizeId
from docket.core.store import TicketSet
from docket.core.ticket import Ticket

# MARK: Functions


def buildSet(*specs: tuple[str, str, str, int, list[str]]) -> TicketSet:
    """
    Build a ticket set from full specifications.

    specs: Tuples of id, title, status, priority, and required ids.

    Returns the assembled set.
    """

    ticketSet: TicketSet = TicketSet()
    for ticketId, title, status, priority, requires in specs:
        ticketSet.tickets[ticketId] = Ticket(id=ticketId, title=title, status=status, priority=priority, requires=list(requires))

    return ticketSet


def testSanitizeIdReplacesTheHyphen() -> None:
    """
    Mermaid dislikes a hyphen in an identifier, so it becomes an underscore.
    """

    assert sanitizeId("CORE-14") == "CORE_14"


def testTheDocumentedShapeIsProduced() -> None:
    """
    The rendered output matches the shape the format is specified in, line for line.
    """

    ticketSet: TicketSet = buildSet(
        ("CORE-14", "Skirmish setup", "todo", 1, ["CORE-9", "GEN-3"]),
        ("CORE-9", "App shell", "done", 0, []),
        ("GEN-3", "Multi-layer battlescape", "todo", 2, []),
    )

    expected: str = (
        "graph TD\n"
        "  subgraph CORE\n"
        '    CORE_9["CORE-9 App shell<br/>p0 done"]\n'
        '    CORE_14["CORE-14 Skirmish setup<br/>p1 todo"]\n'
        "  end\n"
        "  subgraph GEN\n"
        '    GEN_3["GEN-3 Multi-layer battlescape<br/>p2 todo"]\n'
        "  end\n"
        "  CORE_9 --> CORE_14\n"
        "  GEN_3 --> CORE_14\n"
        "  classDef todo fill:#495057,color:#fff\n"
        "  classDef wip fill:#9a6700,color:#fff\n"
        "  classDef done fill:#2d6a4f,color:#fff\n"
        "  class CORE_9 done\n"
        "  class CORE_14,GEN_3 todo\n"
    )

    assert renderGraph(resolveGraph(ticketSet)) == expected


def testTheHyphenatedIdStaysInTheLabel() -> None:
    """
    The identifier is sanitized but the reader still sees the real id.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-14", "Skirmish setup", "todo", 1, []))))

    assert 'CORE_14["CORE-14 Skirmish setup' in output


def testPriorityIsInTheLabelNotTheStyling() -> None:
    """
    Priority must survive in a renderer that ignores classes entirely, so it lives in the label.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "A", "todo", 3, []))))

    assert "<br/>p3 todo" in output

    # No style line mentions the priority, so a renderer that drops classes loses nothing.
    for line in output.splitlines():
        if line.strip().startswith(("classDef", "class ")):
            assert "p3" not in line


def testOneSubgraphPerKey() -> None:
    """
    Related work reads as a block, so each key gets its own subgraph and nothing else does.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "A", "todo", 2, []), ("GEN-1", "B", "todo", 2, []))))

    assert output.count("subgraph ") == 2
    assert output.count("  end\n") == 2


def testEveryStatusClassIsDeclared() -> None:
    """
    One `classDef` per status, whether or not every status is currently in use.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "A", "todo", 2, []))))

    assert "classDef todo" in output
    assert "classDef wip" in output
    assert "classDef done" in output


def testNodesAreGroupedIntoOneClassLine() -> None:
    """
    Nodes sharing a status share one assignment line rather than one line each.
    """

    ticketSet: TicketSet = buildSet(
        ("CORE-1", "A", "todo", 2, []),
        ("CORE-2", "B", "todo", 2, []),
        ("CORE-3", "C", "done", 2, []),
    )

    output: str = renderGraph(resolveGraph(ticketSet))

    assert "  class CORE_1,CORE_2 todo\n" in output
    assert "  class CORE_3 done\n" in output


def testExternalNodesAreStyledSeparately() -> None:
    """
    A neighbor borrowed from another key is marked so the boundary of the scope is visible.
    """

    ticketSet: TicketSet = buildSet(
        ("GEN-1", "A", "todo", 2, ["CORE-9"]),
        ("CORE-9", "B", "done", 0, []),
    )

    output: str = renderGraph(subgraphForKey(resolveGraph(ticketSet), "GEN"))

    assert "classDef external" in output
    assert "  class CORE_9 external\n" in output
    assert "  class GEN_1 todo\n" in output

    # The borrowed node keeps its own key's subgraph, so the reader still sees where it came from.
    assert "subgraph CORE" in output


def testTheExternalClassIsOnlyDeclaredWhenUsed() -> None:
    """
    An unscoped graph has no boundary, so it carries no external class.
    """

    assert "external" not in renderGraph(resolveGraph(buildSet(("CORE-1", "A", "todo", 2, []))))


def testAnEmptyGraphRendersAHeaderOnly() -> None:
    """
    Nothing to draw produces a valid but empty diagram rather than stray style lines.
    """

    assert renderGraph(ResolvedGraph()) == "graph TD\n"


def testAnUnrecognizedStatusIsLeftUnstyled() -> None:
    """
    A status that arrived by hand-editing gets no class rather than an invented one, and still renders as a node.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "A", "blocked", 2, []))))

    assert 'CORE_1["CORE-1 A<br/>p2 blocked"]' in output
    assert "class CORE_1" not in output


def testLabelsEscapeQuotesAndAngleBrackets() -> None:
    """
    A title is free text, so a quote must not end the label early and a bracket must not be read as markup.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", 'The "big" <fix>', "todo", 2, []))))

    assert 'CORE_1["CORE-1 The #quot;big#quot; &lt;fix&gt;<br/>p2 todo"]' in output


def testAmpersandIsEscapedOnlyOnce() -> None:
    """
    The ampersand is replaced first, so the entities introduced afterwards are not themselves re-escaped.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "Fog & war", "todo", 2, []))))

    assert "Fog &amp; war" in output
    assert "&amp;amp;" not in output


def testEscapeLabelIsIdempotentOnPlainText() -> None:
    """
    Ordinary text passes through untouched.
    """

    assert escapeLabel("Skirmish setup") == "Skirmish setup"


def testOutputCarriesNoCodeFence() -> None:
    """
    The renderer emits bare source, since fencing is a presentation choice belonging to whoever displays it.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "A", "todo", 2, []))))

    assert "```" not in output
    assert output.startswith("graph TD\n")
    assert output.endswith("\n")
