"""
Docket Mermaid

Renders a resolved graph to mermaid source.

This is one renderer over `graph.ResolvedGraph` and holds no traversal logic of its own, so a second renderer costs only another module like this one.
"""

# MARK: Imports

import textwrap

from docket.core.graph import Edge, GraphNode, ResolvedGraph

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

# The delimiters that shape a node, so status survives in a renderer that ignores `classDef` entirely, the same way priority does by sitting in the label. Work in flight reads as a hexagon and finished work as a rounded rectangle, leaving the plain rectangle for what has not been started.
STATUS_SHAPES: dict[str, tuple[str, str]] = {
    "todo": ("[", "]"),
    "wip": ("{{", "}}"),
    "done": ("(", ")"),
}

# The shape a status nobody recognizes takes. It is the plain one, for the same reason such a node takes no class: inventing a shape for it would claim to know what it means.
DEFAULT_SHAPE: tuple[str, str] = ("[", "]")

# The border a node takes from its priority, most urgent first, so urgency reads as weight and color and not only as the text in the label. A priority past the end of this takes the last entry, because the band's ceiling is configurable and this module cannot see it.
#
# The ramp drains toward neutral rather than cooling toward green, for two reasons. Green already means done here, so a low-priority todo would otherwise wear the color of finished work. And a red to green ramp is the one pairing a red-green colorblind reader cannot order at all, where draining to grey stays legible to everyone. Grey is also the honest end point, since the least urgent thing on the page wants no attention rather than a different kind of it.
#
# Width descends alongside the color, so the ordering survives being read in greyscale.
PRIORITY_STROKES: tuple[str, ...] = (
    "stroke:#ff6b6b,stroke-width:4px",
    "stroke:#ff922b,stroke-width:3px",
    "stroke:#ffd43b,stroke-width:2px",
    "stroke:#adb5bd,stroke-width:2px",
    "stroke:#6c757d,stroke-width:1px",
)

# Where a long title wraps, in characters. Mermaid lays a label out on one line unless told otherwise, so one long title would stretch every node beside it.
LABEL_WRAP_WIDTH: int = 24

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

    Status and priority are each said twice, once in a way a bare renderer keeps and once in a way it drops. The shape and the label survive anywhere, while the fill and the border are the richer reading for a renderer that honors `classDef`. So nothing a reader needs is only ever a color.

    node: The node to render.

    Returns the declaration line.
    """

    opening, closing = STATUS_SHAPES.get(node.status, DEFAULT_SHAPE)

    return f'{sanitizeId(node.id)}{opening}"{renderLabel(node)}"{closing}'


def renderLabel(node: GraphNode) -> str:
    """
    Build the label text for one node.

    The id, the title, and the priority and status sit on their own lines rather than running together, since the id is what a reader scans for and a title beside it buries the id.

    node: The node to label.

    Returns the label, with its lines joined by mermaid's line break.
    """

    lines: list[str] = [escapeLabel(node.id), *wrapLabel(node.title), f"p{node.priority} {escapeLabel(node.status)}"]

    return "<br/>".join(lines)


def wrapLabel(text: str) -> list[str]:
    """
    Split a title into label lines at word boundaries.

    Wrapping happens before escaping, so an entity the escape introduces can neither be counted toward the width nor be broken across two lines. A single word longer than the width is left whole, because breaking an id or a path mid-word costs the reader more than the width does.

    text: The title to wrap.

    Returns the escaped lines, empty when there is no title to show.
    """

    if not text.strip():
        return []

    return [escapeLabel(line) for line in textwrap.wrap(text, width=LABEL_WRAP_WIDTH, break_long_words=False, break_on_hyphens=False)]


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

    A class carries the fill of a status and the border of a priority together, rather than a node taking one class for each. Combining them is what keeps every node to a single class, and it means only the combinations actually present are ever declared.

    graph: The graph to style.

    Returns the style lines, empty when there is nothing to style.
    """

    if not graph.nodes:
        return []

    # Group nodes by the class they take, with external winning over status so the boundary stays visible.
    styles: dict[str, str] = {}
    grouped: dict[str, list[str]] = {}
    for node in graph.nodes.values():
        if node.isExternal:
            className, style = EXTERNAL_CLASS, EXTERNAL_STYLE
        elif node.status in STATUS_STYLES:
            className, style = statusClassName(node.status, node.priority), f"{STATUS_STYLES[node.status]},{priorityStroke(node.priority)}"
        else:
            # A status that arrived by hand-editing has no class, and is left unstyled rather than inventing one.
            continue

        styles[className] = style
        grouped.setdefault(className, []).append(sanitizeId(node.id))

    lines: list[str] = [f"{INDENT}classDef {className} {styles[className]}" for className in sorted(styles)]

    for className in sorted(grouped):
        lines.append(f"{INDENT}class {','.join(sorted(grouped[className]))} {className}")

    return lines


def statusClassName(status: str, priority: int) -> str:
    """
    Name the class carrying one status and priority pairing.

    The priority is named by its band rather than by its number, so the class count stays bounded however high the configured ceiling goes.

    status: The status the class fills for.
    priority: The priority the class borders for.

    Returns the class name.
    """

    return f"{status}P{priorityBand(priority)}"


def priorityStroke(priority: int) -> str:
    """
    Select the border for one priority.

    priority: The priority to style.

    Returns the stroke declaration.
    """

    return PRIORITY_STROKES[priorityBand(priority)]


def priorityBand(priority: int) -> int:
    """
    Clamp a priority to an index into `PRIORITY_STROKES`.

    Everything past the end shares the lightest border, since the configured ceiling can sit anywhere above it and a band nobody can distinguish is not worth a class of its own.

    priority: The priority to place.

    Returns the index.
    """

    return min(max(priority, 0), len(PRIORITY_STROKES) - 1)


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
