"""
Store Tests

Cover discovery, loading, creation, mutation, and the status move.
"""

# MARK: Imports

from pathlib import Path

import pytest

from docket.core.config import Config
from docket.core.errors import ConflictingArgumentsError, EmptyValueError, InvalidPriorityError, InvalidStatusError, TicketNotFoundError, UnknownKeyError
from docket.core.store import Store, TicketResult, TicketSet
from docket.core.ticket import Ticket, parseTicket

# MARK: Functions


def writeRaw(config: Config, directory: str, filename: str, text: str) -> Path:
    """
    Drop a file straight into a status directory, bypassing the store.

    config: The configuration naming the ticket root.
    directory: Either the todo directory name or the done directory name.
    filename: The filename to write.
    text: The file contents.

    Returns the written path.
    """

    path: Path = config.rootPath / directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")

    return path


def makeText(ticketId: str, title: str = "T", status: str = "todo", priority: int = 2, requires: str = "[]") -> str:
    """
    Build minimal ticket file text.

    ticketId: The id to record.
    title: The title to record.
    status: The status to record.
    priority: The priority to record.
    requires: The dependency list, written as YAML flow style.

    Returns the file text.
    """

    return f"---\nid: {ticketId}\ntitle: {title}\nstatus: {status}\npriority: {priority}\nrequires: {requires}\n---\n\n# {title}\n"


def testLoadAllOnAnEmptyRepositoryIsEmpty(store: Store) -> None:
    """
    A freshly deployed repository has no tickets and that is not an error.
    """

    loaded: TicketSet = store.loadAll()

    assert len(loaded) == 0
    assert loaded.failures == []


def testLoadAllReadsBothStatusDirectories(store: Store, config: Config) -> None:
    """
    Discovery spans todo and done, since both hold real tickets.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))
    writeRaw(config, "done", "CORE-2_b.md", makeText("CORE-2", status="done"))

    loaded: TicketSet = store.loadAll()

    assert sorted(loaded.ids()) == ["CORE-1", "CORE-2"]


def testLoadAllCollectsBrokenFilesInsteadOfRaising(store: Store, config: Config) -> None:
    """
    One unreadable file must not hide every other ticket, so failures are collected for `validate` to report.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))
    writeRaw(config, "todo", "README.md", "# Just a readme, no frontmatter.\n")

    loaded: TicketSet = store.loadAll()

    assert loaded.ids() == ["CORE-1"]
    assert len(loaded.failures) == 1
    assert loaded.failures[0].path.name == "README.md"


def testLoadAllRecordsDuplicateIds(store: Store, config: Config) -> None:
    """
    Two branches minting under one key collide, which must be reported rather than silently overwriting.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", title="First"))
    writeRaw(config, "todo", "CORE-1_b.md", makeText("CORE-1", title="Second"))

    loaded: TicketSet = store.loadAll()

    assert len(loaded.tickets) == 1
    assert len(loaded.duplicates) == 1
    assert loaded.duplicates[0].id == "CORE-1"


def testNonMarkdownFilesAreIgnored(store: Store, config: Config) -> None:
    """
    A stray file that is not markdown is not a ticket and is not a failure either.
    """

    writeRaw(config, "todo", "notes.txt", "not a ticket")

    loaded: TicketSet = store.loadAll()

    assert len(loaded) == 0
    assert loaded.failures == []


def testSortingComparesNumbersNumerically(store: Store, config: Config) -> None:
    """
    `CORE-2` must precede `CORE-10`, which a plain string sort would get backwards.
    """

    writeRaw(config, "todo", "CORE-2_b.md", makeText("CORE-2"))
    writeRaw(config, "todo", "CORE-10_c.md", makeText("CORE-10"))
    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))

    assert [ticket.id for ticket in store.loadAll()] == ["CORE-1", "CORE-2", "CORE-10"]


def testSortingPutsUrgentWorkFirst(store: Store, config: Config) -> None:
    """
    Priority leads the ordering, with 0 most urgent.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", priority=3))
    writeRaw(config, "todo", "GEN-1_b.md", makeText("GEN-1", priority=0))

    assert [ticket.id for ticket in store.loadAll()] == ["GEN-1", "CORE-1"]


def testFilteringCombinesEveryFilter(store: Store, config: Config) -> None:
    """
    Supplied filters narrow the result and omitted ones do not.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1", status="todo", priority=1))
    writeRaw(config, "todo", "CORE-2_b.md", makeText("CORE-2", status="wip", priority=1))
    writeRaw(config, "todo", "GEN-1_c.md", makeText("GEN-1", status="todo", priority=4))

    loaded: TicketSet = store.loadAll()

    assert [ticket.id for ticket in loaded.filtered()] == ["CORE-1", "CORE-2", "GEN-1"]
    assert [ticket.id for ticket in loaded.filtered(status="todo")] == ["CORE-1", "GEN-1"]
    assert [ticket.id for ticket in loaded.filtered(key="CORE")] == ["CORE-1", "CORE-2"]
    assert [ticket.id for ticket in loaded.filtered(priorityMax=1)] == ["CORE-1", "CORE-2"]
    assert [ticket.id for ticket in loaded.filtered(status="todo", priorityMax=1)] == ["CORE-1"]


def testGetRaisesForAnUnknownId(store: Store) -> None:
    """
    Looking up an id that is not present is an error rather than a silent `None`.
    """

    with pytest.raises(TicketNotFoundError):
        store.loadAll().get("CORE-99")


def testCreateAllocatesTheNextIdAndWritesTheFile(store: Store, config: Config) -> None:
    """
    Creation mints an id by scanning, writes to the todo directory, and derives the filename from the title.
    """

    result: TicketResult = store.create(key="CORE", title="Skirmish Setup", body="Goal: one battle.")

    assert result.ticket.id == "CORE-1"
    assert result.ticket.status == "todo"
    assert result.ticket.priority == config.defaultPriority

    path: Path = config.todoPath / "CORE-1_skirmishSetup.md"
    assert path.is_file()
    assert "# Skirmish Setup" in path.read_text(encoding="utf-8")


def testCreateContinuesNumberingFromExistingTickets(store: Store, config: Config) -> None:
    """
    The next number comes from scanning, with no counter file to desynchronize.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))
    writeRaw(config, "done", "CORE-7_b.md", makeText("CORE-7", status="done"))

    assert store.create(key="CORE", title="Next").ticket.id == "CORE-8"


def testCreateUnderAnUnknownKeyFails(store: Store) -> None:
    """
    An unregistered key is refused so a typo cannot spawn an orphan group.
    """

    with pytest.raises(UnknownKeyError):
        store.create(key="NOPE", title="Orphan")


def testCreateWithADanglingDependencyWarnsButWrites(store: Store) -> None:
    """
    An agent writing a batch out of order is never stranded, so a missing dependency warns rather than raising.
    """

    result: TicketResult = store.create(key="CORE", title="Second", requires=["CORE-99"])

    assert result.ticket.path is not None
    assert len(result.warnings) == 1
    assert "CORE-99" in result.warnings[0]
    assert "docket validate" in result.warnings[0]


def testCreateWithASatisfiedDependencyDoesNotWarn(store: Store, config: Config) -> None:
    """
    A dependency that already exists is not a warning.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))

    assert store.create(key="CORE", title="Second", requires=["CORE-1"]).warnings == []


def testCreateRejectsAPriorityOutsideTheBand(store: Store) -> None:
    """
    A priority above the ceiling is a real input error, so it is refused at the boundary.
    """

    with pytest.raises(InvalidPriorityError):
        store.create(key="CORE", title="Too low", priority=99)

    with pytest.raises(InvalidPriorityError):
        store.create(key="CORE", title="Negative", priority=-1)


def testUpdateChangesFieldsWithoutRenamingTheFile(store: Store) -> None:
    """
    Retitling must not rename the file, since that would break every prose cross-reference pointing at it.
    """

    created: Ticket = store.create(key="CORE", title="Original Title").ticket
    originalPath: Path = created.path

    updated: Ticket = store.update("CORE-1", title="Completely Different").ticket

    assert updated.title == "Completely Different"
    assert updated.path == originalPath
    assert originalPath.name == "CORE-1_originalTitle.md"

    # The new title is on disk even though the filename did not follow it.
    assert parseTicket(originalPath.read_text(encoding="utf-8")).title == "Completely Different"


def testUpdateChangesPriorityAndRequires(store: Store, config: Config) -> None:
    """
    Priority and dependencies are both mutable through the tool, so an agent never has to hand-edit.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))
    store.create(key="CORE", title="Second")

    updated: Ticket = store.update("CORE-2", priority=0, requires=["CORE-1"]).ticket

    assert updated.priority == 0
    assert updated.requires == ["CORE-1"]


def testUpdateLeavesOmittedFieldsAlone(store: Store) -> None:
    """
    Only the fields supplied are touched, so a caller changing one thing cannot blank another.
    """

    store.create(key="CORE", title="Original", requires=[], priority=1)

    updated: Ticket = store.update("CORE-1", priority=0).ticket

    assert updated.title == "Original"
    assert updated.priority == 0


def testUpdateDoesNotChangeStatus(store: Store) -> None:
    """
    Status belongs to `setStatus`, because changing it moves the file.
    """

    store.create(key="CORE", title="Original")

    assert store.update("CORE-1", title="Renamed").ticket.status == "todo"


def testUpdateAddsToTheExistingRequires(store: Store, config: Config) -> None:
    """
    Adding appends without disturbing what is already there, which is the whole reason it exists.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))
    writeRaw(config, "todo", "CORE-2_b.md", makeText("CORE-2"))
    store.create(key="CORE", title="Third", requires=["CORE-1"])

    updated: Ticket = store.update("CORE-3", requiresAdd=["CORE-2"]).ticket

    assert updated.requires == ["CORE-1", "CORE-2"]


def testUpdateDoesNotAddAnIdAlreadyRequired(store: Store, config: Config) -> None:
    """
    An id already in the list is left where it is, so adding twice cannot duplicate an edge.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))
    writeRaw(config, "todo", "CORE-2_b.md", makeText("CORE-2"))
    store.create(key="CORE", title="Third", requires=["CORE-1", "CORE-2"])

    updated: Ticket = store.update("CORE-3", requiresAdd=["CORE-1"]).ticket

    assert updated.requires == ["CORE-1", "CORE-2"]


def testUpdateAddWarnsAboutADanglingId(store: Store) -> None:
    """
    An added id naming nothing warns exactly as a created one does, since the same check runs over the final list.
    """

    store.create(key="CORE", title="First")

    result: TicketResult = store.update("CORE-1", requiresAdd=["GEN-9"])

    assert result.ticket.requires == ["GEN-9"]
    assert len(result.warnings) == 1
    assert "GEN-9" in result.warnings[0]


def testUpdateRemovesFromTheExistingRequires(store: Store, config: Config) -> None:
    """
    Removing drops only what was named, leaving the rest of the list in its original order.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))
    writeRaw(config, "todo", "CORE-2_b.md", makeText("CORE-2"))
    store.create(key="CORE", title="Third", requires=["CORE-1", "CORE-2"])

    updated: Ticket = store.update("CORE-3", requiresRemove=["CORE-1"]).ticket

    assert updated.requires == ["CORE-2"]


def testUpdateRemovingAnAbsentIdIsANoOp(store: Store, config: Config) -> None:
    """
    Removing something that is not there leaves the list alone rather than failing, so removal is idempotent.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))
    store.create(key="CORE", title="Second", requires=["CORE-1"])

    result: TicketResult = store.update("CORE-2", requiresRemove=["GEN-4"])

    assert result.ticket.requires == ["CORE-1"]
    assert result.warnings == []


def testUpdateRemovingEverythingLeavesAnEmptyList(store: Store, config: Config) -> None:
    """
    Removing the last entry is allowed, landing where a replacement with an empty list would.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))
    store.create(key="CORE", title="Second", requires=["CORE-1"])

    assert store.update("CORE-2", requiresRemove=["CORE-1"]).ticket.requires == []


def testUpdateAppliesRemovalBeforeAddition(store: Store, config: Config) -> None:
    """
    Removal runs first, so naming one id in both ends with it present rather than gone.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))
    writeRaw(config, "todo", "CORE-2_b.md", makeText("CORE-2"))
    store.create(key="CORE", title="Third", requires=["CORE-1", "CORE-2"])

    updated: Ticket = store.update("CORE-3", requiresAdd=["CORE-1"], requiresRemove=["CORE-1", "CORE-2"]).ticket

    assert updated.requires == ["CORE-1"]


def testUpdateRefusesReplacingAndEditingAtOnce(store: Store) -> None:
    """
    A replacement and an edit in one call name no order the caller actually asked for.
    """

    store.create(key="CORE", title="First")

    with pytest.raises(ConflictingArgumentsError):
        store.update("CORE-1", requires=["GEN-1"], requiresAdd=["GEN-2"])

    with pytest.raises(ConflictingArgumentsError):
        store.update("CORE-1", requires=["GEN-1"], requiresRemove=["GEN-2"])


def testUpdateRejectsAnUnknownId(store: Store) -> None:
    """
    Updating a ticket that does not exist is an error.
    """

    with pytest.raises(TicketNotFoundError):
        store.update("CORE-99", title="Ghost")


def testSetMetadataAddsAKey(store: Store) -> None:
    """
    Setting a key that is not present yet adds it without disturbing anything else.
    """

    store.create(key="CORE", title="Skirmish Setup")

    result: TicketResult = store.setMetadata("CORE-1", "video", "2026-01-devlog")

    assert result.ticket.metadata == {"video": "2026-01-devlog"}


def testSetMetadataOnlyTouchesTheNamedKey(store: Store) -> None:
    """
    One consumer's key survives another consumer setting its own, since two skills may attach data to the same ticket.
    """

    store.create(key="CORE", title="Skirmish Setup")
    store.setMetadata("CORE-1", "video", "2026-01-devlog")

    result: TicketResult = store.setMetadata("CORE-1", "reviewed", True)

    assert result.ticket.metadata == {"video": "2026-01-devlog", "reviewed": True}


def testSetMetadataWithNoneValueRemovesTheKey(store: Store) -> None:
    """
    A `None` value clears the entry rather than storing a null placeholder.
    """

    store.create(key="CORE", title="Skirmish Setup")
    store.setMetadata("CORE-1", "video", "2026-01-devlog")

    result: TicketResult = store.setMetadata("CORE-1", "video", None)

    assert result.ticket.metadata == {}


def testSetMetadataRejectsAnEmptyKey(store: Store) -> None:
    """
    An empty key would be unreadable in the frontmatter, so it is refused at the boundary.
    """

    store.create(key="CORE", title="Skirmish Setup")

    with pytest.raises(EmptyValueError):
        store.setMetadata("CORE-1", "  ", "value")


def testSetMetadataRejectsAnUnknownId(store: Store) -> None:
    """
    Setting metadata on a ticket that does not exist is an error.
    """

    with pytest.raises(TicketNotFoundError):
        store.setMetadata("CORE-99", "video", "x")


def testSetMetadataPersistsAcrossALoad(store: Store) -> None:
    """
    The written value survives a fresh load, not just the in-memory ticket returned from the call.
    """

    store.create(key="CORE", title="Skirmish Setup")
    store.setMetadata("CORE-1", "video", "2026-01-devlog")

    assert store.load("CORE-1").metadata == {"video": "2026-01-devlog"}


def testSetStatusToDoneMovesTheFile(store: Store, config: Config) -> None:
    """
    The frontmatter and the directory are written together, never one without the other.
    """

    created: Ticket = store.create(key="CORE", title="Skirmish Setup").ticket
    todoPath: Path = created.path

    moved: Ticket = store.setStatus("CORE-1", "done")

    assert moved.status == "done"
    assert not todoPath.exists()
    assert moved.path == config.donePath / "CORE-1_skirmishSetup.md"
    assert parseTicket(moved.path.read_text(encoding="utf-8")).status == "done"


def testSetStatusToWipStaysInTodo(store: Store, config: Config) -> None:
    """
    Only `done` moves a file, so `wip` lives alongside `todo` exactly as the source repository did it.
    """

    store.create(key="CORE", title="Skirmish Setup")

    moved: Ticket = store.setStatus("CORE-1", "wip")

    assert moved.status == "wip"
    assert moved.path == config.todoPath / "CORE-1_skirmishSetup.md"


def testSetStatusBackToTodoMovesTheFileBack(store: Store, config: Config) -> None:
    """
    The move is symmetric, so reopening a finished ticket returns it to the todo directory.
    """

    store.create(key="CORE", title="Skirmish Setup")
    store.setStatus("CORE-1", "done")

    reopened: Ticket = store.setStatus("CORE-1", "todo")

    assert reopened.path == config.todoPath / "CORE-1_skirmishSetup.md"
    assert not (config.donePath / "CORE-1_skirmishSetup.md").exists()


def testSetStatusToTheSameStatusIsANoOp(store: Store) -> None:
    """
    Re-setting the current status succeeds rather than failing, and leaves the file in place.
    """

    created: Ticket = store.create(key="CORE", title="Skirmish Setup").ticket

    unchanged: Ticket = store.setStatus("CORE-1", "todo")

    assert unchanged.path == created.path
    assert unchanged.path.exists()


def testSetStatusRejectsAnUnknownStatus(store: Store) -> None:
    """
    The vocabulary is fixed, so an unrecognized status is refused rather than written.
    """

    store.create(key="CORE", title="Skirmish Setup")

    with pytest.raises(InvalidStatusError):
        store.setStatus("CORE-1", "blocked")


def testWritePreservesUnknownFrontmatterFields(store: Store, config: Config) -> None:
    """
    A consumer repository's own fields survive a status move, since the move rewrites the file.
    """

    writeRaw(
        config,
        "todo",
        "CORE-1_a.md",
        "---\nid: CORE-1\ntitle: T\nstatus: todo\npriority: 2\nrequires: []\nowner: brody\n---\n\n# T\n",
    )

    moved: Ticket = store.setStatus("CORE-1", "done")

    assert "owner: brody" in moved.path.read_text(encoding="utf-8")


def testUsedKeysMapsKeysToTheirTickets(store: Store, config: Config) -> None:
    """
    Rejecting a key needs the ids standing in the way so it can name them.
    """

    writeRaw(config, "todo", "CORE-1_a.md", makeText("CORE-1"))
    writeRaw(config, "todo", "META-1_b.md", makeText("META-1"))
    writeRaw(config, "done", "META-2_c.md", makeText("META-2", status="done"))

    used: dict[str, list[str]] = store.usedKeys()

    assert used["CORE"] == ["CORE-1"]
    assert sorted(used["META"]) == ["META-1", "META-2"]
    assert "GEN" not in used


def testFilesAreWrittenWithLfNewlines(store: Store) -> None:
    """
    Writing LF explicitly keeps a Windows checkout from churning every touched file.
    """

    created: Ticket = store.create(key="CORE", title="Skirmish Setup").ticket

    assert b"\r\n" not in created.path.read_bytes()
