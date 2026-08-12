"""
Docket Store

Discovery, loading, writing, and mutation of tickets on disk.
"""

# MARK: Imports

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

from docket.core.atomic import writeTextAtomic
from docket.core.config import Config
from docket.core.errors import ConflictingArgumentsError, InvalidPriorityError, InvalidStatusError, TicketNotFoundError, TicketParseError
from docket.core.ids import buildFilename, nextId, parseId, requireValidKey
from docket.core.inputs import requireText
from docket.core.ticket import STATUS_DONE, STATUSES, Ticket, buildBody, parseTicket, serializeTicket
from docket.core.titles import toTitleCase

# MARK: Constants

# Only markdown files are considered tickets, so a stray README or image under a status directory is ignored rather than reported.
TICKET_GLOB: str = "*.md"

# MARK: Classes


@dataclass(frozen=True)
class LoadFailure:
    """
    A file under a status directory that could not be read as a ticket.

    These are collected rather than raised, so one broken file does not prevent every other ticket from loading and so `validate` can report it as a finding.
    """

    # MARK: Properties

    path: Path
    message: str


@dataclass(frozen=True)
class DuplicateId:
    """
    A file carrying an id another file already claimed.

    Two branches minting under the same key produce this, which is the accepted cost of deriving numbers by scanning rather than from a counter file.
    """

    # MARK: Properties

    id: str
    path: Path
    existingPath: Path


@dataclass
class TicketResult:
    """
    A written ticket together with any non-fatal warnings raised while writing it.

    A dangling `requires` entry is a warning rather than an error at write time, so an agent writing a batch out of order is never stranded mid-batch.
    """

    # MARK: Properties

    ticket: Ticket
    warnings: list[str] = field(default_factory=list)


@dataclass
class TicketSet:
    """
    Every ticket found under the configured root, plus whatever could not be read.
    """

    # MARK: Properties

    tickets: dict[str, Ticket] = field(default_factory=dict)
    failures: list[LoadFailure] = field(default_factory=list)
    duplicates: list[DuplicateId] = field(default_factory=list)

    # MARK: Python Functions

    def __contains__(self, ticketId: str) -> bool:
        """
        Report whether an id is present.

        ticketId: The id to test.

        Returns `True` when a ticket carries the id.
        """

        return ticketId in self.tickets

    def __iter__(self) -> Iterator[Ticket]:
        """
        Iterate every loaded ticket in sorted order.

        Returns an iterator over tickets.
        """

        return iter(self.sorted())

    def __len__(self) -> int:
        """
        Count the loaded tickets.

        Returns the ticket count.
        """

        return len(self.tickets)

    # MARK: Functions

    def get(self, ticketId: str) -> Ticket:
        """
        Fetch one ticket by id.

        ticketId: The id to look up.

        Returns the ticket.
        """

        if ticketId not in self.tickets:
            raise TicketNotFoundError(f"No ticket with id '{ticketId}'.")

        return self.tickets[ticketId]

    def ids(self) -> list[str]:
        """
        List every loaded id.

        Returns the ids, unsorted.
        """

        return list(self.tickets)

    def sorted(self) -> list[Ticket]:
        """
        Order tickets by priority, then by key, then by number.

        The number is compared numerically rather than as text, so `CORE-2` precedes `CORE-10`.

        Returns the ordered tickets.
        """

        return sorted(self.tickets.values(), key=_sortKey)

    def filtered(self, status: Optional[str] = None, key: Optional[str] = None, priorityMax: Optional[int] = None) -> list[Ticket]:
        """
        Select tickets matching every supplied filter, in sorted order.

        status: Keep only tickets with this status.
        key: Keep only tickets carrying this key.
        priorityMax: Keep only tickets at or below this priority number, meaning at or above this urgency.

        Returns the matching tickets.
        """

        matches: list[Ticket] = self.sorted()

        # Apply each filter only when it was supplied, so an omitted filter never narrows the result.
        if status is not None:
            matches = [ticket for ticket in matches if ticket.status == status]
        if key is not None:
            matches = [ticket for ticket in matches if ticket.key == key]
        if priorityMax is not None:
            matches = [ticket for ticket in matches if ticket.priority <= priorityMax]

        return matches


class Store:
    """
    Reads and writes tickets under one configuration's ticket root.
    """

    # MARK: Initializer

    def __init__(self, config: Config) -> None:
        """
        Bind a store to a configuration.

        config: The configuration naming the ticket root and the status directories.
        """

        self.config: Config = config

    # MARK: Functions

    def directoryFor(self, status: str) -> Path:
        """
        Resolve the directory a status belongs in.

        `done` is the only status that moves a file, so everything else shares the todo directory. That rule is what keeps the vocabulary fixed rather than configurable.

        status: The status to resolve.

        Returns the absolute directory path.
        """

        return self.config.donePath if status == STATUS_DONE else self.config.todoPath

    def pathFor(self, ticket: Ticket) -> Path:
        """
        Resolve where a ticket's file belongs.

        Filenames are frozen at creation, so an already-written ticket keeps its existing filename even after a retitle. Only the directory follows the status.

        ticket: The ticket to place.

        Returns the absolute file path.
        """

        # Reuse the existing filename when there is one, since retitling must not rename the file.
        filename: str = ticket.path.name if ticket.path is not None else buildFilename(ticket.id, ticket.title)

        return self.directoryFor(ticket.status) / filename

    def discoverPaths(self) -> list[Path]:
        """
        List every candidate ticket file under both status directories.

        Returns the paths, sorted so results are deterministic across platforms.
        """

        paths: list[Path] = []

        # A directory that does not exist yet is not an error, since a freshly deployed repository has no tickets.
        for directory in (self.config.todoPath, self.config.donePath):
            if directory.is_dir():
                paths.extend(sorted(directory.glob(TICKET_GLOB)))

        return paths

    def loadAll(self) -> TicketSet:
        """
        Load every ticket under the configured root, holding the repository's read lock while doing so.

        Returns the loaded `TicketSet`.
        """

        # A caller already inside a write lock must not come through here, since the lock refuses to downgrade from writing to reading. Those callers use the unlocked form directly.
        with self.config.sharedLock():
            return self.__loadAllUnlocked()

    def load(self, ticketId: str) -> Ticket:
        """
        Load one ticket by id.

        ticketId: The id to look up.

        Returns the ticket.
        """

        return self.loadAll().get(ticketId)

    def write(self, ticket: Ticket) -> Ticket:
        """
        Write a ticket to the path its status and filename imply.

        This does not move an existing file. `setStatus` owns that, so no caller can change a status without the move happening in the same operation.

        ticket: The ticket to write.

        Returns the ticket with its path recorded.
        """

        path: Path = self.pathFor(ticket)

        # A freshly deployed repository may not have the status directories yet.
        path.parent.mkdir(parents=True, exist_ok=True)

        # Replace the file in one step, so a concurrent reader sees either the old ticket or the new one and never a truncated file.
        writeTextAtomic(path, serializeTicket(ticket))
        ticket.path = path

        return ticket

    def create(
        self,
        key: str,
        title: str,
        body: Optional[str] = None,
        requires: Optional[list[str]] = None,
        priority: Optional[int] = None,
    ) -> TicketResult:
        """
        Allocate an id and write a new ticket.

        The id is derived by scanning what already exists, so the scan and the write are held together under one lock. Without that, two processes minting under one key read the same set and allocate the same number.

        key: The key to mint under, which must be registered.
        title: The ticket title, converted to title case before anything derives from it.
        body: Prose for the body, placed under a heading built from the title.
        requires: Ids this ticket depends on.
        priority: The priority, defaulting to the configuration's `defaultPriority`.

        Returns the written ticket and any warnings.
        """

        # The filename slug derives from the title once, here, so an empty one is frozen into the filename as well as the field.
        requireText(title, "title")

        # Convert before the id is allocated, so the slug and the body heading are both built from the title that actually gets stored.
        casedTitle: str = toTitleCase(title)

        # A key must be registered before anything is minted under it, and the error names `add_key` as the way out.
        requireValidKey(key)
        self.config.requireKnownKey(key)

        with self.config.exclusiveLock():
            existing: TicketSet = self.__loadAllUnlocked()

            resolvedPriority: int = priority if priority is not None else self.config.defaultPriority
            self.__requireValidPriority(resolvedPriority)

            ticket: Ticket = Ticket(
                id=nextId(key, existing.ids()),
                title=casedTitle,
                status=STATUSES[0],
                priority=resolvedPriority,
                requires=list(requires or []),
                body=buildBody(casedTitle, body),
            )

            return TicketResult(ticket=self.write(ticket), warnings=self.__danglingWarnings(ticket, existing))

    def update(
        self,
        ticketId: str,
        title: Optional[str] = None,
        priority: Optional[int] = None,
        requires: Optional[list[str]] = None,
        requiresAdd: Optional[list[str]] = None,
        requiresRemove: Optional[list[str]] = None,
    ) -> TicketResult:
        """
        Change a ticket's title, priority, or dependencies in place.

        Status is deliberately excluded, because changing it moves the file and that belongs to `setStatus`. The filename is excluded because it is frozen at creation, so a retitle leaves every prose cross-reference intact.

        The dependency list is edited either wholesale or in place, never both in one call. `requires` replaces it. `requiresAdd` and `requiresRemove` edit whatever is already there, which is what spares a caller from retyping a long list to change one entry.

        The load and the write back are held together under one lock, since a second process changing a different field in the gap would have its change reverted by this write.

        ticketId: The ticket to change.
        title: A new title, converted to title case, if any.
        priority: A new priority, if any.
        requires: A replacement dependency list, if any.
        requiresAdd: Ids to append to the existing list, if any.
        requiresRemove: Ids to drop from the existing list, if any.

        Returns the written ticket and any warnings.
        """

        # Replacing the list and editing it in place at once names no order the caller actually asked for.
        if requires is not None and (requiresAdd is not None or requiresRemove is not None):
            raise ConflictingArgumentsError("A replacement dependency list cannot be combined with adding to or removing from the existing one. Pass either the replacement or the edits.")

        with self.config.exclusiveLock():
            existing: TicketSet = self.__loadAllUnlocked()
            ticket: Ticket = existing.get(ticketId)

            if title is not None:
                ticket.title = toTitleCase(requireText(title, "title"))

            if priority is not None:
                self.__requireValidPriority(priority)
                ticket.priority = priority

            if requires is not None:
                ticket.requires = list(requires)

            # Removal runs first, so passing the same id to both ends with it present rather than gone.
            if requiresRemove is not None:
                dropped: set[str] = set(requiresRemove)
                ticket.requires = [required for required in ticket.requires if required not in dropped]

            # New ids append in the order given, and one already present is left where it is rather than duplicated.
            if requiresAdd is not None:
                for required in requiresAdd:
                    if required not in ticket.requires:
                        ticket.requires.append(required)

            return TicketResult(ticket=self.write(ticket), warnings=self.__danglingWarnings(ticket, existing))

    def setMetadata(self, ticketId: str, key: str, value: Optional[Any]) -> TicketResult:
        """
        Set or clear one entry in a ticket's `metadata` map.

        Only the named entry is touched, so one consumer's key survives another consumer writing its own. `value` of `None` removes the entry rather than storing a null, keeping the map free of placeholders nothing reads.

        The whole file is rewritten to change the one entry, so the load and the write back are held together under one lock. Two consumers namespacing their keys correctly would still lose one of the two without it.

        ticketId: The ticket to change.
        key: The metadata key, which cannot be empty.
        value: The value to store, or `None` to remove the key.

        Returns the written ticket and any warnings.
        """

        requireText(key, "metadata key")

        with self.config.exclusiveLock():
            existing: TicketSet = self.__loadAllUnlocked()
            ticket: Ticket = existing.get(ticketId)

            if value is None:
                ticket.metadata.pop(key, None)
            else:
                ticket.metadata[key] = value

            return TicketResult(ticket=self.write(ticket), warnings=self.__danglingWarnings(ticket, existing))

    def setStatus(self, ticketId: str, status: str) -> Ticket:
        """
        Change a ticket's status and move its file in the same operation.

        The frontmatter is the truth and the directory is a projection of it, so neither is ever written without the other.

        The move is a write followed by a delete, which is two steps no matter how each one is performed, so the lock is what stops a reader from seeing both files at once and reporting a duplicate id.

        ticketId: The ticket to change.
        status: The new status.

        Returns the updated ticket.
        """

        # Reject an unrecognized status at the boundary rather than writing it and leaving `validate` to find it later.
        if status not in STATUSES:
            raise InvalidStatusError(f"Status '{status}' is not one of {', '.join(STATUSES)}.")

        with self.config.exclusiveLock():
            ticket: Ticket = self.__loadAllUnlocked().get(ticketId)
            previousPath: Optional[Path] = ticket.path

            ticket.status = status
            self.write(ticket)

            # Remove the old file only once the new one is on disk, and only when the move actually crossed directories.
            if previousPath is not None and previousPath != ticket.path and previousPath.exists():
                previousPath.unlink()

            return ticket

    def usedKeys(self) -> dict[str, list[str]]:
        """
        Map every key currently in use to the ids carrying it.

        This is what `key reject` needs in order to refuse loudly and name the tickets standing in the way.

        Returns keys mapped to their ticket ids.
        """

        used: dict[str, list[str]] = {}
        for ticket in self.loadAll().tickets.values():
            used.setdefault(ticket.key, []).append(ticket.id)

        return used

    # MARK: Private Functions

    def __loadAllUnlocked(self) -> TicketSet:
        """
        Load every ticket under the configured root without taking any lock.

        A file that cannot be read is collected rather than raised, so one broken ticket does not hide the rest and `validate` can report it.

        This exists because the lock refuses to downgrade from writing to reading, so a mutator already holding the write lock cannot call `loadAll`. Every caller of this is either inside a write lock or is `loadAll` itself.

        Returns the loaded `TicketSet`.
        """

        result: TicketSet = TicketSet()

        for path in self.discoverPaths():
            try:
                ticket: Ticket = parseTicket(path.read_text(encoding="utf-8"), path=path)
            except (TicketParseError, OSError, UnicodeDecodeError) as error:
                result.failures.append(LoadFailure(path=path, message=str(error)))
                continue

            # Keep the first file claiming an id and record the rest, so a merge collision is reported instead of silently overwriting.
            existing: Optional[Ticket] = result.tickets.get(ticket.id)
            if existing is not None:
                result.duplicates.append(DuplicateId(id=ticket.id, path=path, existingPath=existing.path or path))
                continue

            result.tickets[ticket.id] = ticket

        return result

    def __requireValidPriority(self, priority: int) -> None:
        """
        Reject a priority outside the configured band.

        priority: The priority to check.
        """

        if not 0 <= priority <= self.config.maxPriority:
            raise InvalidPriorityError(f"Priority {priority} is outside 0 through {self.config.maxPriority}. 0 is most urgent.")

    def __danglingWarnings(self, ticket: Ticket, existing: TicketSet) -> list[str]:
        """
        Report `requires` entries naming ids that do not exist.

        This is a warning rather than an error, so an agent writing a batch out of order completes the batch. `validate` reports the same condition as an error once the batch is done.

        ticket: The ticket whose dependencies are being checked.
        existing: The set loaded before the write.

        Returns one warning per unknown id.
        """

        # The ticket may legitimately require something written earlier in this same batch, so check against the set loaded before the write.
        return [f"Ticket '{ticket.id}' requires '{required}', which does not exist yet. Run 'docket validate' once the batch is complete." for required in ticket.requires if required != ticket.id and required not in existing]


# MARK: Functions


def _sortKey(ticket: Ticket) -> tuple[int, str, int]:
    """
    Build the ordering key for a ticket.

    The id's number is compared numerically rather than as text, so `CORE-2` precedes `CORE-10` instead of following it.

    ticket: The ticket to order.

    Returns a `(priority, key, number)` tuple.
    """

    key, number = parseId(ticket.id)

    return ticket.priority, key, number
