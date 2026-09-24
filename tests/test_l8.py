"""Tests for L8: Two-axis appropriateness assessment per target age."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from doubletake.config import DEFAULT_SETTINGS, Settings
from doubletake.enums import (
    AgeAppropriatenessVerdict,
    AnchorRelation,
    AnchoringStatus,
    ComprehensionStatus,
    Genre,
)
from doubletake.l8_appropriateness import assess_l8
from doubletake.layers import run_l8
from doubletake.runner import _LAYER_REGISTRY
from doubletake.schema import (
    AgeVerdict,
    AnalysisRecord,
    CandidateEntry,
    L1Result,
    L3Result,
    L4Result,
    L7Result,
    L8Result,
)


def _make_record(
    text: str = "Why don't skeletons fight? Because they have no guts.",
    target_ages: list[int] = [6, 8, 10],
    term: str = "guts",
    sense_a: str = "internal organs",
    sense_b: str = "courage",
    genre: Genre = Genre.QA_RIDDLE,
    l7_comprehension: dict[int, ComprehensionStatus] | None = None,
) -> AnalysisRecord:
    rec = AnalysisRecord(item_id="test_l8", text=text, target_ages=target_ages)
    rec.l1_result = L1Result(
        genre=genre,
        tokens=text.split(),
        lemmas=text.lower().split(),
        pos_tags=["NOUN"] * len(text.split()),
    )
    rec.l3_result = L3Result(candidates=[CandidateEntry(term=term, score=0.85)])
    rec.l4_result = L4Result(
        sense_a=sense_a,
        sense_a_anchor_quote="skeletons",
        sense_b=sense_b,
        sense_b_anchor_quote="no guts",
        anchor_relation=AnchorRelation.SEPARATE_CONTEXTS,
        anchoring_status=AnchoringStatus.PASS,
        resolving_sense="sense_b",
    )
    if l7_comprehension is None:
        l7_comprehension = {
            6: ComprehensionStatus.PARTIALLY_COMPREHENSIBLE,
            8: ComprehensionStatus.FULLY_COMPREHENSIBLE,
            10: ComprehensionStatus.FULLY_COMPREHENSIBLE,
        }
    rec.l7_result = L7Result(
        per_age_comprehension=l7_comprehension,
        sense_a_aoa=5.0,
        sense_b_aoa=8.42,
        metalinguistic_floor=6.0,
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
    del client.models
    return client


class TestL8Schema:
    def test_l8_result_valid_instantiation(self) -> None:
        res = L8Result(
            per_age_verdict={
                6: AgeAppropriatenessVerdict.VOCABULARY_TOO_ADVANCED,
                8: AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE,
            },
            content_issues=[],
            inference_issues=[],
            explanation="Valid test",
        )
        assert res.per_age_verdict[6] == AgeAppropriatenessVerdict.VOCABULARY_TOO_ADVANCED
        assert res.per_age_verdict[8] == AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE
        assert res.content_issues == []
        assert res.explanation == "Valid test"

    def test_l8_result_extra_fields_forbidden(self) -> None:
        with pytest.raises(Exception):
            L8Result(
                per_age_verdict={8: AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE},
                unsupported_field="fail",  # type: ignore[call-arg]
            )

    def test_age_verdict_valid(self) -> None:
        av = AgeVerdict(
            comprehension=ComprehensionStatus.FULLY_COMPREHENSIBLE,
            appropriateness=AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE,
        )
        assert av.comprehension == ComprehensionStatus.FULLY_COMPREHENSIBLE
        assert av.appropriateness == AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE


class TestL8DeterministicBaseline:
    def test_clean_joke_verdict_progression(self) -> None:
        # For J01 "guts": age 6 vocabulary too advanced; ages 8 & 10 fully age appropriate
        rec = _make_record(
            text="Why don't skeletons fight? Because they have no guts.",
            target_ages=[6, 8, 10],
            l7_comprehension={
                6: ComprehensionStatus.PARTIALLY_COMPREHENSIBLE,
                8: ComprehensionStatus.FULLY_COMPREHENSIBLE,
                10: ComprehensionStatus.FULLY_COMPREHENSIBLE,
            },
        )
        res = assess_l8(rec, DEFAULT_SETTINGS)
        assert res.per_age_verdict[6] == AgeAppropriatenessVerdict.VOCABULARY_TOO_ADVANCED
        assert res.per_age_verdict[8] == AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE
        assert res.per_age_verdict[10] == AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE
        assert res.content_issues == []
        assert res.inference_issues == []

    def test_content_inappropriate_substance_detected(self) -> None:
        # Joke mentioning beer/alcohol should flag content as not appropriate for child
        rec = _make_record(
            text="A man walked into a bar and ordered a beer.",
            target_ages=[8, 14],
        )
        res = assess_l8(rec, DEFAULT_SETTINGS)
        assert "substances" in res.content_issues
        assert res.per_age_verdict[8] == AgeAppropriatenessVerdict.CONTENT_NOT_APPROPRIATE

    def test_content_inappropriate_violence_detected(self) -> None:
        rec = _make_record(
            text="The assassin decided to murder his enemy with a pistol.",
            target_ages=[8],
        )
        res = assess_l8(rec, DEFAULT_SETTINGS)
        assert "violence" in res.content_issues
        assert res.per_age_verdict[8] == AgeAppropriatenessVerdict.CONTENT_NOT_APPROPRIATE

    def test_inference_too_advanced_finance_detected(self) -> None:
        # Financial / legal concept outside typical childhood experience
        rec = _make_record(
            text="The accountant refused to sign the tax audit because of corporate bankruptcy.",
            target_ages=[8],
            l7_comprehension={8: ComprehensionStatus.FULLY_COMPREHENSIBLE},
        )
        res = assess_l8(rec, DEFAULT_SETTINGS)
        assert "finance_legal" in res.inference_issues
        assert res.per_age_verdict[8] == AgeAppropriatenessVerdict.CONTENT_OK_INFERENCE_TOO_ADVANCED

    def test_wordplay_skill_too_advanced_aligns_inference(self) -> None:
        rec = _make_record(
            target_ages=[5],
            l7_comprehension={5: ComprehensionStatus.WORDPLAY_SKILL_TOO_ADVANCED},
        )
        res = assess_l8(rec, DEFAULT_SETTINGS)
        assert res.per_age_verdict[5] == AgeAppropriatenessVerdict.CONTENT_OK_INFERENCE_TOO_ADVANCED


class TestL8MultiBackendMocking:
    def test_gemini_mock(self) -> None:
        payload = json.dumps({
            "content_appropriate": {"6": True, "8": True},
            "inference_appropriate": {"6": False, "8": True},
            "per_age_verdict": {
                "6": "CONTENT_OK_INFERENCE_TOO_ADVANCED",
                "8": "FULLY_AGE_APPROPRIATE",
            },
            "content_issues": [],
            "inference_issues": ["courage idiom"],
            "explanation": "Gemini evaluated J01",
        })
        client = _mock_gemini_client(payload)
        rec = _make_record(target_ages=[6, 8])
        res = assess_l8(rec, DEFAULT_SETTINGS, client=client)

        assert res.per_age_verdict[6] == AgeAppropriatenessVerdict.CONTENT_OK_INFERENCE_TOO_ADVANCED
        assert res.per_age_verdict[8] == AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE
        assert "Gemini" in (res.explanation or "")

    def test_anthropic_mock(self) -> None:
        payload = json.dumps({
            "content_appropriate": {"8": True},
            "inference_appropriate": {"8": True},
            "per_age_verdict": {
                "8": "FULLY_AGE_APPROPRIATE",
            },
            "content_issues": [],
            "inference_issues": [],
            "explanation": "Anthropic evaluated",
        })
        client = _mock_anthropic_client(payload)
        settings = DEFAULT_SETTINGS.model_copy(update={"L8_BACKEND": "anthropic"})
        rec = _make_record(target_ages=[8])
        res = assess_l8(rec, settings, client=client)

        assert res.per_age_verdict[8] == AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE

    def test_openai_compatible_mock(self) -> None:
        payload = json.dumps({
            "content_appropriate": {"6": False, "10": True},
            "inference_appropriate": {"6": True, "10": True},
            "per_age_verdict": {
                "6": "CONTENT_NOT_APPROPRIATE",
                "10": "FULLY_AGE_APPROPRIATE",
            },
            "content_issues": ["minor spooky"],
            "inference_issues": [],
            "explanation": "DeepSeek evaluated",
        })
        client = _mock_openai_client(payload)
        settings = DEFAULT_SETTINGS.model_copy(update={"L8_BACKEND": "deepseek"})
        rec = _make_record(target_ages=[6, 10])
        res = assess_l8(rec, settings, client=client)

        assert res.per_age_verdict[6] == AgeAppropriatenessVerdict.CONTENT_NOT_APPROPRIATE
        assert res.per_age_verdict[10] == AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE

    def test_llm_json_fallback_to_deterministic(self) -> None:
        client = _mock_gemini_client("Not valid JSON at all")
        rec = _make_record(target_ages=[6, 8])
        res = assess_l8(rec, DEFAULT_SETTINGS, client=client)

        assert 6 in res.per_age_verdict
        assert 8 in res.per_age_verdict
        assert "Deterministic baseline" in (res.explanation or "")


class TestL8HelpersAndEdgeCases:
    def test_extract_json_markdown_fence(self) -> None:
        from doubletake.l8_appropriateness import _extract_json
        raw = "```json\n{\"per_age_verdict\": {\"8\": \"FULLY_AGE_APPROPRIATE\"}}\n```"
        data = _extract_json(raw)
        assert data["per_age_verdict"]["8"] == "FULLY_AGE_APPROPRIATE"

    def test_extract_json_embedded(self) -> None:
        from doubletake.l8_appropriateness import _extract_json
        raw = "Here is JSON: {\"explanation\": \"OK\"} done."
        data = _extract_json(raw)
        assert data["explanation"] == "OK"

    def test_extract_json_invalid(self) -> None:
        from doubletake.l8_appropriateness import _extract_json
        with pytest.raises(json.JSONDecodeError):
            _extract_json("not valid json at all")

    def test_unknown_backend_raises(self) -> None:
        from doubletake.l8_appropriateness import _complete_l8
        bad_settings = DEFAULT_SETTINGS.model_copy(update={"L8_BACKEND": "nonexistent_backend"})
        with pytest.raises(ValueError, match="Unknown L8_BACKEND"):
            _complete_l8("prompt", bad_settings, client=None)

    def test_gemini_missing_api_key_raises(self) -> None:
        from doubletake.l8_appropriateness import _call_gemini_l8
        settings = DEFAULT_SETTINGS.model_copy(update={"GEMINI_API_KEY": None})
        import os
        old_val = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="not set"):
                _call_gemini_l8("prompt", settings, client=None)
        finally:
            if old_val:
                os.environ["GEMINI_API_KEY"] = old_val

    def test_call_anthropic_direct(self) -> None:
        from doubletake.l8_appropriateness import _call_anthropic_l8
        client = _mock_anthropic_client(json.dumps({"per_age_verdict": {"8": "FULLY_AGE_APPROPRIATE"}}))
        parsed = _call_anthropic_l8("prompt", "claude-sonnet-5", client)
        assert parsed is not None

        bad_client = _mock_anthropic_client("bad json")
        assert _call_anthropic_l8("prompt", "claude-sonnet-5", bad_client) is None

    def test_call_gemini_single_and_chain(self) -> None:
        from google.genai.errors import ServerError as _GeminiServerError
        from doubletake.l8_appropriateness import _call_gemini_l8, _call_gemini_l8_single

        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = json.dumps({"per_age_verdict": {"8": "FULLY_AGE_APPROPRIATE"}})
        mock_client.models.generate_content.return_value = resp

        parsed, retries, err = _call_gemini_l8_single("prompt", "gemini-3.6-flash", mock_client, 1024)
        assert parsed is not None
        assert err is None

        # Fallback chain on 5xx
        server_err = _GeminiServerError(503, "Unavailable")

        def side_effect(model: str, contents: Any, config: Any) -> Any:
            if model == "gemini-3.6-flash":
                raise server_err
            return resp

        mock_client.models.generate_content.side_effect = side_effect
        settings = DEFAULT_SETTINGS.model_copy(update={
            "L8_MODEL_GEMINI": "gemini-3.6-flash",
            "L8_MODEL_GEMINI_CHAIN": ["gemini-3.8-flash"],
        })
        call_res = _call_gemini_l8("prompt", settings, mock_client)
        assert call_res.parsed is not None
        assert call_res.fallback_used is True
        assert call_res.model_used == "gemini-3.8-flash"

    def test_call_openai_direct(self) -> None:
        from doubletake.l8_appropriateness import _call_openai_l8
        client = _mock_openai_client(json.dumps({"per_age_verdict": {"8": "FULLY_AGE_APPROPRIATE"}}))
        call = _call_openai_l8("prompt", "openai", DEFAULT_SETTINGS, client=client)
        assert call.parsed is not None


class TestL8PipelineIntegration:
    def test_run_l8_populates_record_verdict_and_trace(self) -> None:
        rec = _make_record(target_ages=[6, 8])
        updated = run_l8(rec, DEFAULT_SETTINGS)

        assert updated.l8_result is not None
        assert 6 in updated.l8_result.per_age_verdict
        assert 8 in updated.l8_result.per_age_verdict

        # Verify record.final.per_age populated with AgeVerdict
        assert updated.final is not None
        assert 6 in updated.final.per_age
        assert 8 in updated.final.per_age
        assert updated.final.per_age[6].comprehension == ComprehensionStatus.PARTIALLY_COMPREHENSIBLE
        assert updated.final.per_age[6].appropriateness == AgeAppropriatenessVerdict.VOCABULARY_TOO_ADVANCED
        assert updated.final.per_age[8].comprehension == ComprehensionStatus.FULLY_COMPREHENSIBLE
        assert updated.final.per_age[8].appropriateness == AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE

        l8_traces = [t for t in updated.trace if t.layer == "L8"]
        assert len(l8_traces) == 1
        assert l8_traces[0].status == "OK"

    def test_pipeline_runner_includes_l8(self) -> None:
        rec = AnalysisRecord(
            item_id="pipe_test",
            text="Why don't skeletons fight? They don't have the guts.",
            target_ages=[6, 8, 10],
        )
        for layer_name, layer_fn in _LAYER_REGISTRY:
            try:
                rec = layer_fn(rec, DEFAULT_SETTINGS)
            except Exception:
                pass

        trace_layers = [t.layer for t in rec.trace]
        assert "L7" in trace_layers
        assert "L8" in trace_layers
        assert "L0-post" in trace_layers

        l7_idx = trace_layers.index("L7")
        l8_idx = trace_layers.index("L8")
        l0_post_idx = trace_layers.index("L0-post")
        assert l7_idx < l8_idx < l0_post_idx

        assert rec.l8_result is not None
        assert rec.final is not None
        assert 8 in rec.final.per_age
        assert 10 in rec.final.per_age
        assert rec.final.per_age[8].appropriateness == AgeAppropriatenessVerdict.VOCABULARY_TOO_ADVANCED
        assert rec.final.per_age[10].appropriateness == AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE
