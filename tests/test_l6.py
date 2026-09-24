"""Tests for L6: Sense-distinctness and lexical-granularity check."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from doubletake.config import DEFAULT_SETTINGS, Settings
from doubletake.enums import (
    AmbiguityAblation,
    AnchorRelation,
    AnchoringStatus,
    DistinctnessStatus,
    Genre,
    MainClassification,
    ResolutionStatus,
    ScopeLabel,
)
from doubletake.l6_distinctness import distinctness_l6
from doubletake.layers import run_l1, run_l6
from doubletake.runner import _l0_post_layer
from doubletake.schema import (
    AnalysisRecord,
    CandidateEntry,
    FinalVerdict,
    L1Result,
    L3Result,
    L4Result,
    L5QAResult,
    L6Result,
)


def _make_record(
    text: str = "Why don't skeletons fight? Because they have no guts.",
    anchoring_status: AnchoringStatus = AnchoringStatus.PASS,
    relation: AnchorRelation = AnchorRelation.SEPARATE_CONTEXTS,
    sense_a: str = "internal organs",
    sense_b: str = "courage",
    term: str = "guts",
) -> AnalysisRecord:
    rec = AnalysisRecord(item_id="test_l6", text=text, target_ages=[8])
    rec.l1_result = L1Result(
        genre=Genre.QA_RIDDLE,
        tokens=text.split(),
        lemmas=text.lower().split(),
        pos_tags=["NOUN"] * len(text.split()),
    )
    rec.l3_result = L3Result(candidates=[CandidateEntry(term=term, score=0.8)])
    rec.l4_result = L4Result(
        sense_a=sense_a,
        sense_a_anchor_quote="skeletons" if relation != AnchorRelation.RESEGMENTATION else term,
        sense_b=sense_b,
        sense_b_anchor_quote="no guts" if relation != AnchorRelation.RESEGMENTATION else term,
        anchor_relation=relation,
        anchoring_status=anchoring_status,
        resolving_sense="sense_b" if anchoring_status == AnchoringStatus.PASS else None,
    )
    return rec


def _mock_gemini_client(payload: str) -> MagicMock:
    client = MagicMock()
    resp = MagicMock()
    resp.text = payload
    client.models.generate_content.return_value = resp
    return client


def _mock_openai_client(payload: str) -> MagicMock:
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = payload
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


def _mock_anthropic_client(payload: str) -> MagicMock:
    class AnthropicMockMessage:
        def __init__(self, text: str):
            self.text = text

    class AnthropicMockResponse:
        def __init__(self, text: str):
            self.content = [AnthropicMockMessage(text)]

    client = MagicMock()
    client.messages.create.return_value = AnthropicMockResponse(payload)
    del client.models  # ensure models doesn't override
    return client


class TestL6Schema:
    def test_l6_result_valid_instantiation(self) -> None:
        res = L6Result(
            distinctness_status=DistinctnessStatus.SENSES_DISTINCT,
            ambiguity_ablation=AmbiguityAblation.SUPPORTED,
            sense_a_paraphrase="internal organs",
            sense_b_paraphrase="courage",
            explanation="Different concepts.",
        )
        assert res.distinctness_status == DistinctnessStatus.SENSES_DISTINCT
        assert res.ambiguity_ablation == AmbiguityAblation.SUPPORTED
        assert res.sense_a_paraphrase == "internal organs"

    def test_forbid_extra_fields(self) -> None:
        with pytest.raises(Exception):
            L6Result(
                distinctness_status=DistinctnessStatus.SENSES_DISTINCT,
                extra_unexpected_field="disallowed",  # type: ignore[call-arg]
            )


class TestL6ShortCircuits:
    def test_short_circuit_when_l4_is_none(self) -> None:
        rec = AnalysisRecord(item_id="t1", text="some text", target_ages=[8])
        res = distinctness_l6(rec)
        assert res.distinctness_status == DistinctnessStatus.L6_SKIPPED_NO_PARAPHRASE
        assert res.ambiguity_ablation == AmbiguityAblation.SKIPPED

    def test_short_circuit_when_l4_not_pass(self) -> None:
        rec = _make_record(anchoring_status=AnchoringStatus.ONE_SENSE_ONLY)
        res = distinctness_l6(rec)
        assert res.distinctness_status == DistinctnessStatus.L6_SKIPPED_NO_PARAPHRASE
        assert res.ambiguity_ablation == AmbiguityAblation.SKIPPED

    def test_short_circuit_resegmentation_is_distinct(self) -> None:
        rec = _make_record(relation=AnchorRelation.RESEGMENTATION, sense_a="frozen dessert", sense_b="shout")
        res = distinctness_l6(rec, client=None)  # No LLM client needed!
        assert res.distinctness_status == DistinctnessStatus.SENSES_DISTINCT
        assert res.ambiguity_ablation == AmbiguityAblation.SUPPORTED
        assert "Resegmentation" in (res.explanation or "")


class TestL6MockRuns:
    def test_gemini_backend_distinct_senses(self) -> None:
        payload = json.dumps({
            "sense_a_paraphrase": "anatomical organs",
            "sense_b_paraphrase": "bravery / courage",
            "suppresses_other": True,
            "materially_different": True,
            "distinctness_status": "SENSES_DISTINCT",
            "ambiguity_ablation": "SUPPORTED",
            "explanation": "Organs and courage are distinct concepts.",
        })
        client = _mock_gemini_client(payload)
        rec = _make_record()
        res = distinctness_l6(rec, client=client)
        assert res.distinctness_status == DistinctnessStatus.SENSES_DISTINCT
        assert res.ambiguity_ablation == AmbiguityAblation.SUPPORTED
        assert res.sense_a_paraphrase == "anatomical organs"

    def test_openai_backend_too_close_senses(self) -> None:
        payload = json.dumps({
            "sense_a_paraphrase": "jogging",
            "sense_b_paraphrase": "sprinting",
            "suppresses_other": False,
            "materially_different": False,
            "distinctness_status": "SENSES_TOO_CLOSE",
            "ambiguity_ablation": "UNSUPPORTED",
            "explanation": "Both refer to running on foot.",
        })
        settings = DEFAULT_SETTINGS.model_copy(update={"L6_BACKEND": "openai"})
        client = _mock_openai_client(payload)
        rec = _make_record()
        res = distinctness_l6(rec, settings, client=client)
        assert res.distinctness_status == DistinctnessStatus.SENSES_TOO_CLOSE
        assert res.ambiguity_ablation == AmbiguityAblation.UNSUPPORTED
        client.chat.completions.create.assert_called_once()

    def test_deepseek_backend_distinct_senses(self) -> None:
        payload = json.dumps({
            "sense_a_paraphrase": "elephant nose",
            "sense_b_paraphrase": "storage compartment",
            "suppresses_other": True,
            "materially_different": True,
            "distinctness_status": "SENSES_DISTINCT",
            "ambiguity_ablation": "SUPPORTED",
            "explanation": "Clearly distinct meanings.",
        })
        settings = DEFAULT_SETTINGS.model_copy(update={"L6_BACKEND": "deepseek"})
        client = _mock_openai_client(payload)
        rec = _make_record(term="trunk")
        res = distinctness_l6(rec, settings, client=client)
        assert res.distinctness_status == DistinctnessStatus.SENSES_DISTINCT
        client.chat.completions.create.assert_called_once()

    def test_anthropic_backend_mock_run(self) -> None:
        payload = json.dumps({
            "sense_a_paraphrase": "shingles disease",
            "sense_b_paraphrase": "roof shingles",
            "suppresses_other": True,
            "materially_different": True,
            "distinctness_status": "SENSES_DISTINCT",
            "ambiguity_ablation": "SUPPORTED",
            "explanation": "Medical condition vs roofing.",
        })
        settings = DEFAULT_SETTINGS.model_copy(update={"L6_BACKEND": "anthropic"})
        client = _mock_anthropic_client(payload)
        rec = _make_record(term="shingles")
        res = distinctness_l6(rec, settings, client=client)
        assert res.distinctness_status == DistinctnessStatus.SENSES_DISTINCT

    def test_extract_json_with_code_block(self) -> None:
        from doubletake.l6_distinctness import _extract_json
        raw = "```json\n{\"distinctness_status\": \"SENSES_DISTINCT\", \"ambiguity_ablation\": \"SUPPORTED\"}\n```"
        parsed = _extract_json(raw)
        assert parsed["distinctness_status"] == "SENSES_DISTINCT"

    def test_extract_json_embedded_curly_braces(self) -> None:
        from doubletake.l6_distinctness import _extract_json
        raw = "Here is the result: {\"distinctness_status\": \"SENSES_DISTINCT\"} Thank you!"
        parsed = _extract_json(raw)
        assert parsed["distinctness_status"] == "SENSES_DISTINCT"

    def test_unrecognized_status_defaults_to_skipped(self) -> None:
        payload = json.dumps({
            "distinctness_status": "UNKNOWN_CUSTOM_STATUS",
            "ambiguity_ablation": "UNKNOWN_ABLATION",
        })
        client = _mock_gemini_client(payload)
        rec = _make_record()
        res = distinctness_l6(rec, client=client)
        assert res.distinctness_status == DistinctnessStatus.L6_SKIPPED_NO_PARAPHRASE
        assert res.ambiguity_ablation == AmbiguityAblation.SKIPPED

    def test_unknown_l6_backend_raises(self) -> None:
        from doubletake.l6_distinctness import _complete_l6
        custom_settings = DEFAULT_SETTINGS.model_copy(update={"L6_BACKEND": "unknown_backend"})
        with pytest.raises(ValueError, match="Unknown L6_BACKEND"):
            _complete_l6("prompt", custom_settings, client=None)


class TestRunL6Pipeline:
    def test_run_l6_populates_record_and_trace(self) -> None:
        rec = _make_record()
        payload = json.dumps({
            "sense_a_paraphrase": "viscera",
            "sense_b_paraphrase": "fortitude",
            "suppresses_other": True,
            "materially_different": True,
            "distinctness_status": "SENSES_DISTINCT",
            "ambiguity_ablation": "SUPPORTED",
            "explanation": "Distinct.",
        })
        client = _mock_gemini_client(payload)
        from unittest.mock import patch
        with patch("doubletake.l6_distinctness._complete_l6") as mock_comp:
            from doubletake.l6_distinctness import _L6Call
            mock_comp.return_value = _L6Call(json.loads(payload), "mock", False, 0)
            rec = run_l6(rec, DEFAULT_SETTINGS)

        assert rec.l6_result is not None
        assert rec.l6_result.distinctness_status == DistinctnessStatus.SENSES_DISTINCT
        assert rec.trace[-1].layer == "L6"
        assert rec.trace[-1].status == "OK"


class TestL6RunnerIntegration:
    def test_l0_post_downgrades_to_one_sense_only_when_senses_too_close(self) -> None:
        rec = _make_record()
        rec.l5_result = L5QAResult(
            genre=Genre.QA_RIDDLE,
            resolution_status=ResolutionStatus.RESOLUTION_PASS,
            resolution_score=0.85,
            subscores={"polarity_or_direction": 0.8},
        )
        rec.l6_result = L6Result(
            distinctness_status=DistinctnessStatus.SENSES_TOO_CLOSE,
            ambiguity_ablation=AmbiguityAblation.UNSUPPORTED,
            explanation="Senses overlap too closely.",
        )
        rec = _l0_post_layer(rec, DEFAULT_SETTINGS)
        assert rec.final is not None
        assert rec.final.main_classification == MainClassification.ONE_SENSE_ONLY

    def test_l0_post_preserves_valid_joke_when_senses_distinct(self) -> None:
        rec = _make_record()
        rec.l5_result = L5QAResult(
            genre=Genre.QA_RIDDLE,
            resolution_status=ResolutionStatus.RESOLUTION_PASS,
            resolution_score=0.85,
            subscores={"polarity_or_direction": 0.8},
        )
        rec.l6_result = L6Result(
            distinctness_status=DistinctnessStatus.SENSES_DISTINCT,
            ambiguity_ablation=AmbiguityAblation.SUPPORTED,
            explanation="Genuinely distinct.",
        )
        rec = _l0_post_layer(rec, DEFAULT_SETTINGS)
        assert rec.final is not None
        assert rec.final.main_classification == MainClassification.VALID_HOMOGRAPH_JOKE
