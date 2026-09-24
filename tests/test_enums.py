"""Verify every status string from the README appears in enums.py."""

import pytest

from doubletake.enums import (
    AgeAppropriatenessVerdict,
    AmbiguityAblation,
    AnchorRelation,
    AnchoringStatus,
    ComprehensionStatus,
    DistinctnessStatus,
    Genre,
    MainClassification,
    ResolutionStatus,
    ScopeLabel,
)

# All values present across every enum, for O(1) membership checks.
_ALL_ENUM_VALUES: set[str] = set()
for _cls in (
    ScopeLabel,
    Genre,
    AnchoringStatus,
    AnchorRelation,
    ResolutionStatus,
    DistinctnessStatus,
    AmbiguityAblation,
    ComprehensionStatus,
    AgeAppropriatenessVerdict,
    MainClassification,
):
    for _member in _cls:
        _ALL_ENUM_VALUES.add(_member.value)


# Every status string that appears verbatim in the README.
_README_STATUS_STRINGS: list[str] = [
    # ScopeLabel
    "HOMOGRAPH",
    "COMPOUND_SPLIT",
    "OUT_OF_SCOPE_HOMOPHONE",
    "OUT_OF_SCOPE_NONLEXICAL_JOKE",
    "NO_SCOPE_MECHANISM",
    # Genre
    "QA_RIDDLE",
    "DEFINITIONAL_ONELINER",
    "DIALOGUE_MISUNDERSTANDING",
    "DECLARATIVE",
    # AnchoringStatus (L4 suggested schema)
    "PASS",
    "FAIL",
    "ONE_SENSE_ONLY",
    # AnchorRelation (L4 suggested schema)
    "separate_contexts",
    "resegmentation",
    "speaker_mismatch",
    # ResolutionStatus
    "RESOLUTION_PASS",
    "RESOLUTION_FAIL",
    "INSUFFICIENT_CONTEXT",
    # DistinctnessStatus
    "SENSES_DISTINCT",
    "SENSES_TOO_CLOSE",
    "L6_SKIPPED_NO_PARAPHRASE",
    # AmbiguityAblation
    "SUPPORTED",
    "UNSUPPORTED",
    "SKIPPED",
    # ComprehensionStatus
    "FULLY_COMPREHENSIBLE",
    "PARTIALLY_COMPREHENSIBLE",
    "SENSE_B_TOO_ADVANCED",
    "WORDPLAY_SKILL_TOO_ADVANCED",
    "AOA_UNKNOWN",
    # AgeAppropriatenessVerdict
    "FULLY_AGE_APPROPRIATE",
    "CONTENT_OK_INFERENCE_TOO_ADVANCED",
    "VOCABULARY_TOO_ADVANCED",
    "CONTENT_NOT_APPROPRIATE",
    # MainClassification
    "VALID_HOMOGRAPH_JOKE",
    "VALID_COMPOUND_SPLIT_JOKE",
    "NO_AMBIGUITY_FOUND",
    "ONE_SENSE_ONLY",
    "ANCHORING_FAIL",
    "RESOLUTION_FAIL",
    "SENSES_TOO_CLOSE",
    "OUT_OF_SCOPE_HOMOPHONE",
    "OUT_OF_SCOPE_NONLEXICAL_JOKE",
]


@pytest.mark.parametrize("status_string", _README_STATUS_STRINGS)
def test_readme_status_string_in_enum(status_string: str) -> None:
    assert status_string in _ALL_ENUM_VALUES, (
        f"Status string '{status_string}' appears in README but is missing "
        "from enums.py."
    )


def test_readme_contains_all_status_strings() -> None:
    """Detect README drift: assert every expected status string appears in README.md."""
    from pathlib import Path
    readme_path = Path(__file__).resolve().parents[1] / "README.md"
    assert readme_path.exists()
    content = readme_path.read_text(encoding="utf-8")
    for s in _README_STATUS_STRINGS:
        assert s in content, f"Status string '{s}' expected in README.md but missing"
