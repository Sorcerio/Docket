"""
Docket Graph

Forward and reverse edge resolution, traversal, and cycle detection.

This produces a resolved structure and nothing else. Rendering lives in `mermaid.py`, which is what keeps a second renderer cheap to add later.
"""

# MARK: Imports

from dataclasses import dataclass, field, replace
from typing import Iterable, Optional

from docket.core.ids import parseId
from docket.core.store import TicketSet
from docket.core.ticket import STATUS_DONE, Ticket

# MARK: Classes


@dataclass(frozen=True)
class GraphNode:
    """
    One ticket as it appears in a resolved graph, carrying both edge directions.

    The reverse direction is derived here rather than stored on the ticket, which is what makes a one-sided edge impossible by construction.
    """

    # MARK: Properties

    id: str
    title: str
    status: str
    priority: int
    key: str

    # Ids this ticket depends on, narrowed to the ones that actually exist.
    requires: tuple[str, ...] = ()

    # Ids that depend on this ticket, derived by scanning every other ticket's `requires`.
    requiredBy: tuple[str, ...] = ()

    # Set on a node pulled into a key-scoped graph only because it neighbors that key, so a renderer can show the boundary.
    isExternal: bool = False


@dataclass(frozen=True)
class Edge:
    """
    One dependency edge.

    The direction is dependency to dependent, so an arrow reads as "must happen before".
    """

    # MARK: Properties

    fromId: str
    toId: str


@dataclass(frozen=True)
class Readiness:
    """
    Whether one ticket can be worked on now, and what stands in the way when it cannot.

    This is derived from the set on every read and never stored, for the same reason a reverse edge is. A stored answer would go stale the moment a dependency was closed.
    """

    # MARK: Properties

    id: str

    # Whether every dependency is done and there is still work left to do.
    isReady: bool

    # The resolved records of everything holding this ticket back, in the same shape `dependencyContext` returns. Empty on a ticket that is itself done, since nothing is blocking it.
    blockedBy: tuple[dict[str, object], ...] = ()


@dataclass
class ResolvedGraph:
    """
    A set of nodes and the edges between them, ready to render or traverse.
    """

    # MARK: Properties

    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    # What the graph was scoped to, for a renderer to title with. Absent for the whole set.
    scope: Optional[str] = None

    # MARK: Python Functions

    def __len__(self) -> int:
        """
        Count the nodes.

        Returns:
            The node count.
        """

        return len(self.nodes)

    def __contains__(self, ticketId: str) -> bool:
        """
        Report whether a node is present.

        Args:
            ticketId: The id to test.

        Returns:
            `True` when the graph holds the node.
        """

        return ticketId in self.nodes

    # MARK: Functions

    def keys(self) -> list[str]:
        """
        List every key present, sorted.

        Returns:
            The keys.
        """

        return sorted({node.key for node in self.nodes.values()})

    def nodesForKey(self, key: str) -> list[GraphNode]:
        """
        List the nodes carrying one key, ordered by ticket number.

        Args:
            key: The key to select.

        Returns:
            The ordered nodes.
        """

        return sorted((node for node in self.nodes.values() if node.key == key), key=lambda node: parseId(node.id)[1])


@dataclass(frozen=True)
class CulledGraph:
    """
    A graph narrowed to fit a node ceiling, and how much of it was left behind.

    The count travels beside the graph rather than inside it, because a renderer has no use for it and the caller that asked for the cull does. A document meant to show where the work is going should not spend a line apologizing for the history it dropped, while the person who ran the command is owed the fact that something was dropped at all.
    """

    # MARK: Properties

    graph: ResolvedGraph

    # How many nodes the ceiling cost, which is zero whenever the graph already fit.
    dropped: int = 0


# MARK: Functions


def resolveGraph(ticketSet: TicketSet) -> ResolvedGraph:
    """
    Build the full graph for a ticket set, deriving every reverse edge.

    A `requires` entry naming an id that does not exist is dropped here rather than raising, because reporting it is `validate`'s job and the graph still has to render around it.

    Args:
        ticketSet: The loaded tickets.

    Returns:
        The resolved graph.
    """

    tickets: dict[str, Ticket] = ticketSet.tickets

    # Collect forward edges first, keeping only dependencies that resolve to a real ticket.
    forward: dict[str, list[str]] = {}
    reverse: dict[str, list[str]] = {ticketId: [] for ticketId in tickets}
    for ticketId, ticket in tickets.items():
        resolved: list[str] = [required for required in ticket.requires if required in tickets]
        forward[ticketId] = resolved

        # Derive the reverse direction in the same pass, which is the whole reason the ticket file never stores it.
        for required in resolved:
            reverse[required].append(ticketId)

    graph: ResolvedGraph = ResolvedGraph()

    for ticketId, ticket in tickets.items():
        graph.nodes[ticketId] = GraphNode(
            id=ticketId,
            title=ticket.title,
            status=ticket.status,
            priority=ticket.priority,
            key=ticket.key,
            requires=tuple(_orderedIds(forward[ticketId])),
            requiredBy=tuple(_orderedIds(reverse[ticketId])),
        )

    graph.edges = _buildEdges(graph.nodes)

    return graph


def subgraphForId(graph: ResolvedGraph, ticketId: str) -> ResolvedGraph:
    """
    Scope a graph to one ticket's transitive ancestors and descendants.

    Args:
        ticketId: The ticket at the centre.

    Returns:
        The scoped graph.
    """

    if ticketId not in graph.nodes:
        return ResolvedGraph(scope=ticketId)

    # Walk both directions from the centre, which together give everything this ticket blocks or is blocked by.
    included: set[str] = {ticketId}
    included |= _reachable(graph, ticketId, forward=True)
    included |= _reachable(graph, ticketId, forward=False)

    return _restrict(graph, included, scope=ticketId)


def subgraphForKey(graph: ResolvedGraph, key: str) -> ResolvedGraph:
    """
    Scope a graph to one key, plus the immediate neighbors of that key on either side.

    The neighbors are marked external so a renderer can show where the key ends.

    Args:
        key: The key to scope to.

    Returns:
        The scoped graph.
    """

    members: set[str] = {node.id for node in graph.nodes.values() if node.key == key}

    # Pull in direct neighbors only, on both edge directions, so the boundary is visible without dragging in the whole set.
    neighbors: set[str] = set()
    for memberId in members:
        node: GraphNode = graph.nodes[memberId]
        neighbors |= set(node.requires) | set(node.requiredBy)

    neighbors -= members

    scoped: ResolvedGraph = _restrict(graph, members | neighbors, scope=key)

    # Mark the borrowed nodes, which is what tells a renderer to style them differently.
    for neighborId in neighbors:
        scoped.nodes[neighborId] = replace(scoped.nodes[neighborId], isExternal=True)

    return scoped


def subgraphForStatus(graph: ResolvedGraph, status: str) -> ResolvedGraph:
    """
    Scope a graph to the tickets carrying one status, and nothing else.

    Nothing is borrowed from outside, unlike the key scope. A key has a boundary worth drawing, since the work either side of it is still related, but the tickets around a status are only the same work at a different moment, so pulling them in would put every other status back on the page. An edge therefore survives only when both of its ends carry the status, which is what lets the result read as the ordering within that status alone.

    Args:
        graph: The graph to scope.
        status: The status to scope to.

    Returns:
        The scoped graph.
    """

    members: set[str] = {node.id for node in graph.nodes.values() if node.status == status}

    return _restrict(graph, members, scope=status)


def scopeGraph(graph: ResolvedGraph, ticketId: Optional[str] = None, key: Optional[str] = None, status: Optional[str] = None) -> ResolvedGraph:
    """
    Apply whichever of the three scopes was asked for, and return the graph untouched when none was.

    The three remain exclusive, so the first one set is the one that applies and a caller passing two has already been refused by the grammar that read them. Checking that a key is registered or that a status is spelled correctly belongs to the caller, since the CLI and the server learn those from different places and report them differently.

    Args:
        graph: The graph to scope.
        ticketId: The ticket to center on, or `None`.
        key: The key to scope to, or `None`.
        status: The status to scope to, or `None`.

    Returns:
        The scoped graph, or the same graph when nothing scoped it.
    """

    if ticketId is not None:
        return subgraphForId(graph, ticketId)

    if key is not None:
        return subgraphForKey(graph, key)

    if status is not None:
        return subgraphForStatus(graph, status)

    return graph


def cullGraph(graph: ResolvedGraph, maxNodes: int) -> CulledGraph:
    """
    Narrow a graph toward a node ceiling by dropping the finished work furthest from the work still open.

    Every unfinished ticket survives, whatever the ceiling says, and the finished ones are then admitted ring by ring outward from that seed along both edge directions. So a completed ticket something open still depends on stays, its own dependencies stay behind it while there is room, and the history nothing open reaches any more is what goes first.

    The ceiling is therefore a target rather than a cap. A repository whose open work alone exceeds it keeps all of that work and every finished ticket is dropped, because a roadmap that hides a live ticket is worse than one that renders slowly, and choosing which live ticket to hide is not a choice this can make well.

    A ring that will not fit whole is filled in id order, so the same graph always culls to the same nodes and a committed document does not churn between runs.

    Args:
        graph: The graph to narrow.
        maxNodes: The node count to aim for, or zero and below for no ceiling at all.

    Returns:
        The narrowed graph and the number of nodes it cost.
    """

    # Nothing to do when no ceiling was asked for, or when the graph already sits under the one that was.
    if maxNodes <= 0 or len(graph) <= maxNodes:
        return CulledGraph(graph=graph)

    # Seed with everything still open, which is the part of the graph a reader is looking for and the part that is never given up.
    included: set[str] = {node.id for node in graph.nodes.values() if node.status != STATUS_DONE}

    # Walk outward from that seed, one distance ring at a time, until the ceiling is met or the reachable graph runs out.
    frontier: set[str] = included
    while len(included) < maxNodes:
        ring: set[str] = set()
        for nodeId in frontier:
            node: GraphNode = graph.nodes[nodeId]
            ring |= set(node.requires) | set(node.requiredBy)

        # A node keeps its full edge lists through a scoping, so a neighbor may name something this graph does not hold.
        ring &= graph.nodes.keys()
        ring -= included

        # Nothing further out is reachable, so the ceiling is met with room to spare.
        if not ring:
            break

        # A ring that overflows is taken in part, by id, since every member of it sits at the same distance and nothing else distinguishes them.
        remaining: int = maxNodes - len(included)
        if len(ring) > remaining:
            included |= set(_orderedIds(ring)[:remaining])
            break

        included |= ring
        frontier = ring

    # The scope is carried across, since narrowing a graph does not change what it was scoped to.
    return CulledGraph(graph=_restrict(graph, included, scope=graph.scope), dropped=len(graph) - len(included))


def dependencyContext(ticketSet: TicketSet, ticketId: str) -> dict[str, list[dict[str, object]]]:
    """
    Resolve the context a raw ticket file deliberately does not carry.

    The file stores bare ids in one direction only, so both the title and status of each dependency, and the entire reverse direction, have to be resolved here. This is what lets `read_ticket` be useful without the file duplicating anything.

    Args:
        ticketSet: The loaded tickets.
        ticketId: The ticket to resolve context for.

    Returns:
        A mapping of `requires` and `requiredBy` to summary records.
    """

    graph: ResolvedGraph = resolveGraph(ticketSet)
    ticket: Ticket = ticketSet.get(ticketId)

    # A dependency naming a missing id still has to appear, since hiding it would make a broken link invisible to the reader.
    requires: list[dict[str, object]] = []
    for requiredId in ticket.requires:
        requires.append(_contextEntry(ticketSet, requiredId))

    # The reverse direction is the one thing here the set alone cannot answer, which is what the graph is resolved for.
    node: Optional[GraphNode] = graph.nodes.get(ticketId)
    requiredBy: list[dict[str, object]] = [_contextEntry(ticketSet, dependentId) for dependentId in (node.requiredBy if node is not None else ())]

    return {"requires": requires, "requiredBy": requiredBy}


def ticketReadiness(ticketSet: TicketSet, ticketId: str) -> Readiness:
    """
    Decide whether one ticket can be worked on now.

    Ready means every id in `requires` names a ticket that is done. Only the direct dependencies are consulted, because a done ticket is taken at its word. A done dependency with unfinished dependencies of its own is an inconsistency, and reporting that is `validate`'s job rather than this one's.

    A dependency naming a ticket that does not exist blocks, since a link the reader cannot follow is not the same as clear road. A cycle blocks without a special case, because no ticket in one is ever done.

    Args:
        ticketSet: The loaded tickets.
        ticketId: The ticket to judge.

    Returns:
        The readiness of that ticket.
    """

    return _readinessOf(ticketSet, ticketSet.get(ticketId))


def readyTickets(ticketSet: TicketSet, tickets: Iterable[Ticket]) -> list[Ticket]:
    """
    Select the tickets that can be worked on now, keeping the order they arrived in.

    The whole set is needed to judge any one ticket, so the candidates are passed separately from the set they are judged against. That is what lets a caller filter an already narrowed listing.

    Args:
        ticketSet: The loaded tickets, which every dependency is looked up in.
        tickets: The candidates to filter.

    Returns:
        The ready candidates.
    """

    return [ticket for ticket in tickets if _readinessOf(ticketSet, ticket).isReady]


def findCycles(graph: ResolvedGraph) -> list[list[str]]:
    """
    Find every dependency cycle, reporting one representative per strongly connected component.

    Tarjan's algorithm is used iteratively rather than recursively, so a deep chain cannot exhaust the interpreter stack.

    Args:
        graph: The graph to search.

    Returns:
        One sorted member list per cycle, ordered for stable output.
    """

    index: dict[str, int] = {}
    lowLink: dict[str, int] = {}
    onStack: set[str] = set()
    stack: list[str] = []
    counter: int = 0
    cycles: list[list[str]] = []

    # Iterate roots in sorted order so the reported cycles do not shift between runs.
    for rootId in sorted(graph.nodes):
        if rootId in index:
            continue

        # Each frame holds a node and how far through its successors the walk has got.
        work: list[tuple[str, int]] = [(rootId, 0)]
        while work:
            nodeId, successorIndex = work[-1]

            # First visit to this node, so assign it a discovery index.
            if successorIndex == 0:
                index[nodeId] = counter
                lowLink[nodeId] = counter
                counter += 1
                stack.append(nodeId)
                onStack.add(nodeId)

            successors: tuple[str, ...] = graph.nodes[nodeId].requires
            if successorIndex < len(successors):
                work[-1] = (nodeId, successorIndex + 1)
                successorId: str = successors[successorIndex]

                # Descend into an unvisited successor, or fold a back edge into this node's low link.
                if successorId not in index:
                    work.append((successorId, 0))
                elif successorId in onStack:
                    lowLink[nodeId] = min(lowLink[nodeId], index[successorId])

                continue

            # Every successor is done, so this node's component is decided.
            work.pop()
            if work:
                parentId: str = work[-1][0]
                lowLink[parentId] = min(lowLink[parentId], lowLink[nodeId])

            if lowLink[nodeId] != index[nodeId]:
                continue

            # Pop the component this node roots.
            component: list[str] = []
            while True:
                memberId: str = stack.pop()
                onStack.discard(memberId)
                component.append(memberId)
                if memberId == nodeId:
                    break

            # A component of one is a cycle only when the node depends on itself.
            if len(component) > 1 or nodeId in graph.nodes[nodeId].requires:
                cycles.append(sorted(component))

    return sorted(cycles)


def _readinessOf(ticketSet: TicketSet, ticket: Ticket) -> Readiness:
    """
    Judge one already-loaded ticket, which is what both public entry points do their work through.

    Args:
        ticketSet: The loaded tickets, which every dependency is looked up in.
        ticket: The ticket to judge.

    Returns:
        The readiness of that ticket.
    """

    # A finished ticket has no work left to be ready for, so it is not ready and nothing is holding it back.
    if ticket.isDone:
        return Readiness(id=ticket.id, isReady=False)

    blockers: list[dict[str, object]] = [_contextEntry(ticketSet, requiredId) for requiredId in ticket.requires if not _isSatisfied(ticketSet, requiredId)]

    return Readiness(id=ticket.id, isReady=not blockers, blockedBy=tuple(blockers))


def _isSatisfied(ticketSet: TicketSet, requiredId: str) -> bool:
    """
    Report whether one dependency is met.

    Args:
        requiredId: The id the depending ticket names.

    Returns:
        `True` only when the id names a ticket that exists and is done.
    """

    required: Optional[Ticket] = ticketSet.tickets.get(requiredId)

    return required is not None and required.isDone


def _contextEntry(ticketSet: TicketSet, ticketId: str) -> dict[str, object]:
    """
    Build one resolved dependency record.

    Args:
        ticketSet: The loaded tickets to look the ticket up in.
        ticketId: The id to describe.

    Returns:
        The record, flagged when the id names nothing that exists.
    """

    ticket: Optional[Ticket] = ticketSet.tickets.get(ticketId)
    if ticket is None:
        return {"id": ticketId, "title": None, "status": None, "priority": None, "exists": False}

    return {"id": ticket.id, "title": ticket.title, "status": ticket.status, "priority": ticket.priority, "exists": True}


def _reachable(graph: ResolvedGraph, startId: str, forward: bool) -> set[str]:
    """
    Collect every node reachable from a start node in one direction.

    The visited set makes this safe on a graph that already contains a cycle, which matters because `validate` has to render a broken graph in order to explain it.

    Args:
        graph: The graph to walk.
        startId: The node to walk from.
        forward: Walk `requires` when `True`, `requiredBy` when `False`.

    Returns:
        The reachable ids, excluding the start unless a cycle leads back to it.
    """

    seen: set[str] = set()
    pending: list[str] = list(graph.nodes[startId].requires if forward else graph.nodes[startId].requiredBy)

    while pending:
        currentId: str = pending.pop()
        if currentId in seen or currentId not in graph.nodes:
            continue

        seen.add(currentId)

        node: GraphNode = graph.nodes[currentId]
        pending.extend(node.requires if forward else node.requiredBy)

    return seen


def _restrict(graph: ResolvedGraph, included: set[str], scope: Optional[str]) -> ResolvedGraph:
    """
    Build a graph holding only the named nodes and the edges between them.

    Each node keeps its full edge lists, so a caller can still see that a node has neighbors outside the scope. Only the rendered edges are narrowed.

    Args:
        graph: The graph to restrict.
        included: The ids to keep.
        scope: What the result is scoped to.

    Returns:
        The restricted graph.
    """

    nodes: dict[str, GraphNode] = {ticketId: graph.nodes[ticketId] for ticketId in included if ticketId in graph.nodes}

    return ResolvedGraph(nodes=nodes, edges=_buildEdges(nodes), scope=scope)


def _buildEdges(nodes: dict[str, GraphNode]) -> list[Edge]:
    """
    Build the edge list for a node set, keeping only edges with both ends present.

    Args:
        nodes: The nodes to connect.

    Returns:
        The edges, sorted for stable output.
    """

    edges: list[Edge] = []
    for node in nodes.values():
        for requiredId in node.requires:
            if requiredId in nodes:
                edges.append(Edge(fromId=requiredId, toId=node.id))

    return sorted(edges, key=lambda edge: (_idSortKey(edge.fromId), _idSortKey(edge.toId)))


def _orderedIds(ids: Iterable[str]) -> list[str]:
    """
    Sort ids by key and then numerically, so `CORE-2` precedes `CORE-10`.

    Args:
        ids: The ids to sort.

    Returns:
        The sorted ids.
    """

    return sorted(ids, key=_idSortKey)


def _idSortKey(ticketId: str) -> tuple[str, int]:
    """
    Build the ordering key for one id.

    Args:
        ticketId: The id to order.

    Returns:
        A `(key, number)` tuple.
    """

    return parseId(ticketId)
