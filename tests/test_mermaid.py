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
        '    CORE_9("CORE-9<br/>App shell<br/>p0 done")\n'
        '    CORE_14["CORE-14<br/>Skirmish setup<br/>p1 todo"]\n'
        "  end\n"
        "  subgraph GEN\n"
        '    GEN_3["GEN-3<br/>Multi-layer battlescape<br/>p2 todo"]\n'
        "  end\n"
        "  CORE_9 --> CORE_14\n"
        "  GEN_3 --> CORE_14\n"
        "  classDef doneP0 fill:#2d6a4f,color:#fff,stroke:#ff6b6b,stroke-width:4px\n"
        "  classDef todoP1 fill:#495057,color:#fff,stroke:#ff922b,stroke-width:3px\n"
        "  classDef todoP2 fill:#495057,color:#fff,stroke:#ffd43b,stroke-width:2px\n"
        "  class CORE_9 doneP0\n"
        "  class CORE_14 todoP1\n"
        "  class GEN_3 todoP2\n"
    )

    assert renderGraph(resolveGraph(ticketSet)) == expected


def testTheHyphenatedIdStaysInTheLabel() -> None:
    """
    The identifier is sanitized but the reader still sees the real id.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-14", "Skirmish setup", "todo", 1, []))))

    assert 'CORE_14["CORE-14<br/>Skirmish setup' in output


def testPriorityAndStatusSurviveWithoutClasses() -> None:
    """
    Both readings must survive a renderer that ignores classes entirely, so the label carries the priority and the shape carries the status.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "A", "wip", 3, []))))

    # Dropping every style line still leaves the priority written out and the status shaped.
    assert "<br/>p3 wip" in output
    assert 'CORE_1{{"CORE-1' in output


def testStatusPicksTheNodeShape() -> None:
    """
    Status is said twice, and the shape is the half of it that no renderer can drop.
    """

    ticketSet: TicketSet = buildSet(
        ("CORE-1", "A", "todo", 2, []),
        ("CORE-2", "B", "wip", 2, []),
        ("CORE-3", "C", "done", 2, []),
    )

    output: str = renderGraph(resolveGraph(ticketSet))

    assert 'CORE_1["CORE-1<br/>A<br/>p2 todo"]' in output
    assert 'CORE_2{{"CORE-2<br/>B<br/>p2 wip"}}' in output
    assert 'CORE_3("CORE-3<br/>C<br/>p2 done")' in output


def testPriorityPicksTheBorderWeight() -> None:
    """
    Urgency reads as visual weight and color, so a lower priority number takes a heavier and more saturated border.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "A", "todo", 0, []), ("CORE-2", "B", "todo", 2, []))))

    assert "classDef todoP0 fill:#495057,color:#fff,stroke:#ff6b6b,stroke-width:4px" in output
    assert "classDef todoP2 fill:#495057,color:#fff,stroke:#ffd43b,stroke-width:2px" in output


def testTheRampDrainsToNeutralRatherThanToGreen() -> None:
    """
    Green already means done, so a low-priority todo must not wear the color of finished work. Draining to grey also stays ordered for a reader who cannot separate red from green.
    """

    ticketSet: TicketSet = buildSet(*((f"CORE-{priority + 1}", "A", "todo", priority, []) for priority in range(5)))

    output: str = renderGraph(resolveGraph(ticketSet))

    # The last two bands are the neutrals the ramp ends on, and no band anywhere is a green.
    assert "classDef todoP3 fill:#495057,color:#fff,stroke:#adb5bd,stroke-width:2px" in output
    assert "classDef todoP4 fill:#495057,color:#fff,stroke:#6c757d,stroke-width:1px" in output
    assert "stroke:#2d6a4f" not in output


def testAPriorityPastTheBandSharesTheLightestBorder() -> None:
    """
    The configured ceiling can sit anywhere, so everything past the last band shares its border rather than inventing a class per number.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "A", "todo", 4, []), ("CORE-2", "B", "todo", 9, []))))

    # Both nodes land in the same class, so the priority they differ by shows only in the label.
    assert "  class CORE_1,CORE_2 todoP4\n" in output
    assert "todoP9" not in output
    assert "<br/>p9 todo" in output


def testOnlyTheCombinationsPresentAreDeclared() -> None:
    """
    A class pairs a status with a priority, so declaring every pairing would declare mostly classes nothing takes.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "A", "todo", 2, []))))

    assert "classDef todoP2" in output
    assert output.count("classDef") == 1


def testALongTitleWrapsAcrossLines() -> None:
    """
    Mermaid lays a label out on one line, so one long title would stretch every node beside it.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "Key Removal Checks Usage Outside the Lock", "todo", 2, []))))

    assert 'CORE_1["CORE-1<br/>Key Removal Checks Usage<br/>Outside the Lock<br/>p2 todo"]' in output


def testALongWordIsNotBroken() -> None:
    """
    Breaking an id or a path mid-word costs the reader more than the width does.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "Supercalifragilisticexpialidocious", "todo", 2, []))))

    assert "Supercalifragilisticexpialidocious" in output


def testAnEmptyTitleLeavesNoBlankLine() -> None:
    """
    A title nobody wrote produces no line at all, rather than a gap between the id and the meta line.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "", "todo", 2, []))))

    assert 'CORE_1["CORE-1<br/>p2 todo"]' in output


def testOneSubgraphPerKey() -> None:
    """
    Related work reads as a block, so each key gets its own subgraph and nothing else does.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", "A", "todo", 2, []), ("GEN-1", "B", "todo", 2, []))))

    assert output.count("subgraph ") == 2
    assert output.count("  end\n") == 2


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

    assert "  class CORE_1,CORE_2 todoP2\n" in output
    assert "  class CORE_3 doneP2\n" in output


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
    assert "  class GEN_1 todoP2\n" in output

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

    # It takes the plain shape too, since inventing one would claim to know what the status means.
    assert 'CORE_1["CORE-1<br/>A<br/>p2 blocked"]' in output
    assert "class CORE_1" not in output


def testLabelsEscapeQuotesAndAngleBrackets() -> None:
    """
    A title is free text, so a quote must not end the label early and a bracket must not be read as markup.
    """

    output: str = renderGraph(resolveGraph(buildSet(("CORE-1", 'The "big" <fix>', "todo", 2, []))))

    assert 'CORE_1["CORE-1<br/>The #quot;big#quot; &lt;fix&gt;<br/>p2 todo"]' in output


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
