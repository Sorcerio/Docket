"""
Id Tests

Cover key validation, id parsing, next-number allocation, and slug hardening.
"""

# MARK: Imports

import pytest

from docket.core.errors import InvalidIdError, InvalidKeyError
from docket.core.ids import SLUG_FALLBACK, SLUG_MAX_LENGTH, buildFilename, formatId, keyOf, nextId, nextNumber, parseId, requireValidKey, slugify

# MARK: Functions


@pytest.mark.parametrize("key", ["CORE", "GEN", "A", "P29", "X1Y2"])
def testValidKeysAreAccepted(key: str) -> None:
    """
    A key that is uppercase alphanumeric and starts with a letter is accepted.
    """

    assert requireValidKey(key) == key


@pytest.mark.parametrize("key", ["core", "Core", "1CORE", "CO-RE", "CO RE", "", "proposed", "CORE_1"])
def testMalformedKeysAreRejected(key: str) -> None:
    """
    Anything outside the required form is rejected, including the lowercase `proposed` table name.
    """

    with pytest.raises(InvalidKeyError):
        requireValidKey(key)


def testParseIdSplitsKeyAndNumber() -> None:
    """
    A well-formed id splits into its key and its number.
    """

    assert parseId("CORE-14") == ("CORE", 14)
    assert keyOf("GEN-3") == "GEN"


@pytest.mark.parametrize("ticketId", ["CORE14", "CORE-0", "CORE-01", "core-14", "CORE-14x", "xCORE-14", "CORE-", "-14", ""])
def testMalformedIdsAreRejected(ticketId: str) -> None:
    """
    Partial matches, leading zeros, and a zero number are all rejected.
    """

    with pytest.raises(InvalidIdError):
        parseId(ticketId)


def testFormatIdRejectsANonPositiveNumber() -> None:
    """
    Ticket numbers start at 1, so zero and negatives are refused at construction.
    """

    assert formatId("CORE", 14) == "CORE-14"

    with pytest.raises(InvalidIdError):
        formatId("CORE", 0)


def testNextNumberIgnoresOtherKeys() -> None:
    """
    Allocation scans only ids carrying the requested key.
    """

    existing: list[str] = ["CORE-1", "CORE-2", "GEN-9", "HEAD-40"]

    assert nextNumber("CORE", existing) == 3
    assert nextNumber("GEN", existing) == 10
    assert nextNumber("META", existing) == 1


def testNextNumberDoesNotFillGaps() -> None:
    """
    A deleted ticket's number is never reused, so allocation is one past the highest seen.
    """

    assert nextNumber("CORE", ["CORE-1", "CORE-7"]) == 8
    assert nextId("CORE", ["CORE-1", "CORE-7"]) == "CORE-8"


def testNextNumberIgnoresMalformedIds() -> None:
    """
    A corrupt id in the set does not break allocation for the rest.
    """

    assert nextNumber("CORE", ["CORE-1", "not an id", "CORE-x", "CORE-4"]) == 5


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Skirmish setup", "skirmishSetup"),
        ("skirmish", "skirmish"),
        ("HTTP API client", "httpApiClient"),
        ("Multi-layer battlescape", "multiLayerBattlescape"),
        ("  leading and trailing  ", "leadingAndTrailing"),
        ("Phase 2 map gen", "phase2MapGen"),
        ("café résumé", "cafeResume"),
        ("under_scored words", "underScoredWords"),
    ],
)
def testSlugifyProducesCamelCase(title: str, expected: str) -> None:
    """
    Ordinary titles become camelCase slugs, with accents folded onto their ASCII bases.
    """

    assert slugify(title) == expected


@pytest.mark.parametrize(
    "title",
    [
        "../../etc/passwd",
        "..\\..\\windows\\system32",
        "a/b/c",
        "name\x00with\x00nulls",
        'quote"and\'quote',
        "semi;colon && rm -rf",
        "tab\tand\nnewline",
    ],
)
def testSlugifyStripsPathAndShellCharacters(title: str) -> None:
    """
    A hostile title cannot produce a slug containing a separator, a dot, or a control character.
    """

    slug: str = slugify(title)

    assert "/" not in slug
    assert "\\" not in slug
    assert "." not in slug
    assert slug.isalnum()


@pytest.mark.parametrize("title", ["", "   ", "...", "!!!", "😀🎉", "日本語", "---"])
def testSlugifyFallsBackWhenNothingSurvives(title: str) -> None:
    """
    A title with no ASCII alphanumerics falls back rather than producing an empty filename.
    """

    assert slugify(title) == SLUG_FALLBACK


def testSlugifyCutsAtTheCap() -> None:
    """
    Truncation lands wherever the cap falls, mid-token included.
    """

    slug: str = slugify("alpha bravo charlie delta echo foxtrot golf hotel india juliet")

    assert len(slug) == SLUG_MAX_LENGTH

    # `india` ends at 47 characters, so the cap takes the first letter of `juliet` with it.
    assert slug == "alphaBravoCharlieDeltaEchoFoxtrotGolfHotelIndiaJ"[:SLUG_MAX_LENGTH]


def testSlugifyHardCutsAnOversizedSingleToken() -> None:
    """
    One token longer than the cap has no boundary to break on, so it is cut hard.
    """

    slug: str = slugify("a" * 200)

    assert len(slug) == SLUG_MAX_LENGTH


def testBuildFilenameCombinesIdAndSlug() -> None:
    """
    The filename is the id, an underscore, the slug, and the extension.
    """

    assert buildFilename("CORE-14", "Skirmish setup") == "CORE-14_skirmishSetup.md"


def testBuildFilenameValidatesTheId() -> None:
    """
    A malformed id is refused rather than being interpolated into a path.
    """

    with pytest.raises(InvalidIdError):
        buildFilename("../evil", "Skirmish setup")


def testBuildFilenameIsSafeForAReservedDeviceName() -> None:
    """
    A title matching a Windows device name is harmless, because the id prefix means the stem never equals it.
    """

    assert buildFilename("CORE-3", "CON") == "CORE-3_con.md"
