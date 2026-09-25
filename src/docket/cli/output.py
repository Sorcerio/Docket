"""
Docket CLI Output

Everything the CLI prints, and the styling decisions behind it.
"""

# MARK: Imports

import sys
from pathlib import Path
from typing import Any, Iterable, Optional

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

        if value is None or isinstance(value, (dict, list, tuple, bool)):
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


def buildContextTable(heading: str, entries: list[dict[str, object]]) -> Table:
    """
    Build the table showing one direction of a ticket's resolved dependencies.

    Args:
        heading: What to title the table.
        entries: The resolved records.

    Returns:
        The table.
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
