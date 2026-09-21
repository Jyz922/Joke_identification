"""Tests for AnalysisRecord schema: JSON round-trip, invariant validation,
and corpus loader error handling."""

import pytest
from pydantic import ValidationError

from doubletake.corpus import join_blind_gold, load_blind, load_gold
from doubletake.enums import (
    AgeAppropriatenessVerdict,
    ComprehensionStatus,
    MainClassification,
    ScopeLabel,
)
from doubletake.schema import (
    AnalysisRecord,
    AgeVerdict,
    FinalVerdict,
    LayerTrace,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_record() -> AnalysisRecord:
    return AnalysisRecord(
        item_id="J01",
        text="Why don't skeletons fight? Because they have no guts.",
        target_ages=[6, 8, 10],
    )


def _age_verdict() -> AgeVerdict:
    return AgeVerdict(
        comprehension=ComprehensionStatus.FULLY_COMPREHENSIBLE,
        appropriateness=AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE,
    )


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------

def test_minimal_record_round_trips() -> None:
    original = _minimal_record()
    restored = AnalysisRecord.model_validate_json(original.model_dump_json())
    assert restored == original


def test_record_with_trace_round_trips() -> None:
    record = _minimal_record()
    record.trace.append(LayerTrace(
        layer="L0-pre",
        status="OK",
        reason=None,
        duration_ms=1.2,
        hints_used=0,
    ))
    restored = AnalysisRecord.model_validate_json(record.model_dump_json())
    assert restored.trace[0].layer == "L0-pre"


def test_record_with_final_round_trips() -> None:
    record = _minimal_record()
    record.final = FinalVerdict(
        main_classification=MainClassification.VALID_HOMOGRAPH_JOKE,
        scope_label=ScopeLabel.HOMOGRAPH,
        per_age={8: _age_verdict()},
    )
    record.confidence = 0.92
    restored = AnalysisRecord.model_validate_json(record.model_dump_json())
    assert restored.final.scope_label == ScopeLabel.HOMOGRAPH
    assert restored.confidence == 0.92
    assert restored.final.per_age[8].comprehension == ComprehensionStatus.FULLY_COMPREHENSIBLE


# ---------------------------------------------------------------------------
# per_age validation: detection fields must not appear inside AgeVerdict
# ---------------------------------------------------------------------------

def test_per_age_rejects_extra_detection_field() -> None:
    """AgeVerdict has extra='forbid'; smuggling a detection field must raise."""
    with pytest.raises(ValidationError):
        AnalysisRecord.model_validate({
            "item_id": "J01",
            "text": "test text ok",
            "target_ages": [8],
            "trace": [],
            "final": {
                "main_classification": "VALID_HOMOGRAPH_JOKE",
                "scope_label": "HOMOGRAPH",
                "per_age": {
                    "8": {
                        "comprehension": "FULLY_COMPREHENSIBLE",
                        "appropriateness": "FULLY_AGE_APPROPRIATE",
                        "ambiguous_term": "guts",  # detection field — must be rejected
                    }
                },
            },
        })


def test_age_verdict_rejects_any_extra_field() -> None:
    with pytest.raises(ValidationError):
        AgeVerdict.model_validate({
            "comprehension": "FULLY_COMPREHENSIBLE",
            "appropriateness": "FULLY_AGE_APPROPRIATE",
            "sense_a": "internal organs",
        })


def test_record_without_final_validates_cleanly() -> None:
    record = _minimal_record()
    assert record.final is None
    # model_validator should not raise when final is None
    AnalysisRecord.model_validate_json(record.model_dump_json())


# ---------------------------------------------------------------------------
# Corpus loader error handling
# ---------------------------------------------------------------------------

def test_load_blind_rejects_malformed_json(tmp_path) -> None:
    bad = tmp_path / "blind.jsonl"
    bad.write_text(
        '{"id":"J01","text":"ok","target_ages":[8]}\nnot-json\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid JSON"):
        load_blind(bad)


def test_load_blind_rejects_missing_field(tmp_path) -> None:
    bad = tmp_path / "blind.jsonl"
    bad.write_text('{"id":"J01","text":"ok"}\n', encoding="utf-8")  # no target_ages
    with pytest.raises(ValueError, match="missing required fields"):
        load_blind(bad)


def test_load_blind_rejects_unknown_field(tmp_path) -> None:
    bad = tmp_path / "blind.jsonl"
    bad.write_text(
        '{"id":"J01","text":"ok","target_ages":[8],"extra":"bad"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown fields"):
        load_blind(bad)


def test_load_blind_rejects_duplicate_id(tmp_path) -> None:
    bad = tmp_path / "blind.jsonl"
    bad.write_text(
        '{"id":"J01","text":"ok","target_ages":[8]}\n'
        '{"id":"J01","text":"again","target_ages":[8]}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate id"):
        load_blind(bad)


def test_load_gold_rejects_malformed_json(tmp_path) -> None:
    bad = tmp_path / "gold.jsonl"
    bad.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_gold(bad)


def test_join_blind_gold_rejects_gold_id_absent_from_blind(tmp_path) -> None:
    blind_file = tmp_path / "blind.jsonl"
    blind_file.write_text(
        '{"id":"J01","text":"Why don\'t skeletons fight?","target_ages":[8]}\n',
        encoding="utf-8",
    )
    gold_file = tmp_path / "gold.jsonl"
    gold_file.write_text(
        '{"id":"J99","gold_label":"VALID_HOMOGRAPH_JOKE","genre":"QA_RIDDLE",'
        '"ambiguous_term":"guts","sense_a":"organs","sense_b":"courage",'
        '"expected_age_verdict":{"8":"FULLY_AGE_APPROPRIATE"}}\n',
        encoding="utf-8",
    )
    blind = load_blind(blind_file)
    gold = load_gold(gold_file)
    with pytest.raises(ValueError, match="Gold ids not found in blind"):
        join_blind_gold(blind, gold)
