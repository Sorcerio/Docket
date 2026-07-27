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


def testRegisteredKeysExcludeTheProposedTable(config: Config) -> None:
    """
    The nested `proposed` sub-table lives inside `[keys]` and must not be read as a key itself.
    """

    assert config.registeredKeys == {
        "CORE": "tactical-sim core",
        "GEN": "map generation",
        "HEAD": "Godot frontend and seam",
    }
    assert "proposed" not in config.registeredKeys


def testProposedKeysAreReadWithTheirRationale(config: Config) -> None:
    """
    A proposal carries the description and rationale a human needs to decide on it.
    """

    proposed = config.proposedKeys["META"]

    assert proposed.key == "META"
    assert proposed.description == "campaign and progression"
    assert proposed.rationale == "the strategic layer is a distinct area"
    assert proposed.by == "agent"
    assert proposed.at == "2026-07-27"


def testKnownKeysCoverBothRegisteredAndProposed(config: Config) -> None:
    """
    A ticket may use a proposed key immediately, so both sides count as known.
    """

    assert config.isRegisteredKey("CORE")
    assert not config.isRegisteredKey("META")

    assert config.isProposedKey("META")
    assert config.isKnownKey("META")

    assert not config.isKnownKey("NOPE")


def testRequireKnownKeyPointsAtProposeKey(config: Config) -> None:
    """
    The error an agent sees names the valid keys and the recovery path.
    """

    with pytest.raises(UnknownKeyError) as excInfo:
        config.requireKnownKey("NOPE")

    message: str = str(excInfo.value)

    assert "propose_key" in message
    assert "CORE" in message


def testRequireKnownKeyRejectsAMalformedKeyFirst(config: Config) -> None:
    """
    A malformed key is a format error, not an unknown-key error.
    """

    with pytest.raises(InvalidKeyError):
        config.requireKnownKey("nope")


def testProposeKeyWritesToTheFile(config: Config) -> None:
    """
    A proposal persists immediately, so a batch can continue against the new key.
    """

    config.proposeKey("SIM", "simulation layer", "the tick loop is its own area", at="2026-07-27")

    reloaded: Config = loadConfig(config.path)

    assert reloaded.isProposedKey("SIM")
    assert reloaded.proposedKeys["SIM"].rationale == "the tick loop is its own area"
    assert not reloaded.isRegisteredKey("SIM")


def testProposeKeyDefaultsTheDate(config: Config) -> None:
    """
    Omitting the date records today rather than leaving the field blank.
    """

    proposed = config.proposeKey("SIM", "simulation layer", "needed")

    assert len(proposed.at) == 10
    assert proposed.by == "agent"


def testProposingAnExistingKeyFails(config: Config) -> None:
    """
    Re-proposing a key on either side is a mistake worth naming rather than a silent overwrite.
    """

    with pytest.raises(InvalidKeyError):
        config.proposeKey("CORE", "duplicate", "duplicate")

    with pytest.raises(InvalidKeyError):
        config.proposeKey("META", "duplicate", "duplicate")


def testApproveKeyMovesItAcross(config: Config) -> None:
    """
    Approval carries the description into the registered set and drops the proposal record.
    """

    config.approveKey("META")

    reloaded: Config = loadConfig(config.path)

    assert reloaded.registeredKeys["META"] == "campaign and progression"
    assert not reloaded.isProposedKey("META")


def testApprovingAnUnproposedKeyFails(config: Config) -> None:
    """
    There is nothing to promote for a key that was never proposed.
    """

    with pytest.raises(UnknownKeyError):
        config.approveKey("NOPE")


def testRejectKeyRemovesIt(config: Config) -> None:
    """
    Rejection drops the proposal entirely.
    """

    config.rejectKey("META")

    reloaded: Config = loadConfig(config.path)

    assert not reloaded.isKnownKey("META")


def testRejectKeyRefusesWhileTicketsUseIt(config: Config) -> None:
    """
    Rejecting a key in use would strand those tickets, so it fails and names them.
    """

    with pytest.raises(InvalidKeyError) as excInfo:
        config.rejectKey("META", usedBy=["META-2", "META-1"])

    message: str = str(excInfo.value)

    assert "META-1" in message
    assert "META-2" in message

    # The proposal survives the refusal.
    assert loadConfig(config.path).isProposedKey("META")


def testWritingPreservesCommentsAndKeyOrder(config: Config) -> None:
    """
    The file is hand-maintained, so a write must not strip the comments or alphabetize the keys around them.
    """

    config.proposeKey("SIM", "simulation layer", "needed", at="2026-07-27")

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
