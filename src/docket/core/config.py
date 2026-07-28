"""
Docket Config

Reading and writing `.docket.toml`, including the key registry.
"""

# MARK: Imports

from pathlib import Path
from typing import Any, Optional

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.items import Comment, Table

from docket.core.errors import ConfigError, ConfigNotFoundError, InvalidKeyError, UnknownKeyError
from docket.core.fields import readInt, readString
from docket.core.ids import requireValidKey

# MARK: Constants

# The filename looked for when walking up from a starting directory.
CONFIG_FILENAME: str = ".docket.toml"

# The table holding registered keys.
KEYS_TABLE: str = "keys"

# Field defaults, applied when a configuration omits an optional field.
DEFAULT_ROOT: str = "docs/tickets"
DEFAULT_TODO_DIR: str = "todo"
DEFAULT_DONE_DIR: str = "done"
DEFAULT_PRIORITY: int = 2
DEFAULT_MAX_PRIORITY: int = 4

# MARK: Classes


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
        Registered keys mapped to their descriptions.
        """

        # Skip any nested sub-table, so a configuration left over from an older layout is ignored rather than read as a key.
        return {name: str(value) for name, value in self.__keysTable().items() if not isinstance(value, dict)}

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

    def __dropFromKeysTable(self, key: str) -> None:
        """
        Remove a key from `[keys]` along with the rationale comment sitting immediately above it, so the reasoning does not outlive what it explained.

        A comment a human wrote elsewhere in the table is untouched, since only the run directly above the key is considered part of it.
        The table is rebuilt rather than edited in place, because deleting a comment line from the document's body directly would leave `tomlkit`'s internal index pointing at the wrong entries.

        key: The key to drop.
        """

        body: list[Any] = self.__keysTable().value.body

        # Find the key's own entry, which is the anchor the comment run is measured back from.
        index: int = -1
        for position, (name, _) in enumerate(body):
            if name is not None and name.key == key:
                index = position
                break

        if index < 0:
            return

        # Walk backwards over the comment lines directly above it, stopping at the first entry that is anything else.
        start: int = index
        while start > 0:
            name, item = body[start - 1]
            if name is not None or not isinstance(item, Comment):
                break

            start -= 1

        # Copy everything else across in order, so the surviving keys keep their positions and their own comments.
        rebuilt: Table = tomlkit.table()
        for position, (name, item) in enumerate(body):
            if start <= position <= index:
                continue

            if name is None:
                rebuilt.add(item)
                continue

            rebuilt.add(name, item)

        self.document[KEYS_TABLE] = rebuilt

    # MARK: Functions

    def isRegisteredKey(self, key: str) -> bool:
        """
        Report whether a key has been approved.

        key: The key to test.

        Returns `True` when the key is registered.
        """

        return key in self.registeredKeys

    def requireKnownKey(self, key: str) -> str:
        """
        Return the key unchanged, raising when it is not usable on a ticket.

        The message points at `add_key`, since that is the recovery path an agent has.

        key: The key to check.

        Returns the same key.
        """

        requireValidKey(key)

        if not self.isRegisteredKey(key):
            known: str = ", ".join(sorted(self.registeredKeys)) or "none"
            raise UnknownKeyError(f"Key '{key}' is not registered. Known keys: {known}. Ask the user whether to add a new one, then call add_key.")

        return key

    def addKey(self, key: str, description: str, rationale: Optional[str] = None) -> str:
        """
        Register a key so tickets may be created under it.

        key: The key to register.
        description: What the key groups, shown alongside the other keys.
        rationale: Why the key was added, written as a comment above it so the reasoning survives in the file.

        Returns the same key.
        """

        requireValidKey(key)

        # A key that already exists is not an addition, it is a mistake worth naming.
        if self.isRegisteredKey(key):
            raise InvalidKeyError(f"Key '{key}' is already registered.")

        table: Table = self.__keysTable()

        # Write the rationale first, so it lands on the line above the key rather than beside it.
        if rationale:
            table.add(tomlkit.comment(rationale))

        table[key] = description
        self.save()

        return key

    def removeKey(self, key: str, usedBy: Optional[list[str]] = None) -> None:
        """
        Remove a registered key.

        Removing a key that tickets already carry would strand those tickets with an unknown key, so the caller passes the ids it found and this refuses loudly.

        key: The key to remove.
        usedBy: Ids of tickets currently carrying the key, if any.
        """

        if not self.isRegisteredKey(key):
            raise UnknownKeyError(f"Key '{key}' is not registered, so there is nothing to remove.")

        # Refuse while tickets depend on the key, and name them so the user can act.
        if usedBy:
            raise InvalidKeyError(f"Key '{key}' cannot be removed because {len(usedBy)} ticket(s) use it: {', '.join(sorted(usedBy))}.")

        # Take the rationale comment with it, since a comment explaining a key that no longer exists only misleads.
        self.__dropFromKeysTable(key)

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
