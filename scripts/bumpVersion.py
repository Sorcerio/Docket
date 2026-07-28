"""
Bump Version

Set the package version in the one file that holds it, then resync the lock file.
"""

# MARK: Imports

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

# MARK: Constants

# The program name used in help output and messages.
PROGRAM_NAME: str = "bumpVersion"

# The package this script bumps, named in its output so the line reads the same as the CLI's own `--version`.
PACKAGE_NAME: str = "docket"

# The single file holding the version literal, resolved from this script rather than from the working directory so the script runs from anywhere.
VERSION_FILE: Path = Path(__file__).resolve().parent.parent / "src" / "docket" / "__init__.py"

# The assignment to read and rewrite. The type annotation is optional in the pattern so the script survives its removal, and the captured group is the version itself.
VERSION_PATTERN: re.Pattern[str] = re.compile(r'^(__version__\s*(?::\s*str\s*)?=\s*")([^"]*)(")$', re.MULTILINE)

# A strict semantic version, three numeric parts with no prerelease or build suffix. A leading zero is rejected because the specification forbids it, and `0` alone is not a leading zero.
SEMVER_PATTERN: re.Pattern[str] = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

# The keywords accepted in place of an explicit version, in the order of the parts they increment.
BUMP_PARTS: tuple[str, ...] = ("major", "minor", "patch")

# Exit codes, distinguishing a bump that could not be made from a command that was called wrongly.
EXIT_OK: int = 0
EXIT_ERROR: int = 1
EXIT_USAGE: int = 2

# MARK: Functions


def parseVersion(text: str) -> tuple[int, int, int]:
    """
    Parse a semantic version string into its numeric parts.

    Only the three-part form is accepted. A prerelease or build suffix is rejected rather than tolerated, because incrementing one has no single correct answer and a wrong guess would be written to disk unnoticed.

    text: The version string, for example `0.1.1`.

    Returns the major, minor, and patch numbers.
    """

    match: Optional[re.Match[str]] = SEMVER_PATTERN.match(text.strip())

    if match is None:
        raise ValueError(f"'{text}' is not a semantic version. Expected three numbers separated by dots, for example 0.1.1.")

    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def formatVersion(parts: tuple[int, int, int]) -> str:
    """
    Render numeric version parts back into a string.

    parts: The major, minor, and patch numbers.

    Returns the version string.
    """

    return ".".join(str(part) for part in parts)


def bumpPart(parts: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    """
    Increment one part of a version, resetting everything less significant than it.

    parts: The major, minor, and patch numbers to start from.
    part: Which part to increment, one of `major`, `minor`, or `patch`.

    Returns the incremented parts.
    """

    if part not in BUMP_PARTS:
        raise ValueError(f"'{part}' is not a version part. Expected one of {', '.join(BUMP_PARTS)}.")

    # Increment the named part and zero the ones below it, since a new minor starts at patch zero rather than carrying the old one forward.
    index: int = BUMP_PARTS.index(part)
    bumped: list[int] = list(parts)
    bumped[index] += 1
    for lower in range(index + 1, len(bumped)):
        bumped[lower] = 0

    return (bumped[0], bumped[1], bumped[2])


def resolveTarget(current: str, request: str) -> str:
    """
    Work out the version to write from what the caller asked for.

    Both accepted forms end here, so an explicit version is validated by the same parser that does the arithmetic for a keyword.

    current: The version currently on disk.
    request: Either an explicit version or one of the `BUMP_PARTS` keywords.

    Returns the version to write.
    """

    currentParts: tuple[int, int, int] = parseVersion(current)

    # A keyword is arithmetic on the current version, and anything else is read as an explicit version.
    if request in BUMP_PARTS:
        targetParts: tuple[int, int, int] = bumpPart(currentParts, request)
    else:
        targetParts = parseVersion(request)

    # Refuse a version that does not move forward, since writing one is almost always a typo and the mistake would otherwise reach a published artifact.
    if targetParts <= currentParts:
        raise ValueError(f"{formatVersion(targetParts)} does not come after the current {current}.")

    return formatVersion(targetParts)


def readVersion(path: Path) -> str:
    """
    Read the version literal out of the file that holds it.

    path: The file to read.

    Returns the version string as written.
    """

    try:
        text: str = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"Could not read '{path}': {error.strerror or error}.") from error

    match: Optional[re.Match[str]] = VERSION_PATTERN.search(text)

    if match is None:
        raise ValueError(f"No __version__ assignment found in '{path}'.")

    return match.group(2)


def writeVersion(path: Path, version: str) -> None:
    """
    Replace the version literal in the file that holds it, leaving the rest of the file untouched.

    path: The file to rewrite.
    version: The version to write.
    """

    text: str = path.read_text(encoding="utf-8")

    # Substitute only the captured version, so the annotation, quoting, and surrounding lines survive exactly as they were. The replacement is passed as a function because a version is not a valid backreference template.
    updated: str = VERSION_PATTERN.sub(lambda match: f"{match.group(1)}{version}{match.group(3)}", text, count=1)

    try:
        # Write LF explicitly so the file does not churn on a Windows checkout.
        path.write_text(updated, encoding="utf-8", newline="\n")
    except OSError as error:
        raise ValueError(f"Could not write '{path}': {error.strerror or error}.") from error


def runLock() -> bool:
    """
    Resync the lock file so its record of this package matches what was just written.

    A failure here is reported rather than raised, because the version is already on disk by this point and undoing it would be a larger surprise than an unsynced lock file.

    Returns whether the lock file was resynced.
    """

    try:
        completed: subprocess.CompletedProcess[bytes] = subprocess.run(["uv", "lock"], capture_output=True)
    except FileNotFoundError:
        print(f"{PROGRAM_NAME}: uv is not on PATH, so the lock file was left alone. Run 'uv lock' yourself.", file=sys.stderr)

        return False

    if completed.returncode != 0:
        details: str = completed.stderr.decode(errors="replace").strip()
        print(f"{PROGRAM_NAME}: 'uv lock' failed, so the lock file may disagree with the new version. Run it yourself.\n{details}", file=sys.stderr)

        return False

    return True


def buildParser() -> argparse.ArgumentParser:
    """
    Build the argument parser.

    Returns the configured `argparse.ArgumentParser`.
    """

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description=f"Set the {PACKAGE_NAME} version in the one file that holds it, then resync the lock file.",
    )
    parser.add_argument("version", help=f"An explicit version such as 0.2.0, or one of {', '.join(BUMP_PARTS)} to increment that part of the current one.")
    parser.add_argument("--dry-run", action="store_true", dest="dryRun", help="Report what would change without writing anything or touching the lock file.")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """
    Run the script.

    argv: Arguments to parse, defaulting to the process arguments.

    Returns the exit code.
    """

    arguments: argparse.Namespace = buildParser().parse_args(argv)

    # Every rejection reaches here as a `ValueError`, so a bad version and an unreadable file are reported the same way rather than as a traceback.
    try:
        current: str = readVersion(VERSION_FILE)
        target: str = resolveTarget(current, arguments.version)
    except ValueError as error:
        print(f"{PROGRAM_NAME}: {error}", file=sys.stderr)

        return EXIT_USAGE

    # A dry run stops before the write, so the lock file is not resynced against a version that was never set.
    if arguments.dryRun:
        print(f"{PACKAGE_NAME} {current} -> {target} (dry run, nothing written)")

        return EXIT_OK

    try:
        writeVersion(VERSION_FILE, target)
    except ValueError as error:
        print(f"{PROGRAM_NAME}: {error}", file=sys.stderr)

        return EXIT_ERROR

    print(f"{PACKAGE_NAME} {current} -> {target}")

    runLock()

    return EXIT_OK


# MARK: Entry

if __name__ == "__main__":
    raise SystemExit(main())
