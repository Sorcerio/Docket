"""
Graph Tests

Cover reverse edge derivation, scoped traversal, dependency context, and cycle detection.
"""

# MARK: Imports

import pytest

from docket.core.graph import Edge, ResolvedGraph, dependencyContext, findCycles, resolveGraph, subgraphForId, subgraphForKey
from docket.core.store import TicketSet
from docket.core.ticket import Ticket

# MARK: Functions


def buildSet(*specs: tuple[str, list[str]]) -> TicketSet:
    """
    Build a ticket set from id and dependency pairs.

    specs: Pairs of a ticket id and the ids it requires.

    Returns the assembled set.
    """

    ticketSet: TicketSet = TicketSet()
    for ticketId, requires in specs:
        ticketSet.tickets[ticketId] = Ticket(id=ticketId, title=f"Title {ticketId}", status="todo", priority=2, requires=list(requires))

    return ticketSet


def testReverseEdgesAreDerived() -> None:
    """
    A ticket never stores what it blocks, so the reverse direction has to come back from a scan.
    """

    graph: ResolvedGraph = resolveGraph(buildSet(("CORE-9", []), ("GEN-3", []), ("CORE-14", ["CORE-9", "GEN-3"])))

    assert graph.nodes["CORE-14"].requires == ("CORE-9", "GEN-3")
    assert graph.nodes["CORE-9"].requiredBy == ("CORE-14",)
    assert graph.nodes["GEN-3"].requiredBy == ("CORE-14",)
    assert graph.nodes["CORE-14"].requiredBy == ()


def testEdgesPointFromDependencyToDependent() -> None:
    """
    An arrow must read as "must happen before", so it leaves the dependency and lands on the dependent.
    """

    graph: ResolvedGraph = resolveGraph(buildSet(("CORE-9", []), ("CORE-14", ["CORE-9"])))

    assert graph.edges == [Edge(fromId="CORE-9", toId="CORE-14")]


def testAMissingDependencyIsDroppedFromTheGraph() -> None:
    """
    The graph still has to render around a broken link, so an unresolvable id is dropped here and left for `validate` to report.
    """

    graph: ResolvedGraph = resolveGraph(buildSet(("CORE-1", ["CORE-99"])))

    assert graph.nodes["CORE-1"].requires == ()
    assert graph.edges == []


def testEdgeAndNeighborOrderIsNumeric() -> None:
    """
    Ordering is by number rather than by text, so `CORE-2` precedes `CORE-10` in every list.
    """

    graph: ResolvedGraph = resolveGraph(buildSet(("CORE-2", []), ("CORE-10", []), ("CORE-1", ["CORE-10", "CORE-2"])))

    assert graph.nodes["CORE-1"].requires == ("CORE-2", "CORE-10")
    assert [edge.fromId for edge in graph.edges] == ["CORE-2", "CORE-10"]


def testSubgraphForIdWalksBothDirections() -> None:
    """
    Scoping to a ticket gathers everything it transitively depends on and everything that transitively depends on it.
    """

    ticketSet: TicketSet = buildSet(
        ("CORE-1", []),
        ("CORE-2", ["CORE-1"]),
        ("CORE-3", ["CORE-2"]),
        ("CORE-4", ["CORE-3"]),
        ("GEN-1", []),
    )

    scoped: ResolvedGraph = subgraphForId(resolveGraph(ticketSet), "CORE-3")

    assert sorted(scoped.nodes) == ["CORE-1", "CORE-2", "CORE-3", "CORE-4"]
    assert scoped.scope == "CORE-3"

    # An unrelated ticket is not dragged in.
    assert "GEN-1" not in scoped


def testSubgraphForAnUnknownIdIsEmpty() -> None:
    """
    Scoping to a ticket that does not exist yields nothing rather than raising.
    """

    scoped: ResolvedGraph = subgraphForId(resolveGraph(buildSet(("CORE-1", []))), "CORE-99")

    assert len(scoped) == 0
    assert scoped.scope == "CORE-99"


def testSubgraphForKeyMarksCrossKeyNeighbors() -> None:
    """
    A key-scoped graph shows where the key ends, so borrowed neighbors are flagged and members are not.
    """

    ticketSet: TicketSet = buildSet(
        ("GEN-1", []),
        ("GEN-2", ["GEN-1", "CORE-9"]),
        ("CORE-9", []),
        ("CORE-14", ["GEN-2"]),
        ("HEAD-1", ["CORE-14"]),
    )

    scoped: ResolvedGraph = subgraphForKey(resolveGraph(ticketSet), "GEN")

    assert sorted(scoped.nodes) == ["CORE-14", "CORE-9", "GEN-1", "GEN-2"]
    assert not scoped.nodes["GEN-2"].isExternal
    assert scoped.nodes["CORE-9"].isExternal
    assert scoped.nodes["CORE-14"].isExternal

    # Only immediate neighbors are pulled in, so the walk does not spread across the whole set.
    assert "HEAD-1" not in scoped


def testSubgraphOnlyKeepsEdgesWithBothEndsPresent() -> None:
    """
    An edge leaving the scope would render as an arrow to nothing, so it is dropped.
    """

    ticketSet: TicketSet = buildSet(("CORE-1", []), ("CORE-2", ["CORE-1"]), ("GEN-1", ["CORE-2"]))

    scoped: ResolvedGraph = subgraphForId(resolveGraph(ticketSet), "CORE-1")

    for edge in scoped.edges:
        assert edge.fromId in scoped
        assert edge.toId in scoped


def testNodesKeepTheirFullEdgeListsWhenScoped() -> None:
    """
    Only the rendered edges are narrowed, so a caller can still see that a scoped node has neighbors outside.
    """

    ticketSet: TicketSet = buildSet(("CORE-1", []), ("GEN-1", ["CORE-1"]), ("HEAD-1", ["CORE-1"]))

    scoped: ResolvedGraph = subgraphForKey(resolveGraph(ticketSet), "GEN")

    assert set(scoped.nodes["CORE-1"].requiredBy) == {"GEN-1", "HEAD-1"}


def testKeysAndNodesForKeyAreOrdered() -> None:
    """
    A renderer needs deterministic ordering, so keys sort alphabetically and nodes sort by number.
    """

    graph: ResolvedGraph = resolveGraph(buildSet(("GEN-2", []), ("CORE-10", []), ("CORE-2", [])))

    assert graph.keys() == ["CORE", "GEN"]
    assert [node.id for node in graph.nodesForKey("CORE")] == ["CORE-2", "CORE-10"]


def testDependencyContextResolvesBothDirections() -> None:
    """
    The raw file carries bare ids in one direction, so context has to supply the titles, the statuses, and the whole reverse side.
    """

    ticketSet: TicketSet = buildSet(("CORE-9", []), ("CORE-14", ["CORE-9"]), ("HEAD-1", ["CORE-14"]))

    context = dependencyContext(ticketSet, "CORE-14")

    assert context["requires"] == [{"id": "CORE-9", "title": "Title CORE-9", "status": "todo", "priority": 2, "exists": True}]
    assert context["requiredBy"] == [{"id": "HEAD-1", "title": "Title HEAD-1", "status": "todo", "priority": 2, "exists": True}]


def testDependencyContextReportsAMissingDependency() -> None:
    """
    Hiding a broken link would make it invisible to the reader, so it is returned and flagged instead.
    """

    context = dependencyContext(buildSet(("CORE-1", ["CORE-99"])), "CORE-1")

    assert context["requires"] == [{"id": "CORE-99", "title": None, "status": None, "priority": None, "exists": False}]


def testNoCyclesOnAnAcyclicGraph() -> None:
    """
    A well-formed dependency chain reports nothing.
    """

    graph: ResolvedGraph = resolveGraph(buildSet(("CORE-1", []), ("CORE-2", ["CORE-1"]), ("CORE-3", ["CORE-2"])))

    assert findCycles(graph) == []


def testASelfDependencyIsACycle() -> None:
    """
    A ticket requiring itself is a one-node cycle and must be caught.
    """

    assert findCycles(resolveGraph(buildSet(("CORE-1", ["CORE-1"])))) == [["CORE-1"]]


def testATwoNodeCycleIsFound() -> None:
    """
    The simplest real cycle is two tickets each requiring the other.
    """

    assert findCycles(resolveGraph(buildSet(("CORE-1", ["CORE-2"]), ("CORE-2", ["CORE-1"])))) == [["CORE-1", "CORE-2"]]


def testALongerCycleIsFound() -> None:
    """
    A cycle spanning several tickets and keys is reported as one component.
    """

    ticketSet: TicketSet = buildSet(("CORE-1", ["GEN-1"]), ("GEN-1", ["HEAD-1"]), ("HEAD-1", ["CORE-1"]))

    assert findCycles(resolveGraph(ticketSet)) == [["CORE-1", "GEN-1", "HEAD-1"]]


def testSeparateCyclesAreReportedSeparately() -> None:
    """
    Two independent cycles are two findings, not one merged blob.
    """

    ticketSet: TicketSet = buildSet(
        ("CORE-1", ["CORE-2"]),
        ("CORE-2", ["CORE-1"]),
        ("GEN-1", ["GEN-2"]),
        ("GEN-2", ["GEN-1"]),
        ("HEAD-1", []),
    )

    assert findCycles(resolveGraph(ticketSet)) == [["CORE-1", "CORE-2"], ["GEN-1", "GEN-2"]]


def testCycleDetectionSurvivesADeepChain() -> None:
    """
    Traversal is iterative rather than recursive, so a long chain does not exhaust the interpreter stack.
    """

    specs: list[tuple[str, list[str]]] = [("CORE-1", [])]
    specs.extend((f"CORE-{number}", [f"CORE-{number - 1}"]) for number in range(2, 3000))

    assert findCycles(resolveGraph(buildSet(*specs))) == []


def testTraversalSurvivesACycle() -> None:
    """
    `validate` has to render a broken graph in order to explain it, so scoping must not hang on a cycle.
    """

    graph: ResolvedGraph = resolveGraph(buildSet(("CORE-1", ["CORE-2"]), ("CORE-2", ["CORE-1"]), ("CORE-3", ["CORE-1"])))

    scoped: ResolvedGraph = subgraphForId(graph, "CORE-3")

    assert sorted(scoped.nodes) == ["CORE-1", "CORE-2", "CORE-3"]
