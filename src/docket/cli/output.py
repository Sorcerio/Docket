"""
Docket CLI Output

Everything the CLI prints, and the styling decisions behind it.
"""

# MARK: Imports

import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

# MARK: Constants

# Styles for the status column, matching the intent of the mermaid classes without depending on them.
STATUS_STYLES: dict[str, str] = {"todo": "dim", "wip": "yellow", "done": "green"}

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

        renderable: Anything `rich` can render.
        """

        self.console.print(renderable)

    def raw(self, text: str) -> None:
        """
        Write machine-readable output with no styling applied.

        Mermaid source goes through here, so redirecting it to a file or a pipe yields exactly the source and nothing else.

        text: The text to write.
        """

        sys.stdout.write(text)

    def warn(self, message: str) -> None:
        """
        Report a non-fatal warning.

        message: The warning text.
        """

        self.errorConsole.print(Text(f"warning: {message}", style="yellow"))

    def error(self, message: str) -> None:
        """
        Report a failure.

        message: The error text.
        """

        self.errorConsole.print(Text(f"error: {message}", style="bold red"))


# MARK: Functions


def buildContextTable(heading: str, entries: list[dict[str, object]]) -> Table:
    """
    Build the table showing one direction of a ticket's resolved dependencies.

    heading: What to title the table.
    entries: The resolved records.

    Returns the table.
    """

    table: Table = Table(title=heading, title_justify="left", box=None, pad_edge=False, title_style="bold")
    table.add_column("ID")
    table.add_column("STATUS")
    table.add_column("TITLE")

    if not entries:
        table.add_row("[dim]none[/dim]", "", "")

        return table

    for entry in entries:
        # A dependency naming a missing id is shown rather than hidden, since a broken link the reader cannot see is worse than one they can.
        if not entry["exists"]:
            table.add_row(str(entry["id"]), Text("missing", style="bold red"), "[dim]no such ticket[/dim]")
            continue

        status: str = str(entry["status"])
        table.add_row(str(entry["id"]), Text(status, style=STATUS_STYLES.get(status, "white")), str(entry["title"]))

    return table


def relativeToRoot(path: Optional[Path], root: Path) -> str:
    """
    Describe a path relative to a repository root, so output stays readable in a narrow terminal.

    path: The path to describe.
    root: The directory to describe it against.

    Returns the relative path, falling back to the absolute one when it lies outside the root.
    """

    if path is None:
        return "an unwritten file"

    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
