"""
Title Case Tests

The conversion itself, covering the two things that decide a word: its position and its existing shape.
"""

# MARK: Imports

import pytest

from docket.core.titles import MINOR_WORDS, isTitleCase, toTitleCase

# MARK: Functions


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("record demo gif", "Record Demo Gif"),
        ("Already Title Case", "Already Title Case"),
        ("one", "One"),
        ("HOST FLAG", "HOST FLAG"),
    ],
)
def testEveryMajorWordIsCapitalized(title: str, expected: str) -> None:
    """
    A word that is not minor, not positioned in the middle, and carries no case of its own is capitalized.
    """

    assert toTitleCase(title) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("key removal checks usage outside the lock", "Key Removal Checks Usage Outside the Lock"),
        ("Cannot Clear With Set Command", "Cannot Clear with Set Command"),
        ("Check if Ticket is Ready For Work", "Check if Ticket Is Ready for Work"),
    ],
)
def testAMinorWordInTheMiddleIsLowercased(title: str, expected: str) -> None:
    """
    A minor word is matched by its lowercase form, so one that arrived capitalized is corrected rather than left alone.
    """

    assert toTitleCase(title) == expected


@pytest.mark.parametrize("word", ["the", "and", "of", "with"])
def testAMinorWordIsStillCapitalizedAtEitherEnd(word: str) -> None:
    """
    The first and the last word of a title are always major, whichever word they happen to be.
    """

    capitalized: str = word[:1].upper() + word[1:]

    assert toTitleCase(f"{word} middle word {word}") == f"{capitalized} Middle Word {capitalized}"


@pytest.mark.parametrize(
    "title",
    [
        "Add to Requires in CLI",
        "Fix Character Encoding Issue in FEAT-5",
        "Record Demo GIF with VHS",
        "Set Up and Publish to PyPI",
        "Migrate to 2.x MCPServer API",
    ],
)
def testAWordCarryingItsOwnCaseOrADigitSurvives(title: str) -> None:
    """
    An acronym, a ticket id, and a version number are left exactly as written, which is the whole reason `textcase.title` is not used bare.
    """

    assert toTitleCase(title) == title


def testALowercaseAcronymIsNotRecognized() -> None:
    """
    An acronym typed in lowercase is indistinguishable from an ordinary word, so it is capitalized like one.

    This is a known limit of the rule rather than an oversight, and the fix is to type the acronym in caps.
    """

    assert toTitleCase("migrate to mcp") == "Migrate to Mcp"


def testSurroundingAndRepeatedWhitespaceCollapses() -> None:
    """
    The split that finds the words is what removes the whitespace between them, so a title cannot carry padding into the file.
    """

    assert toTitleCase("  spaced   out  title  ") == "Spaced Out Title"


def testConversionIsIdempotent() -> None:
    """
    Converting an already converted title changes nothing, which is what lets every write run it without drift.
    """

    once: str = toTitleCase("key removal checks usage outside the lock")

    assert toTitleCase(once) == once


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Already Title Case", True),
        ("Add to Requires in CLI", True),
        ("not title case", False),
        ("Trailing Space ", False),
    ],
)
def testIsTitleCaseAsksWhatToTitleCaseAnswers(title: str, expected: bool) -> None:
    """
    The asking half is defined by the converting half, so the two can never disagree about what is correct.
    """

    assert isTitleCase(title) is expected


def testMinorWordsAreAllLowercase() -> None:
    """
    The list is matched against lowercased words, so an entry carrying a capital could never match.
    """

    assert all(word == word.lower() for word in MINOR_WORDS)


@pytest.mark.parametrize("word", ["up", "out"])
def testAParticleIsNotTreatedAsMinor(word: str) -> None:
    """
    `up` and `out` are left out of the list on purpose, since a ticket title wants the phrasal verb far more often than the preposition.
    """

    assert word not in MINOR_WORDS
