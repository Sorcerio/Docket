"""
Docket Config

Reading and writing `.docket.toml`, including the key registry and its proposal flow.
"""

# MARK: Imports

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.items import Table

from docket.core.errors import ConfigError, ConfigNotFoundError, InvalidKeyError, UnknownKeyError
from docket.core.fields import readInt, readString
from docket.core.ids import requireValidKey

# MARK: Constants

# The filename looked for when walking up from a starting directory.
CONFIG_FILENAME: str = ".docket.toml"

# The table holding registered keys, and the sub-table inside it holding proposed ones.
KEYS_TABLE: str = "keys"
PROPOSED_TABLE: str = "proposed"

# Field defaults, applied when a configuration omits an optional field.
DEFAULT_ROOT: str = "docs/tickets"
DEFAULT_TODO_DIR: str = "todo"
DEFAULT_DONE_DIR: str = "done"
DEFAULT_PRIORITY: int = 2
DEFAULT_MAX_PRIORITY: int = 4

# MARK: Classes


@dataclass(frozen=True)
class ProposedKey:
    """
    A key an agent proposed through `propose_key`, awaiting human approval.
    """

    # MARK: Properties

    key: str
    description: str
    rationale: str
    by: str
    at: str


class Config:
    """
    A loaded `.docket.toml`, backed by the `tomlkit` document it was parsed from.

    The document is retained rather than discarded because writes must preserve the comments, spacing, and key order a human wrote around their key descriptions.
    """

    # MARK: Initializer

    def __init__(self, path: Path, document: TOMLDocument) -> None:
        """
        Wrap a parsed document.

        path: The path the document was read from, and the path `save` writes back to.
        document: The parsed `tomlkit` document, retained for round-tripping.
        """

        self.path: Path = path
        self.document: TOMLDocument = document

        # Name the file in field errors, since a user may have several repositories open.
        source: str = f"Configuration {path}"

        # Read the scalar fields once, since they are plain values with no round-trip concerns.
        self.root: str = readString(document, "root", ConfigError, source, DEFAULT_ROOT)
        self.todoDir: str = readString(document, "todoDir", ConfigError, source, DEFAULT_TODO_DIR)
        self.doneDir: str = readString(document, "doneDir", ConfigError, source, DEFAULT_DONE_DIR)
        self.defaultPriority: int = readInt(document, "defaultPriority", ConfigError, source, DEFAULT_PRIORITY)
        self.maxPriority: int = readInt(document, "maxPriority", ConfigError, source, DEFAULT_MAX_PRIORITY)

        # A default outside the allowed band would make every created ticket invalid, so catch it at load.
        if not 0 <= self.defaultPriority <= self.maxPriority:
            raise ConfigError(f"defaultPriority {self.defaultPriority} is outside 0 through maxPriority {self.maxPriority} in {self.path}.")

    # MARK: Properties

    @property
    def repoRoot(self) -> Path:
        """
        The directory holding the configuration file, which is the repository root.
        """

        return self.path.parent

    @property
    def rootPath(self) -> Path:
        """
        The absolute path of the ticket root directory.
        """

        return self.repoRoot / self.root

    @property
    def todoPath(self) -> Path:
        """
        The absolute path of the directory holding `todo` and `wip` tickets.
        """

        return self.rootPath / self.todoDir

    @property
    def donePath(self) -> Path:
        """
        The absolute path of the directory holding `done` tickets.
        """

        return self.rootPath / self.doneDir

    @property
    def registeredKeys(self) -> dict[str, str]:
        """
        Approved keys mapped to their descriptions.
        """

        # Skip the nested `proposed` sub-table, which is safe to identify by name because a valid key is always uppercase.
        return {name: str(value) for name, value in self.__keysTable().items() if name != PROPOSED_TABLE}

    @property
    def proposedKeys(self) -> dict[str, ProposedKey]:
        """
        Keys awaiting approval, mapped to their proposal records.
        """

        proposed: dict[str, ProposedKey] = {}
        for name, value in self.__proposedTable().items():
            proposed[name] = ProposedKey(
                key=name,
                description=str(value.get("description", "")),
                rationale=str(value.get("rationale", "")),
                by=str(value.get("by", "")),
                at=str(value.get("at", "")),
            )

        return proposed

    # MARK: Private Functions

    def __keysTable(self) -> Table:
        """
        Return the `[keys]` table, creating it in the document when absent.

        Returns the table.
        """

        if KEYS_TABLE not in self.document:
            self.document[KEYS_TABLE] = tomlkit.table()

        table: Any = self.document[KEYS_TABLE]
        if not isinstance(table, Table):
            raise ConfigError(f"Section '[{KEYS_TABLE}]' in {self.path} must be a table.")

        return table

    def __proposedTable(self) -> Table:
        """
        Return the `[keys.proposed]` sub-table, creating it in the document when absent.

        Returns the sub-table.
        """

        keys: Table = self.__keysTable()
        if PROPOSED_TABLE not in keys:
            keys[PROPOSED_TABLE] = tomlkit.table()

        table: Any = keys[PROPOSED_TABLE]
        if not isinstance(table, Table):
            raise ConfigError(f"Section '[{KEYS_TABLE}.{PROPOSED_TABLE}]' in {self.path} must be a table.")

        return table

    # MARK: Functions

    def isRegisteredKey(self, key: str) -> bool:
        """
        Report whether a key has been approved.

        key: The key to test.

        Returns `True` when the key is registered.
        """

        return key in self.registeredKeys

    def isProposedKey(self, key: str) -> bool:
        """
        Report whether a key is awaiting approval.

        key: The key to test.

        Returns `True` when the key is proposed.
        """

        return key in self.proposedKeys

    def isKnownKey(self, key: str) -> bool:
        """
        Report whether a key may be used on a ticket, meaning it is registered or proposed.

        key: The key to test.

        Returns `True` when tickets may use the key.
        """

        return self.isRegisteredKey(key) or self.isProposedKey(key)

    def requireKnownKey(self, key: str) -> str:
        """
        Return the key unchanged, raising when it is not usable on a ticket.

        The message points at `propose_key`, since that is the recovery path an agent has.

        key: The key to check.

        Returns the same key.
        """

        requireValidKey(key)

        if not self.isKnownKey(key):
            known: str = ", ".join(sorted(self.registeredKeys) + sorted(self.proposedKeys)) or "none"
            raise UnknownKeyError(f"Key '{key}' is neither registered nor proposed. Known keys: {known}. Call propose_key to add a new one.")

        return key

    def proposeKey(self, key: str, description: str, rationale: str, by: str = "agent", at: Optional[str] = None) -> ProposedKey:
        """
        Add a key to the proposed section so tickets may use it immediately.

        key: The key to propose.
        description: What the key groups, shown alongside registered keys.
        rationale: Why the key is needed, which is what a human reads when deciding to approve.
        by: Who proposed it.
        at: The ISO date of the proposal, defaulting to today.

        Returns the recorded proposal.
        """

        requireValidKey(key)

        # A key that already exists on either side is not a proposal, it is a mistake worth naming.
        if self.isRegisteredKey(key):
            raise InvalidKeyError(f"Key '{key}' is already registered.")
        if self.isProposedKey(key):
            raise InvalidKeyError(f"Key '{key}' is already proposed.")

        # Record the proposal as an inline table so it reads as one line in the file.
        entry: Any = tomlkit.inline_table()
        entry["description"] = description
        entry["rationale"] = rationale
        entry["by"] = by
        entry["at"] = at if at is not None else datetime.date.today().isoformat()

        self.__proposedTable()[key] = entry
        self.save()

        return self.proposedKeys[key]

    def approveKey(self, key: str) -> None:
        """
        Promote a proposed key into the registered set, carrying its description across.

        key: The key to approve.
        """

        if not self.isProposedKey(key):
            raise UnknownKeyError(f"Key '{key}' is not proposed, so there is nothing to approve.")

        # Move the description up and drop the proposal record, since the rationale has served its purpose.
        description: str = self.proposedKeys[key].description
        del self.__proposedTable()[key]
        self.__keysTable()[key] = description

        self.save()

    def rejectKey(self, key: str, usedBy: Optional[list[str]] = None) -> None:
        """
        Remove a proposed key.

        Rejecting a key that tickets already carry would strand those tickets with an unknown key, so the caller passes the ids it found and this refuses loudly.

        key: The key to reject.
        usedBy: Ids of tickets currently carrying the key, if any.
        """

        if not self.isProposedKey(key):
            raise UnknownKeyError(f"Key '{key}' is not proposed, so there is nothing to reject.")

        # Refuse while tickets depend on the key, and name them so the user can act.
        if usedBy:
            raise InvalidKeyError(f"Key '{key}' cannot be rejected because {len(usedBy)} ticket(s) use it: {', '.join(sorted(usedBy))}.")

        del self.__proposedTable()[key]
        self.save()

    def save(self) -> None:
        """
        Write the document back to disk, preserving comments, spacing, and key order.
        """

        # Write LF newlines explicitly so a checkout on Windows does not churn the file.
        self.path.write_text(tomlkit.dumps(self.document), encoding="utf-8", newline="\n")


# MARK: Functions


def findConfigPath(startDir: Optional[Path] = None) -> Path:
    """
    Locate `.docket.toml` by walking up from a starting directory.

    The walk stops at the git root, so a parent repository's configuration is never picked up by a nested one.

    startDir: The directory to start from, defaulting to the current working directory.

    Returns the path to the configuration file.
    """

    current: Path = (startDir if startDir is not None else Path.cwd()).resolve()

    # Walk upward, checking each directory before deciding whether the walk may continue past it.
    searched: list[str] = []
    for directory in [current, *current.parents]:
        candidate: Path = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate

        searched.append(str(directory))

        # A `.git` entry marks the repository boundary. It may be a file rather than a directory in a worktree or submodule, so test existence rather than type.
        if (directory / ".git").exists():
            break

    raise ConfigNotFoundError(f"No {CONFIG_FILENAME} found. Searched: {', '.join(searched)}. Run 'docket deploy .' at the repository root to create one.")


def loadConfig(configPath: Path) -> Config:
    """
    Parse a configuration file.

    configPath: The path to read.

    Returns the loaded `Config`.
    """

    try:
        document: TOMLDocument = tomlkit.parse(configPath.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigError(f"Could not read {configPath}: {error}") from error
    except Exception as error:
        raise ConfigError(f"Could not parse {configPath}: {error}") from error

    return Config(path=configPath, document=document)


def discoverConfig(startDir: Optional[Path] = None) -> Config:
    """
    Find and load the configuration governing a directory.

    startDir: The directory to start the walk from, defaulting to the current working directory.

    Returns the loaded `Config`.
    """

    return loadConfig(findConfigPath(startDir))
