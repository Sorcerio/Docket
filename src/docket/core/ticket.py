"""
Docket Ticket

The `Ticket` dataclass, frontmatter parsing, and serialization back to markdown.
"""

# MARK: Imports

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from docket.core.errors import InvalidStatusError, TicketParseError
from docket.core.fields import readDict, readInt, readString, readStringList
from docket.core.ids import keyOf

# MARK: Constants

# The status vocabulary is fixed in the tool, not configurable, because only a fixed set can carry the rule that exactly one status moves the file.
STATUS_TODO: str = "todo"
STATUS_WIP: str = "wip"
STATUS_DONE: str = "done"
STATUSES: tuple[str, ...] = (STATUS_TODO, STATUS_WIP, STATUS_DONE)

# The line that opens and closes a frontmatter block.
FRONTMATTER_DELIMITER: str = "---"

# Field order is explicit rather than incidental, so a rewrite never churns the diff.
CANONICAL_FIELDS: tuple[str, ...] = ("id", "title", "status", "priority", "requires", "metadata")

# A very large width keeps `pyyaml` from wrapping a long title across lines.
YAML_WIDTH: int = 1 << 20

# What field errors name, since a ticket's fields all come from its frontmatter block.
FIELD_SOURCE: str = "Frontmatter"

# MARK: Classes


class FlowList(list):
    """
    A list that serializes in YAML flow style.

    This exists so `requires` renders as `[CORE-9, GEN-3]` on one line, and so an empty list reads as `requires: []` rather than as a blank.
    """


class TicketDumper(yaml.SafeDumper):
    """
    A dumper carrying docket's representers.

    Subclassed rather than configured globally so registering a representer cannot affect another consumer of `pyyaml` in the same process.
    """


@dataclass
class Ticket:
    """
    One ticket, holding its frontmatter fields, any unrecognized fields, and its body.
    """

    # MARK: Properties

    id: str
    title: str
    status: str
    priority: int
    requires: list[str] = field(default_factory=list)

    # Free-form entries any tool or skill can attach to a ticket, namespaced by whatever key that consumer chooses.
    metadata: dict[str, Any] = field(default_factory=dict)

    body: str = ""

    # Fields the tool does not recognize, kept in the order they were read so a consumer repo can extend the schema without a tool change.
    extra: dict[str, Any] = field(default_factory=dict)

    # Where the ticket was loaded from, absent for a ticket that has not been written yet.
    path: Optional[Path] = None

    @property
    def key(self) -> str:
        """
        The key portion of the ticket's id.
        """

        return keyOf(self.id)

    @property
    def isDone(self) -> bool:
        """
        Whether the ticket's status is the one that moves the file.
        """

        return self.status == STATUS_DONE

    # MARK: Functions

    def toFrontmatter(self) -> dict[str, Any]:
        """
        Build the frontmatter mapping in canonical order.

        The explicit ordering is the whole mechanism, since dumping with sorting disabled follows insertion order.

        Returns the ordered mapping.
        """

        # Place the recognized fields first, in the documented order.
        mapping: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "requires": FlowList(self.requires),
            "metadata": dict(self.metadata),
        }

        # Append preserved fields after them, in the order they were read.
        for name, value in self.extra.items():
            mapping[name] = value

        return mapping

    def summary(self) -> dict[str, Any]:
        """
        Build the summary form used by listings, which never carries the body.

        Returns the summary mapping.
        """

        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "key": self.key,
        }


# MARK: Functions


def _representFlowList(dumper: yaml.SafeDumper, data: FlowList) -> yaml.Node:
    """
    Represent a `FlowList` as an inline YAML sequence.

    dumper: The active dumper.
    data: The list being represented.

    Returns the sequence node.
    """

    return dumper.represent_sequence("tag:yaml.org,2002:seq", list(data), flow_style=True)


TicketDumper.add_representer(FlowList, _representFlowList)


def requireKnownStatus(status: str) -> str:
    """
    Return the status unchanged, raising when it is not one of the fixed vocabulary.

    The vocabulary is closed, so every surface that accepts a status has the same check to make. It lives here beside the vocabulary itself rather than at each surface, the same way `requireKnownKey` sits beside the registry.

    status: The status to check.

    Returns the same status.
    """

    if status not in STATUSES:
        raise InvalidStatusError(f"Status '{status}' is not one of {', '.join(STATUSES)}.")

    return status


def splitFrontmatter(text: str) -> tuple[str, str]:
    """
    Split raw file text into its frontmatter block and its body.

    The body is returned verbatim, including the blank line that conventionally follows the closing delimiter, so a round-trip reproduces the file exactly.

    text: The full file text, with newlines already normalized to `\\n`.

    Returns a `(frontmatterText, body)` pair.
    """

    lines: list[str] = text.split("\n")

    # A ticket must open with the delimiter on its very first line.
    if not lines or lines[0] != FRONTMATTER_DELIMITER:
        raise TicketParseError(f"File does not open with a '{FRONTMATTER_DELIMITER}' frontmatter delimiter.")

    # Find the closing delimiter, which is the first later line consisting of exactly the delimiter.
    for index in range(1, len(lines)):
        if lines[index] == FRONTMATTER_DELIMITER:
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])

    raise TicketParseError(f"Frontmatter block was opened but never closed with '{FRONTMATTER_DELIMITER}'.")


def parseTicket(text: str, path: Optional[Path] = None) -> Ticket:
    """
    Parse raw file text into a `Ticket`.

    Structural problems raise here. Rule violations such as an out-of-range priority or an unrecognized status do not, because reporting those is `validate`'s job and it needs the ticket loaded to do it.

    text: The full file text.
    path: Where the text came from, recorded on the result.

    Returns the parsed `Ticket`.
    """

    # Normalize line endings so a CRLF checkout parses identically to an LF one. Files are always written back as LF.
    normalized: str = text.replace("\r\n", "\n").replace("\r", "\n")

    frontmatterText, body = splitFrontmatter(normalized)

    # Parse the block, turning any YAML failure into a docket error the shells already know how to report.
    try:
        loaded: Any = yaml.safe_load(frontmatterText)
    except yaml.YAMLError as error:
        raise TicketParseError(f"Frontmatter is not valid YAML: {error}") from error

    # An empty block loads as `None`, which is a missing-fields problem rather than a mapping.
    if loaded is None:
        raise TicketParseError("Frontmatter block is empty.")
    if not isinstance(loaded, dict):
        raise TicketParseError(f"Frontmatter must be a mapping, got {type(loaded).__name__}.")

    ticketId: str = readString(loaded, "id", TicketParseError, FIELD_SOURCE)
    title: str = readString(loaded, "title", TicketParseError, FIELD_SOURCE)
    status: str = readString(loaded, "status", TicketParseError, FIELD_SOURCE)
    priority: int = readInt(loaded, "priority", TicketParseError, FIELD_SOURCE)
    requires: list[str] = readStringList(loaded, "requires", TicketParseError, FIELD_SOURCE)
    metadata: dict[str, Any] = readDict(loaded, "metadata", TicketParseError, FIELD_SOURCE)

    # Keep everything the tool does not recognize, in the order it was read.
    extra: dict[str, Any] = {name: value for name, value in loaded.items() if name not in CANONICAL_FIELDS}

    return Ticket(id=ticketId, title=title, status=status, priority=priority, requires=requires, metadata=metadata, body=body, extra=extra, path=path)


def serializeTicket(ticket: Ticket) -> str:
    """
    Serialize a `Ticket` back to markdown.

    ticket: The ticket to serialize.

    Returns the full file text, with `\\n` newlines.
    """

    # Sorting must stay off, since the explicit field order in the mapping is what keeps diffs clean.
    frontmatterText: str = yaml.dump(
        ticket.toFrontmatter(),
        Dumper=TicketDumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=YAML_WIDTH,
    )

    return f"{FRONTMATTER_DELIMITER}\n{frontmatterText}{FRONTMATTER_DELIMITER}\n{ticket.body}"


def buildBody(title: str, body: Optional[str] = None) -> str:
    """
    Assemble a new ticket's body.

    The file always leads with an H1, because that is the shape the format documents. A supplied body that already opens with its own H1 is used as-is, so a caller writing a complete document does not end up with two headings.

    title: The ticket title, used for the heading when one is needed.
    body: The prose to place under the heading, if any.

    Returns the body text, including the leading blank line that follows the closing frontmatter delimiter.
    """

    # Trim surrounding blank lines so spacing is decided here rather than by the caller.
    prose: str = (body or "").strip("\n")

    # A body that already leads with a heading owns its own structure.
    if prose.startswith("# "):
        return f"\n{prose}\n"

    if not prose:
        return f"\n# {title}\n"

    return f"\n# {title}\n\n{prose}\n"
