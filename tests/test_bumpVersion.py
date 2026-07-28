"""
Bump Version Tests

Cover the semantic version parsing and the rewrite the bump script performs.

The script is not part of the installed package, so it is loaded from its path rather than imported by name.
"""

# MARK: Imports

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

# MARK: Constants

# The script under test, resolved from this file so the tests run from any working directory.
SCRIPT_PATH: Path = Path(__file__).resolve().parent.parent / "scripts" / "bumpVersion.py"

# A stand-in for the file holding the version literal, written exactly as the real one is. The assignment carries no type annotation, because hatchling's default version regex does not allow one.
SAMPLE_MODULE: str = '''\
"""
Docket

A per-repo ticketing system.
"""

# MARK: Constants

__version__ = "0.1.1"
'''

# The same assignment with a type annotation, which the script still reads so it stays liftable into a project that annotates it.
ANNOTATED_MODULE: str = SAMPLE_MODULE.replace("__version__ =", "__version__: str =")

# MARK: Fixtures


@pytest.fixture(scope="module")
def bumpVersion() -> ModuleType:
    """
    Load the bump script as a module.

    Returns the loaded module.
    """

    spec = importlib.util.spec_from_file_location("bumpVersion", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None

    module: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


@pytest.fixture
def versionFile(tmp_path: Path) -> Path:
    """
    Write a throwaway module carrying a version literal.

    tmp_path: The pytest-provided temporary directory.

    Returns the path written.
    """

    path: Path = tmp_path / "__init__.py"
    path.write_text(SAMPLE_MODULE, encoding="utf-8", newline="\n")

    return path


# MARK: Functions


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0.1.1", (0, 1, 1)),
        ("1.0.0", (1, 0, 0)),
        ("10.20.30", (10, 20, 30)),
        ("0.0.0", (0, 0, 0)),
        ("  0.2.0  ", (0, 2, 0)),
    ],
)
def testParseVersionAcceptsSemanticVersions(bumpVersion: ModuleType, text: str, expected: tuple[int, int, int]) -> None:
    """
    A well-formed version parses into its three numeric parts.
    """

    assert bumpVersion.parseVersion(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "1",
        "0.1",
        "0.1.1.1",
        "v0.1.1",
        "0.1.x",
        "0.1.-1",
        "01.1.1",
        "0.1.1-rc1",
        "0.1.1+build",
    ],
)
def testParseVersionRejectsEverythingElse(bumpVersion: ModuleType, text: str) -> None:
    """
    Anything that is not three plain numbers is refused rather than written to disk.

    A prerelease or build suffix is rejected with the rest, because incrementing one has no single correct answer.
    """

    with pytest.raises(ValueError):
        bumpVersion.parseVersion(text)


@pytest.mark.parametrize(
    "part,expected",
    [
        ("patch", "0.1.2"),
        ("minor", "0.2.0"),
        ("major", "1.0.0"),
    ],
)
def testBumpPartResetsLowerParts(bumpVersion: ModuleType, part: str, expected: str) -> None:
    """
    Incrementing a part zeroes everything below it, so a new minor starts at patch zero.
    """

    assert bumpVersion.formatVersion(bumpVersion.bumpPart((0, 1, 1), part)) == expected


def testBumpPartRejectsAnUnknownPart(bumpVersion: ModuleType) -> None:
    """
    Only the three named parts may be incremented.
    """

    with pytest.raises(ValueError):
        bumpVersion.bumpPart((0, 1, 1), "epoch")


def testResolveTargetAcceptsBothForms(bumpVersion: ModuleType) -> None:
    """
    An explicit version and a keyword reach the same result through the same parser.
    """

    assert bumpVersion.resolveTarget("0.1.1", "patch") == "0.1.2"
    assert bumpVersion.resolveTarget("0.1.1", "0.1.2") == "0.1.2"


@pytest.mark.parametrize("request_", ["0.1.1", "0.1.0", "0.0.9"])
def testResolveTargetRejectsAVersionThatDoesNotMoveForward(bumpVersion: ModuleType, request_: str) -> None:
    """
    Repeating or lowering the current version is refused, since it is almost always a typo.
    """

    with pytest.raises(ValueError):
        bumpVersion.resolveTarget("0.1.1", request_)


def testReadVersionFindsTheLiteral(bumpVersion: ModuleType, versionFile: Path) -> None:
    """
    The version is read out of the assignment in the module.
    """

    assert bumpVersion.readVersion(versionFile) == "0.1.1"


def testReadVersionAcceptsAnAnnotatedAssignment(bumpVersion: ModuleType, tmp_path: Path) -> None:
    """
    An annotated assignment is read too, so the script survives being copied into a project that writes one.
    """

    path: Path = tmp_path / "annotated.py"
    path.write_text(ANNOTATED_MODULE, encoding="utf-8", newline="\n")

    assert bumpVersion.readVersion(path) == "0.1.1"

    bumpVersion.writeVersion(path, "0.2.0")

    assert path.read_text(encoding="utf-8") == ANNOTATED_MODULE.replace("0.1.1", "0.2.0")


def testReadVersionRejectsAFileWithoutOne(bumpVersion: ModuleType, tmp_path: Path) -> None:
    """
    A file carrying no assignment is an error rather than a silent default.
    """

    path: Path = tmp_path / "empty.py"
    path.write_text("# nothing here\n", encoding="utf-8", newline="\n")

    with pytest.raises(ValueError):
        bumpVersion.readVersion(path)


def testWriteVersionLeavesTheRestOfTheFileIntact(bumpVersion: ModuleType, versionFile: Path) -> None:
    """
    Only the version changes, with the annotation, the docstring, and the section headers untouched.
    """

    bumpVersion.writeVersion(versionFile, "0.2.0")

    written: str = versionFile.read_text(encoding="utf-8")

    assert '__version__ = "0.2.0"' in written
    assert written == SAMPLE_MODULE.replace("0.1.1", "0.2.0")


def testMainDryRunWritesNothing(bumpVersion: ModuleType, versionFile: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A dry run reports the change and leaves both the file and the lock file alone.
    """

    monkeypatch.setattr(bumpVersion, "VERSION_FILE", versionFile)

    # Fail loudly if the lock file is touched, since a dry run must stop before it.
    monkeypatch.setattr(bumpVersion, "runLock", lambda: pytest.fail("A dry run must not resync the lock file."))

    assert bumpVersion.main(["patch", "--dry-run"]) == bumpVersion.EXIT_OK
    assert "0.1.1 -> 0.1.2" in capsys.readouterr().out
    assert versionFile.read_text(encoding="utf-8") == SAMPLE_MODULE


def testMainWritesAndResyncsTheLock(bumpVersion: ModuleType, versionFile: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """
    A real run writes the new version and then resyncs the lock file.
    """

    monkeypatch.setattr(bumpVersion, "VERSION_FILE", versionFile)

    # Record the call rather than shelling out to uv, which would rewrite the repository's own lock file.
    calls: list[bool] = []

    def recordLock() -> bool:
        calls.append(True)

        return True

    monkeypatch.setattr(bumpVersion, "runLock", recordLock)

    assert bumpVersion.main(["0.2.0"]) == bumpVersion.EXIT_OK
    assert "0.1.1 -> 0.2.0" in capsys.readouterr().out
    assert bumpVersion.readVersion(versionFile) == "0.2.0"
    assert calls == [True]


def testMainRejectsABadVersionBeforeWriting(bumpVersion: ModuleType, versionFile: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    A malformed version is a usage error, and the file is left as it was.
    """

    monkeypatch.setattr(bumpVersion, "VERSION_FILE", versionFile)
    monkeypatch.setattr(bumpVersion, "runLock", lambda: pytest.fail("A rejected version must not resync the lock file."))

    assert bumpVersion.main(["0.2"]) == bumpVersion.EXIT_USAGE
    assert versionFile.read_text(encoding="utf-8") == SAMPLE_MODULE
