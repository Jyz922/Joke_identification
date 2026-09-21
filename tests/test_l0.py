"""Tests for L0-pre (preprocess_input) and L0-post (assign_scope_label)."""

import pytest

from doubletake.config import Settings
from doubletake.enums import ScopeLabel
from doubletake.l0_scope import (
    InputValidationError,
    LayerEvidence,
    assign_scope_label,
    preprocess_input,
)


# ---------------------------------------------------------------------------
# L0-pre: preprocess_input
# ---------------------------------------------------------------------------

class TestPreprocessInput:

    def test_accepts_valid_text(self) -> None:
        result = preprocess_input("Why don't skeletons fight?")
        assert result == "Why don't skeletons fight?"

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert preprocess_input("  hello  ") == "hello"

    def test_collapses_internal_whitespace(self) -> None:
        assert preprocess_input("hello   world") == "hello world"

    def test_collapses_tabs_and_newlines(self) -> None:
        assert preprocess_input("hello\t\nworld") == "hello world"

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(InputValidationError, match="empty or whitespace"):
            preprocess_input("")

    def test_rejects_whitespace_only_string(self) -> None:
        with pytest.raises(InputValidationError, match="empty or whitespace"):
            preprocess_input("   \t\n  ")

    def test_rejects_text_over_max_length(self) -> None:
        settings = Settings(MAX_INPUT_CHARS=10)
        with pytest.raises(InputValidationError, match="maximum is 10"):
            preprocess_input("A" * 11, settings)

    def test_accepts_text_at_exactly_max_length(self) -> None:
        settings = Settings(MAX_INPUT_CHARS=10)
        result = preprocess_input("A" * 10, settings)
        assert len(result) == 10

    def test_rejects_text_below_min_length(self) -> None:
        settings = Settings(MIN_INPUT_CHARS=5)
        with pytest.raises(InputValidationError, match="minimum is 5"):
            preprocess_input("Hi", settings)

    def test_accepts_text_at_exactly_min_length(self) -> None:
        settings = Settings(MIN_INPUT_CHARS=3)
        result = preprocess_input("abc", settings)
        assert result == "abc"

    def test_rejects_excessive_non_ascii(self) -> None:
        settings = Settings(MAX_NON_ASCII_RATIO=0.10)
        # 2 non-ASCII out of 6 chars = 0.33, exceeds 0.10
        with pytest.raises(InputValidationError, match="non-ASCII"):
            preprocess_input("AAAAéé", settings)

    def test_accepts_text_within_non_ascii_ratio(self) -> None:
        settings = Settings(MAX_NON_ASCII_RATIO=0.20)
        # "Hello café" → 1 non-ASCII / 10 chars = 0.10 ≤ 0.20
        result = preprocess_input("Hello café", settings)
        assert "caf" in result

    def test_non_ascii_exactly_at_threshold_is_accepted(self) -> None:
        settings = Settings(MAX_NON_ASCII_RATIO=0.50)
        # "abéé" → 2/4 = 0.50, not strictly greater than 0.50
        result = preprocess_input("abéé", settings)
        assert len(result) == 4


# ---------------------------------------------------------------------------
# L0-post: assign_scope_label — table-driven against every decision branch
# ---------------------------------------------------------------------------

_SCOPE_TABLE: list[tuple[str, LayerEvidence, ScopeLabel]] = [
    (
        "homophone and no homograph → OUT_OF_SCOPE_HOMOPHONE",
        LayerEvidence(is_homophone=True, has_homograph=False),
        ScopeLabel.OUT_OF_SCOPE_HOMOPHONE,
    ),
    (
        "homograph only → HOMOGRAPH",
        LayerEvidence(has_homograph=True),
        ScopeLabel.HOMOGRAPH,
    ),
    (
        "homograph + homophone together → HOMOGRAPH wins (not excluded)",
        LayerEvidence(has_homograph=True, is_homophone=True),
        ScopeLabel.HOMOGRAPH,
    ),
    (
        "compound split only → COMPOUND_SPLIT",
        LayerEvidence(has_compound_split=True),
        ScopeLabel.COMPOUND_SPLIT,
    ),
    (
        "compound split + nonlexical → COMPOUND_SPLIT wins over nonlexical",
        LayerEvidence(has_compound_split=True, is_nonlexical_joke=True),
        ScopeLabel.COMPOUND_SPLIT,
    ),
    (
        "nonlexical only → OUT_OF_SCOPE_NONLEXICAL_JOKE",
        LayerEvidence(is_nonlexical_joke=True),
        ScopeLabel.OUT_OF_SCOPE_NONLEXICAL_JOKE,
    ),
    (
        "homophone + nonlexical, no homograph → OUT_OF_SCOPE_HOMOPHONE wins",
        LayerEvidence(is_homophone=True, is_nonlexical_joke=True),
        ScopeLabel.OUT_OF_SCOPE_HOMOPHONE,
    ),
    (
        "all False (incomplete evidence) → NO_SCOPE_MECHANISM",
        LayerEvidence(),
        ScopeLabel.NO_SCOPE_MECHANISM,
    ),
    (
        "all four flags True → HOMOGRAPH wins (homophone guard: has_homograph=True)",
        LayerEvidence(
            has_homograph=True,
            has_compound_split=True,
            is_homophone=True,
            is_nonlexical_joke=True,
        ),
        ScopeLabel.HOMOGRAPH,
    ),
]


@pytest.mark.parametrize(
    "description,evidence,expected",
    _SCOPE_TABLE,
    ids=[row[0] for row in _SCOPE_TABLE],
)
def test_assign_scope_label(
    description: str,
    evidence: LayerEvidence,
    expected: ScopeLabel,
) -> None:
    assert assign_scope_label(evidence) == expected
