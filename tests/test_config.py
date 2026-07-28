"""
Config Tests

Cover discovery, field reading, the key registry, and comment-preserving round-trips.
"""

# MARK: Imports

from pathlib import Path

import pytest

from docket.core.config import Config, discoverConfig, findConfigPath, loadConfig
from docket.core.errors import ConfigError, ConfigNotFoundError, InvalidKeyError, UnknownKeyError

# MARK: Functions


def testFieldsAreReadFromTheFile(config: Config) -> None:
    """
    Every scalar field is read, and the derived paths hang off the configuration's own location.
    """

    assert config.root == "docs/tickets"
    assert config.todoDir == "todo"
    assert config.doneDir == "done"
    assert config.defaultPriority == 2
    assert config.maxPriority == 4

    assert config.rootPath == config.repoRoot / "docs" / "tickets"
    assert config.todoPath == config.rootPath / "todo"
    assert config.donePath == config.rootPath / "done"


def testFieldsAreNarrowedToExactBuiltinTypes(config: Config) -> None:
    """
    `tomlkit` returns `str` and `int` subclasses, and `pyyaml` dispatches its representers on exact type.

    A subclass leaking out of configuration reaches ticket serialization and fails there instead of here, so the narrowing is asserted at the source.
    """

    assert type(config.root) is str
    assert type(config.defaultPriority) is int
    assert type(config.maxPriority) is int


def testMissingFieldsFallBackToDefaults(tmp_path: Path) -> None:
    """
    An almost empty configuration still loads, using the documented defaults.
    """

    configPath: Path = tmp_path / ".docket.toml"
    configPath.write_text("[keys]\nCORE = \"core\"\n", encoding="utf-8", newline="\n")

    config: Config = loadConfig(configPath)

    assert config.root == "docs/tickets"
    assert config.defaultPriority == 2
    assert config.maxPriority == 4


def testAWrongTypedFieldIsRejected(tmp_path: Path) -> None:
    """
    A field of the wrong type fails at load rather than surfacing later as a confusing error.
    """

    configPath: Path = tmp_path / ".docket.toml"
    configPath.write_text('root = 3\n', encoding="utf-8", newline="\n")

    with pytest.raises(ConfigError):
        loadConfig(configPath)


def testABooleanIsNotAcceptedAsAnInteger(tmp_path: Path) -> None:
    """
    `bool` subclasses `int` in Python, so `true` must be rejected explicitly rather than read as 1.
    """

    configPath: Path = tmp_path / ".docket.toml"
    configPath.write_text("maxPriority = true\n", encoding="utf-8", newline="\n")

    with pytest.raises(ConfigError):
        loadConfig(configPath)


def testADefaultPriorityAboveTheCeilingIsRejected(tmp_path: Path) -> None:
    """
    A default outside the allowed band would make every created ticket invalid, so it fails at load.
    """

    configPath: Path = tmp_path / ".docket.toml"
    configPath.write_text("defaultPriority = 9\nmaxPriority = 4\n", encoding="utf-8", newline="\n")

    with pytest.raises(ConfigError):
        loadConfig(configPath)


def testRegisteredKeysAreReadWithTheirDescriptions(config: Config) -> None:
    """
    Every scalar entry under `[keys]` is a key, and the comments between them are not.
    """

    assert config.registeredKeys == {
        "CORE": "tactical-sim core",
        "GEN": "map generation",
        "HEAD": "Godot frontend and seam",
        "META": "campaign and progression",
    }


def testANestedTableUnderKeysIsIgnored(tmp_path: Path) -> None:
    """
    A configuration left over from the older proposal layout still loads, with the stale sub-table read as nothing rather than as a key.
    """

    configPath: Path = tmp_path / ".docket.toml"
    configPath.write_text("[keys]\nCORE = \"core\"\n\n[keys.proposed]\nMETA = { description = \"old\" }\n", encoding="utf-8", newline="\n")

    config: Config = loadConfig(configPath)

    assert config.registeredKeys == {"CORE": "core"}
    assert not config.isRegisteredKey("META")


def testRequireKnownKeyPointsAtAddKey(config: Config) -> None:
    """
    The error an agent sees names the valid keys and the recovery path.
    """

    with pytest.raises(UnknownKeyError) as excInfo:
        config.requireKnownKey("NOPE")

    message: str = str(excInfo.value)

    assert "add_key" in message
    assert "CORE" in message


def testRequireKnownKeyRejectsAMalformedKeyFirst(config: Config) -> None:
    """
    A malformed key is a format error, not an unknown-key error.
    """

    with pytest.raises(InvalidKeyError):
        config.requireKnownKey("nope")


def testAddKeyWritesToTheFile(config: Config) -> None:
    """
    A new key persists immediately, so a batch can continue against it.
    """

    config.addKey("SIM", "simulation layer")

    reloaded: Config = loadConfig(config.path)

    assert reloaded.isRegisteredKey("SIM")
    assert reloaded.registeredKeys["SIM"] == "simulation layer"


def testAddKeyWritesTheRationaleAsACommentAboveIt(config: Config) -> None:
    """
    The rationale is reasoning for a human reader, so it lives on the line above the key rather than inside its value.
    """

    config.addKey("SIM", "simulation layer", rationale="the tick loop is its own area")

    text: str = config.path.read_text(encoding="utf-8")

    assert "# the tick loop is its own area\nSIM = \"simulation layer\"" in text

    # The comment is reasoning around the key, not part of it.
    assert loadConfig(config.path).registeredKeys["SIM"] == "simulation layer"


def testAddingAnExistingKeyFails(config: Config) -> None:
    """
    Re-adding a key is a mistake worth naming rather than a silent overwrite of its description.
    """

    with pytest.raises(InvalidKeyError):
        config.addKey("CORE", "duplicate")


def testAddingAMalformedKeyFails(config: Config) -> None:
    """
    The key form is checked before anything is written, so a typo cannot land in the file.
    """

    with pytest.raises(InvalidKeyError):
        config.addKey("sim", "simulation layer")


def testRemoveKeyTakesItsRationaleCommentWithIt(config: Config) -> None:
    """
    A comment explaining a key that no longer exists only misleads, so the run directly above the key goes too.
    """

    config.removeKey("META")

    text: str = config.path.read_text(encoding="utf-8")

    assert "META" not in text
    assert "The strategic layer is a distinct area" not in text

    # A comment belonging to a different key is left alone.
    assert "# The engine itself." in text
    assert loadConfig(config.path).registeredKeys["CORE"] == "tactical-sim core"


def testRemoveKeyRefusesWhileTicketsUseIt(config: Config) -> None:
    """
    Removing a key in use would strand those tickets, so it fails and names them.
    """

    with pytest.raises(InvalidKeyError) as excInfo:
        config.removeKey("META", usedBy=["META-2", "META-1"])

    message: str = str(excInfo.value)

    assert "META-1" in message
    assert "META-2" in message

    # The key survives the refusal.
    assert loadConfig(config.path).isRegisteredKey("META")


def testRemovingAnUnregisteredKeyFails(config: Config) -> None:
    """
    There is nothing to remove for a key that was never registered.
    """

    with pytest.raises(UnknownKeyError):
        config.removeKey("NOPE")


def testWritingPreservesCommentsAndKeyOrder(config: Config) -> None:
    """
    The file is hand-maintained, so a write must not strip the comments or alphabetize the keys around them.
    """

    config.addKey("SIM", "simulation layer")

    text: str = config.path.read_text(encoding="utf-8")

    assert "# Docket configuration for the test repository." in text
    assert "# The engine itself." in text

    # The original non-alphabetical order survives, which a dict-rebuilding writer would have destroyed.
    assert text.index("CORE =") < text.index("GEN =") < text.index("HEAD =")


def testFindConfigPathWalksUpFromASubdirectory(repoDir: Path) -> None:
    """
    A command run deep inside the repository still finds the configuration at the root.
    """

    deep: Path = repoDir / "docs" / "tickets" / "todo"

    assert findConfigPath(deep) == repoDir / ".docket.toml"


def testFindConfigPathStopsAtTheGitRoot(tmp_path: Path) -> None:
    """
    A nested repository must not pick up a parent repository's configuration.
    """

    # The outer directory has a configuration the inner repository must not see.
    (tmp_path / ".docket.toml").write_text("root = \"outer\"\n", encoding="utf-8", newline="\n")

    inner: Path = tmp_path / "inner"
    inner.mkdir()
    (inner / ".git").mkdir()

    with pytest.raises(ConfigNotFoundError):
        findConfigPath(inner)


def testFindConfigPathReportsWhereItLooked(tmp_path: Path) -> None:
    """
    The failure names the directories searched and the command that fixes it.
    """

    (tmp_path / ".git").mkdir()

    with pytest.raises(ConfigNotFoundError) as excInfo:
        findConfigPath(tmp_path)

    message: str = str(excInfo.value)

    assert str(tmp_path.resolve()) in message
    assert "docket deploy" in message


def testConfigInTheGitRootItselfIsFound(repoDir: Path) -> None:
    """
    The boundary check runs after the configuration check, so a configuration beside `.git` is still found.
    """

    assert discoverConfig(repoDir).repoRoot == repoDir.resolve()
