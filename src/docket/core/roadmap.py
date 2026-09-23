"""
Docket Roadmap

Rendering the committable roadmap document.

The document is one markdown file a repository keeps under version control, so what it holds is a diagram and the key to reading it, and nothing that would change between two runs over the same tickets.
"""

# MARK: Imports

from dataclasses import dataclass
from typing import Any, Optional

from docket.core.graph import CulledGraph, ResolvedGraph, cullGraph, resolveGraph, scopeGraph
from docket.core.mermaid import renderGraph
from docket.core.store import Store
from docket.core.templating import renderDocument

# MARK: Constants

# The document itself.
ROADMAP_TEMPLATE: str = "roadmap.md.jinja"

# What the roadmap is called once it has been written into a repository.
ROADMAP_FILENAME: str = "roadmap.md"

# The heading an unscoped roadmap carries.
ROADMAP_TITLE: str = "Roadmap"

# MARK: Classes


@dataclass(frozen=True)
class Roadmap:
    """
    A rendered roadmap, and what the node ceiling cost to produce it.

    The count rides along because the document deliberately does not mention it. A roadmap is about where the work is going rather than what has already been finished, so the omission is worth telling the person who ran the command and not worth spending a line of the file on.
    """

    # MARK: Properties

    document: str

    # How many nodes the ceiling dropped, which is zero whenever the whole graph fit.
    dropped: int = 0


# MARK: Functions


def buildContext(graph: ResolvedGraph) -> dict[str, Any]:
    """
    Gather what the document names about the graph it is drawn from.

    graph: The graph the document draws, already scoped and culled.

    Returns the render context.
    """

    return {
        # The scope is whatever narrowed the graph, so a scoped roadmap says so in its own heading rather than looking like the whole project.
        "title": f"{ROADMAP_TITLE}: {graph.scope}" if graph.scope is not None else ROADMAP_TITLE,
        "mermaid": renderGraph(graph),
        # The legend explains a dashed border only where one appears, since a key is the one scope that borrows from outside itself.
        "hasExternal": any(node.isExternal for node in graph.nodes.values()),
    }


def buildRoadmap(store: Store, ticketId: Optional[str] = None, key: Optional[str] = None, status: Optional[str] = None, maxNodes: int = 0) -> Roadmap:
    """
    Render the roadmap for a repository.

    Scoping happens before culling, so the ceiling is measured against what will actually be drawn rather than against the whole repository.

    store: The store to read the tickets from.
    ticketId: The ticket to center on, or `None`.
    key: The key to scope to, or `None`.
    status: The status to scope to, or `None`.
    maxNodes: The node count to aim for, or zero for no ceiling.

    Returns the rendered document and what the ceiling cost.
    """

    culled: CulledGraph = cullGraph(scopeGraph(resolveGraph(store.loadAll()), ticketId, key, status), maxNodes)

    return Roadmap(document=renderDocument(ROADMAP_TEMPLATE, buildContext(culled.graph)), dropped=culled.dropped)
