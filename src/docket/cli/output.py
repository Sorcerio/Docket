"""
Docket CLI Output

Everything the CLI prints, and the styling decisions behind it.
"""

# MARK: Imports

import json
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from docket.core.ticket import Ticket

# MARK: Constants

# Styles for the status column, matching the intent of the mermaid classes without depending on them.
STATUS_STYLES: dict[str, str] = {"todo": "dim", "wip": "yellow", "done": "green"}

# The columns of a dependency table, shared by its styled and plain forms so the two cannot drift.
CONTEXT_COLUMNS: tuple[str, str, str] = ("ID", "STATUS", "TITLE")

# MARK: Classes


class Output:
    """
    Everything the CLI prints.

    Human-facing output goes through `rich`. Machine-readable output does not, because a pipe must receive bare text with no wrapping, highlighting, or escape sequences in it.
    """

    # MARK: Initializer

    def __init__(self) -> None:
        """
        Build the consoles.
        """

        self.console: Console = Console()
        self.errorConsole: Console = Console(stderr=True)

    # MARK: Functions

    def print(self, renderable: object) -> None:
        """
        Print human-facing output.

        Args:
            renderable: Anything `rich` can render.
        """

        self.console.print(renderable)

    def raw(self, text: str) -> None:
        """
        Write machine-readable output with no styling applied.

        Mermaid source goes through here, so redirecting it to a file or a pipe yields exactly the source and nothing else.

        Args:
            text: The text to write.
        """

        sys.stdout.write(text)

    def lines(self, entries: Iterable[object]) -> None:
        """
        Write each entry raw on its own line.

        A list read by a shell is most useful one entry per line, since that is what `while read`, `xargs`, and `wc -l` all expect. An empty list writes nothing at all.

        Args:
            entries: The entries to write.
        """

        self.raw("".join(f"{entry}\n" for entry in entries))

    def json(self, data: Any) -> None:
        """
        Write structured data as JSON.

        `rich` highlights it for a terminal and falls back to plain text when stdout is a pipe or a file, so the same call serves a person and `jq` alike. It also never wraps, so a long value is not split across lines. A value JSON has no form for, such as a date `pyyaml` parsed, is written as its text rather than refused.

        Args:
            data: The data to write.
        """

        self.console.print_json(data=data, default=str)

    def value(self, value: Any) -> None:
        """
        Write one value for a pipe, bare when it is plain and as JSON when it has structure.

        A string or a number is written exactly as it reads, with no quoting. A mapping, a list, a boolean, or a null goes out as JSON, since its own text would be Python's spelling rather than anything a shell could parse.

        Args:
            value: The value to write.
        """

        if isStructured(value):
            self.json(value)
            return

        self.raw(f"{value}\n")

    def warn(self, message: str) -> None:
        """
        Report a non-fatal warning.

        Args:
            message: The warning text.
        """

        self.errorConsole.print(Text(f"warning: {message}", style="yellow"))

    def error(self, message: str) -> None:
        """
        Report a failure.

        Args:
            message: The error text.
        """

        self.errorConsole.print(Text(f"error: {message}", style="bold red"))


# MARK: Functions


def isStructured(value: Any) -> bool:
    """
    Report whether a value has structure that only JSON can spell for a reader.

    A mapping, a list, a boolean, or a null reads as Python's spelling when turned into text, which is neither what was written nor anything a shell could parse.

    Args:
        value: The value to classify.

    Returns:
        Whether the value should be written as JSON.
    """

    return value is None or isinstance(value, (dict, list, tuple, bool))


def describeValue(value: Any) -> str:
    """
    Describe one value on a single line, as compact JSON when it has structure.

    Args:
        value: The value to describe.

    Returns:
        The value's text.
    """

    if isStructured(value):
        return json.dumps(value, default=str)

    return str(value)


def ticketFieldRows(ticket: Ticket, root: Path) -> list[tuple[Text, Text]]:
    """
    Build the labeled rows describing a ticket's frontmatter, for both the styled and plain forms of `show`.

    A map contributes one row per entry, labeled only on its first, so a long map reads as one group. An empty map contributes nothing.

    Args:
        ticket: The ticket to describe.
        root: The directory to describe the ticket's path against.

    Returns:
        The label and value of each row.
    """

    # Style lives on the text itself, so the plain form only has to drop it.
    rows: list[tuple[Text, Text]] = [
        (Text("Status"), Text(ticket.status, style=STATUS_STYLES.get(ticket.status, "white"))),
        (Text("Priority"), Text(str(ticket.priority))),
        (Text("Key"), Text(ticket.key)),
        (Text("File"), Text(relativeToRoot(ticket.path, root))),
    ]

    # Both maps are free-form, so every entry is shown rather than a chosen few.
    for label, entries in (("Metadata", ticket.metadata), ("Extra", ticket.extra)):
        for index, (name, value) in enumerate(entries.items()):
            rows.append((Text(label if index == 0 else ""), Text(f"{name}: {describeValue(value)}")))

    return rows


def buildTicketPanel(ticket: Ticket, root: Path) -> Panel:
    """
    Build the panel heading a shown ticket, titled with its id and title and holding its frontmatter.

    Args:
        ticket: The ticket to describe.
        root: The directory to describe the ticket's path against.

    Returns:
        The panel.
    """

    grid: Table = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()

    for label, value in ticketFieldRows(ticket, root):
        grid.add_row(label, value)

    return Panel(grid, title=Text(f"{ticket.id}  {ticket.title}", style="bold"), title_align="left", expand=False)


def buildTicketBody(ticket: Ticket) -> Markdown:
    """
    Build the rendered form of a ticket's body.

    Args:
        ticket: The ticket whose body to render.

    Returns:
        The body as rendered Markdown.
    """

    return Markdown(ticket.trimmedBody)


def contextRows(entries: list[dict[str, object]]) -> list[tuple[Text, Text, Text]]:
    """
    Build the rows of one direction of a ticket's resolved dependencies, for both the styled and plain forms of `show`.

    Args:
        entries: The resolved records.

    Returns:
        The id, status, and title of each row.
    """

    if not entries:
        return [(Text("none", style="dim"), Text(""), Text(""))]

    rows: list[tuple[Text, Text, Text]] = []
    for entry in entries:
        # A dependency naming a missing id is shown rather than hidden, since a broken link the reader cannot see is worse than one they can.
        if not entry["exists"]:
            rows.append((Text(str(entry["id"])), Text("missing", style="bold red"), Text("no such ticket", style="dim")))
            continue

        status: str = str(entry["status"])
        rows.append((Text(str(entry["id"])), Text(status, style=STATUS_STYLES.get(status, "white")), Text(str(entry["title"]))))

    return rows


def buildContextTable(heading: str, entries: list[dict[str, object]]) -> Table:
    """
    Build the table showing one direction of a ticket's resolved dependencies.

    Args:
        heading: What to title the table.
        entries: The resolved records.

    Returns:
        The table.
    """

    table: Table = Table(title=heading, title_justify="left", box=None, pad_edge=False, title_style="bold", header_style="bold dim")
    for column in CONTEXT_COLUMNS:
        table.add_column(column)

    for row in contextRows(entries):
        table.add_row(*row)

    return table


def plainTicket(ticket: Ticket, context: dict[str, list[dict[str, object]]], root: Path) -> str:
    """
    Describe a shown ticket as bare text, carrying the same content as the styled form with no styling or rendering.

    The body goes out exactly as written, so the Markdown survives for whatever reads it next.

    Args:
        ticket: The ticket to describe.
        context: The ticket's resolved dependency context.
        root: The directory to describe the ticket's path against.

    Returns:
        The text, ending in a newline.
    """

    # Head it the way the panel does, with the rows aligned the way its grid aligns them.
    fieldRows: list[tuple[str, ...]] = [(label.plain, value.plain) for label, value in ticketFieldRows(ticket, root)]
    sections: list[str] = [f"{ticket.id}  {ticket.title}\n{_alignRows(fieldRows)}"]

    # Both directions follow, each under its own heading with the same columns as the styled table.
    for heading, entries in (("Requires", context["requires"]), ("Required by", context["requiredBy"])):
        rows: list[tuple[str, ...]] = [CONTEXT_COLUMNS, *(tuple(cell.plain for cell in row) for row in contextRows(entries))]
        sections.append(f"{heading}\n{_alignRows(rows)}")

    # The body goes last and untouched, and an empty one adds nothing rather than a stray blank section.
    if ticket.trimmedBody:
        sections.append(ticket.trimmedBody)

    return "\n\n".join(sections) + "\n"


def _alignRows(rows: list[tuple[str, ...]]) -> str:
    """
    Align rows of cells into columns separated by two spaces, the way the styled grids space them.

    Args:
        rows: The rows to align.

    Returns:
        One line per row, joined by newlines, with no trailing whitespace.
    """

    widths: list[int] = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]

    return "\n".join("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows)


def relativeToRoot(path: Optional[Path], root: Path) -> str:
    """
    Describe a path relative to a repository root, so output stays readable in a narrow terminal.

    Args:
        path: The path to describe.
        root: The directory to describe it against.

    Returns:
        The relative path, falling back to the absolute one when it lies outside the root.
    """

    if path is None:
        return "an unwritten file"

    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
