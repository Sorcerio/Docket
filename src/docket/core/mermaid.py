"""
Docket Mermaid

Renders a resolved graph to mermaid source.

This is one renderer over `graph.ResolvedGraph` and holds no traversal logic of its own, so a second renderer costs only another module like this one.
"""

# MARK: Imports

from docket.core.graph import Edge, GraphNode, ResolvedGraph
from docket.core.ticket import STATUSES

# MARK: Constants

# Top-down reads naturally for dependencies, since an arrow then points from what must happen first to what follows.
GRAPH_HEADER: str = "graph TD"

# Two spaces per level, matching the shape the format is documented in.
INDENT: str = "  "

# Fills chosen to stay legible on both a light and a dark backdrop, since mermaid renders inside whatever theme the viewer has.
STATUS_STYLES: dict[str, str] = {
    "todo": "fill:#495057,color:#fff",
    "wip": "fill:#9a6700,color:#fff",
    "done": "fill:#2d6a4f,color:#fff",
}

# The class marking a node borrowed from another key, dashed so the boundary reads at a glance.
EXTERNAL_CLASS: str = "external"
EXTERNAL_STYLE: str = "fill:#212529,color:#adb5bd,stroke-dasharray: 3 3"

# Mermaid parses these inside a node label, so they are replaced with the HTML entities it understands.
LABEL_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("&", "&amp;"),
    ('"', "#quot;"),
    ("<", "&lt;"),
    (">", "&gt;"),
)

# MARK: Functions


def renderGraph(graph: ResolvedGraph) -> str:
    """
    Render a resolved graph to mermaid source.

    graph: The graph to render.

    Returns the mermaid source, with a trailing newline and no code fence.
    """

    lines: list[str] = [GRAPH_HEADER]

    # One subgraph per key, so related work reads as a block.
    for key in graph.keys():
        lines.append(f"{INDENT}subgraph {key}")
        for node in graph.nodesForKey(key):
            lines.append(f"{INDENT * 2}{renderNode(node)}")

        lines.append(f"{INDENT}end")

    # Edges sit outside the subgraphs, since an edge may cross between them.
    for edge in graph.edges:
        lines.append(f"{INDENT}{renderEdge(edge)}")

    lines.extend(renderStyles(graph))

    return "\n".join(lines) + "\n"


def renderNode(node: GraphNode) -> str:
    """
    Render one node declaration.

    Priority is written into the label rather than carried by the class, so it survives in a renderer that ignores `classDef` entirely.

    node: The node to render.

    Returns the declaration line.
    """

    return f'{sanitizeId(node.id)}["{escapeLabel(node.id)} {escapeLabel(node.title)}<br/>p{node.priority} {escapeLabel(node.status)}"]'


def renderEdge(edge: Edge) -> str:
    """
    Render one edge.

    edge: The edge to render.

    Returns the edge line, pointing from dependency to dependent.
    """

    return f"{sanitizeId(edge.fromId)} --> {sanitizeId(edge.toId)}"


def renderStyles(graph: ResolvedGraph) -> list[str]:
    """
    Render the class definitions and the class assignments for a graph.

    graph: The graph to style.

    Returns the style lines, empty when there is nothing to style.
    """

    if not graph.nodes:
        return []

    lines: list[str] = [f"{INDENT}classDef {status} {STATUS_STYLES[status]}" for status in STATUSES]

    # Group nodes by the class they take, with external winning over status so the boundary stays visible.
    grouped: dict[str, list[str]] = {}
    for node in graph.nodes.values():
        className: str = EXTERNAL_CLASS if node.isExternal else node.status

        # A status that arrived by hand-editing has no class, and is left unstyled rather than inventing one.
        if className != EXTERNAL_CLASS and className not in STATUS_STYLES:
            continue

        grouped.setdefault(className, []).append(sanitizeId(node.id))

    # Only declare the external class when something actually uses it.
    if EXTERNAL_CLASS in grouped:
        lines.append(f"{INDENT}classDef {EXTERNAL_CLASS} {EXTERNAL_STYLE}")

    for className in sorted(grouped):
        lines.append(f"{INDENT}class {','.join(sorted(grouped[className]))} {className}")

    return lines


def sanitizeId(ticketId: str) -> str:
    """
    Convert a ticket id into a mermaid node identifier.

    Mermaid dislikes a hyphen in an identifier, so it becomes an underscore. The hyphenated id stays in the label, which is what the reader sees.

    ticketId: The id to convert.

    Returns the identifier.
    """

    return ticketId.replace("-", "_")


def escapeLabel(text: str) -> str:
    """
    Escape text for use inside a quoted mermaid label.

    A title is free text, so it may hold a quote or an angle bracket that would otherwise end the label early or be read as markup.

    text: The text to escape.

    Returns the escaped text.
    """

    escaped: str = text

    # The ampersand is replaced first, so the entities introduced afterwards are not themselves re-escaped.
    for character, replacement in LABEL_REPLACEMENTS:
        escaped = escaped.replace(character, replacement)

    return escaped
