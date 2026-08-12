"""
Graph Tests

Cover reverse edge derivation, scoped traversal, dependency context, readiness, and cycle detection.
"""

# MARK: Imports

import pytest

from docket.core.graph import Edge, Readiness, ResolvedGraph, dependencyContext, findCycles, readyTickets, resolveGraph, subgraphForId, subgraphForKey, subgraphForStatus, ticketReadiness
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


def buildStatusSet(*specs: tuple[str, str, list[str]]) -> TicketSet:
    """
    Build a ticket set whose statuses differ, which is what every readiness case turns on.

    specs: Triples of a ticket id, its status, and the ids it requires.

    Returns the assembled set.
    """

    ticketSet: TicketSet = buildSet(*[(ticketId, requires) for ticketId, _, requires in specs])

    for ticketId, status, _ in specs:
        ticketSet.tickets[ticketId].status = status

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


def testSubgraphForStatusKeepsOnlyThatStatus() -> None:
    """
    A status has no boundary worth drawing, so nothing outside it is borrowed and an edge survives only when both of its ends carry it.
    """

    ticketSet: TicketSet = buildSet(
        ("CORE-1", []),
        ("CORE-2", ["CORE-1"]),
        ("CORE-3", ["CORE-2"]),
    )
    ticketSet.tickets["CORE-1"].status = "done"

    scoped: ResolvedGraph = subgraphForStatus(resolveGraph(ticketSet), "todo")

    assert sorted(scoped.nodes) == ["CORE-2", "CORE-3"]
    assert scoped.scope == "todo"

    # The dependency inside the status keeps its arrow, while the one leaving it goes with the node it pointed at.
    assert scoped.edges == [Edge(fromId="CORE-2", toId="CORE-3")]

    # Nothing was borrowed, so the flag a key scope sets is never set here.
    assert not any(node.isExternal for node in scoped.nodes.values())


def testSubgraphForStatusMatchingNothingIsEmpty() -> None:
    """
    A status nothing carries is a true answer rather than a mistake, so it scopes to an empty graph instead of raising.
    """

    scoped: ResolvedGraph = subgraphForStatus(resolveGraph(buildSet(("CORE-1", []))), "done")

    assert len(scoped) == 0
    assert scoped.edges == []


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


def testATicketWithNoDependenciesIsReady() -> None:
    """
    Nothing to wait on is the common case, so it needs no special handling to come back ready.
    """

    assert ticketReadiness(buildSet(("CORE-1", [])), "CORE-1") == Readiness(id="CORE-1", isReady=True, blockedBy=())


def testEveryDependencyDoneMakesATicketReady() -> None:
    """
    Ready is the whole question the check exists to answer, and this is the shape of a yes.
    """

    ticketSet: TicketSet = buildStatusSet(("CORE-9", "done", []), ("GEN-3", "done", []), ("CORE-14", "todo", ["CORE-9", "GEN-3"]))

    assert ticketReadiness(ticketSet, "CORE-14").isReady


def testOneUnfinishedDependencyBlocks() -> None:
    """
    A single open prerequisite is enough, and the answer has to name it rather than only refusing.
    """

    ticketSet: TicketSet = buildStatusSet(("CORE-9", "done", []), ("GEN-3", "wip", []), ("CORE-14", "todo", ["CORE-9", "GEN-3"]))

    readiness: Readiness = ticketReadiness(ticketSet, "CORE-14")

    assert not readiness.isReady
    assert readiness.blockedBy == ({"id": "GEN-3", "title": "Title GEN-3", "status": "wip", "priority": 2, "exists": True},)


def testAMissingDependencyBlocks() -> None:
    """
    A link the reader cannot follow is not the same as clear road, so it blocks and stays visible.
    """

    readiness: Readiness = ticketReadiness(buildSet(("CORE-14", ["CORE-99"])), "CORE-14")

    assert not readiness.isReady
    assert readiness.blockedBy == ({"id": "CORE-99", "title": None, "status": None, "priority": None, "exists": False},)


def testAWipTicketCanStillBeReady() -> None:
    """
    Readiness asks about the dependencies, so work already started does not change the answer.
    """

    assert ticketReadiness(buildStatusSet(("CORE-1", "wip", [])), "CORE-1").isReady


def testADoneTicketIsNeverReady() -> None:
    """
    There is no work left to be ready for, and an empty blocker list is what tells the two apart from being unblocked.
    """

    readiness: Readiness = ticketReadiness(buildStatusSet(("CORE-9", "done", []), ("CORE-14", "done", ["CORE-9"])), "CORE-14")

    assert not readiness.isReady
    assert readiness.blockedBy == ()


def testOnlyDirectDependenciesAreConsulted() -> None:
    """
    A done dependency is taken at its word, since an unfinished dependency behind it is `validate`'s finding rather than this rule's.
    """

    ticketSet: TicketSet = buildStatusSet(("CORE-1", "todo", []), ("CORE-9", "done", ["CORE-1"]), ("CORE-14", "todo", ["CORE-9"]))

    assert ticketReadiness(ticketSet, "CORE-14").isReady


def testACycleBlocksWithoutASpecialCase() -> None:
    """
    No ticket in a cycle can be done, so each one blocks the next by the ordinary rule.
    """

    ticketSet: TicketSet = buildSet(("CORE-1", ["CORE-2"]), ("CORE-2", ["CORE-1"]))

    assert not ticketReadiness(ticketSet, "CORE-1").isReady
    assert not ticketReadiness(ticketSet, "CORE-2").isReady


def testReadyTicketsFiltersAndKeepsOrder() -> None:
    """
    A listing is already ordered by the time it is filtered, so the filter must not reorder what survives.
    """

    ticketSet: TicketSet = buildStatusSet(("CORE-9", "done", []), ("CORE-1", "todo", []), ("CORE-2", "todo", ["CORE-1"]), ("CORE-3", "todo", ["CORE-9"]))
    candidates: list[Ticket] = [ticketSet.tickets[ticketId] for ticketId in ("CORE-3", "CORE-2", "CORE-1")]

    assert [ticket.id for ticket in readyTickets(ticketSet, candidates)] == ["CORE-3", "CORE-1"]


def testReadyTicketsJudgesAgainstTheWholeSet() -> None:
    """
    A dependency may well have been filtered out of the listing, so the candidates and the set they are judged against are separate arguments.
    """

    ticketSet: TicketSet = buildStatusSet(("CORE-9", "done", []), ("CORE-14", "todo", ["CORE-9"]))

    assert [ticket.id for ticket in readyTickets(ticketSet, [ticketSet.tickets["CORE-14"]])] == ["CORE-14"]


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
