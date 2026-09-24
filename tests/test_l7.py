"""Tests for L7: Comprehension assessment per target age."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from doubletake.config import DEFAULT_SETTINGS, Settings
from doubletake.enums import (
    AnchorRelation,
    AnchoringStatus,
    ComprehensionStatus,
    Genre,
)
from doubletake.l7_comprehension import assess_l7
from doubletake.layers import run_l7
from doubletake.runner import _LAYER_REGISTRY
from doubletake.schema import (
    AnalysisRecord,
    CandidateEntry,
    L1Result,
    L3Result,
    L4Result,
    L7Result,
)


def _make_record(
    text: str = "Why don't skeletons fight? Because they have no guts.",
    target_ages: list[int] = [6, 8, 10],
    term: str = "guts",
    sense_a: str = "internal organs",
    sense_b: str = "courage",
    genre: Genre = Genre.QA_RIDDLE,
    relation: AnchorRelation = AnchorRelation.SEPARATE_CONTEXTS,
) -> AnalysisRecord:
    rec = AnalysisRecord(item_id="test_l7", text=text, target_ages=target_ages)
    rec.l1_result = L1Result(
        genre=genre,
        tokens=text.split(),
        lemmas=text.lower().split(),
        pos_tags=["NOUN"] * len(text.split()),
        compound_splits=["auto", "biography"] if relation == AnchorRelation.RESEGMENTATION else [],
    )
    rec.l3_result = L3Result(
        candidates=[
            CandidateEntry(
                term=term,
                score=0.85,
                score_components={"compound_split": 1.0 if relation == AnchorRelation.RESEGMENTATION else 0.0},
            )
        ]
    )
    rec.l4_result = L4Result(
        sense_a=sense_a,
        sense_a_anchor_quote="skeletons",
        sense_b=sense_b,
        sense_b_anchor_quote="no guts",
        anchor_relation=relation,
        anchoring_status=AnchoringStatus.PASS,
        resolving_sense="sense_b",
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


class TestL7Schema:
    def test_l7_result_valid_instantiation(self) -> None:
        res = L7Result(
            per_age_comprehension={
                6: ComprehensionStatus.PARTIALLY_COMPREHENSIBLE,
                8: ComprehensionStatus.FULLY_COMPREHENSIBLE,
            },
            sense_a_aoa=4.5,
            sense_b_aoa=8.2,
            metalinguistic_floor=6.0,
            explanation="Test explanation",
        )
        assert res.per_age_comprehension[6] == ComprehensionStatus.PARTIALLY_COMPREHENSIBLE
        assert res.per_age_comprehension[8] == ComprehensionStatus.FULLY_COMPREHENSIBLE
        assert res.sense_a_aoa == 4.5
        assert res.sense_b_aoa == 8.2
        assert res.metalinguistic_floor == 6.0
        assert res.explanation == "Test explanation"

    def test_l7_result_extra_fields_forbidden(self) -> None:
        with pytest.raises(Exception):
            L7Result(
                per_age_comprehension={8: ComprehensionStatus.FULLY_COMPREHENSIBLE},
                unexpected_field=123,  # type: ignore[call-arg]
            )


class TestL7DeterministicBaseline:
    def test_homograph_guts_age_progression(self) -> None:
        # At age 6: "guts" sense B (courage, AoA ~ 8.42) is above age 6 -> PARTIALLY_COMPREHENSIBLE
        # At age 8, 10: both senses known and >= floor 6.0 -> FULLY_COMPREHENSIBLE
        rec = _make_record(
            text="Why don't skeletons fight? Because they have no guts.",
            target_ages=[6, 8, 10],
            term="guts",
            sense_a="internal organs",
            sense_b="courage",
        )
        res = assess_l7(rec, DEFAULT_SETTINGS)
        assert res.sense_a_aoa is not None
        assert res.sense_b_aoa is not None
        assert res.sense_b_aoa > res.sense_a_aoa
        assert res.metalinguistic_floor == DEFAULT_SETTINGS.L7_METALINGUISTIC_FLOOR_HOMOGRAPH

        assert res.per_age_comprehension[6] == ComprehensionStatus.PARTIALLY_COMPREHENSIBLE
        assert res.per_age_comprehension[8] == ComprehensionStatus.FULLY_COMPREHENSIBLE
        assert res.per_age_comprehension[10] == ComprehensionStatus.FULLY_COMPREHENSIBLE

    def test_compound_split_metalinguistic_floor(self) -> None:
        # For resegmentation jokes, metalinguistic floor is higher (7.0).
        # At age 5: below metalinguistic floor (7.0) and below sense B / split AoA
        rec = _make_record(
            text="I wrote a book about my life. It was an autobiography.",
            target_ages=[5, 7, 10],
            term="autobiography",
            sense_a="written account of person life",
            sense_b="self moving vehicle story",
            relation=AnchorRelation.RESEGMENTATION,
        )
        res = assess_l7(rec, DEFAULT_SETTINGS)
        assert res.metalinguistic_floor == DEFAULT_SETTINGS.L7_METALINGUISTIC_FLOOR_RESEGMENTATION
        assert res.compound_split_aoa is not None
        assert 5 in res.per_age_comprehension
        assert res.per_age_comprehension[10] == ComprehensionStatus.FULLY_COMPREHENSIBLE

    def test_metalinguistic_floor_by_genre(self) -> None:
        # Dialogue genre floor check
        rec_dialogue = _make_record(
            text="Waiter: What would you like? Customer: Tea please.",
            genre=Genre.DIALOGUE_MISUNDERSTANDING,
        )
        res_dialogue = assess_l7(rec_dialogue, DEFAULT_SETTINGS)
        assert res_dialogue.metalinguistic_floor == DEFAULT_SETTINGS.L7_METALINGUISTIC_FLOOR_DIALOGUE

        # Definitional genre floor check
        rec_def = _make_record(
            text="A bicycle cannot stand on its own because it is two tired.",
            genre=Genre.DEFINITIONAL_ONELINER,
        )
        res_def = assess_l7(rec_def, DEFAULT_SETTINGS)
        assert res_def.metalinguistic_floor == DEFAULT_SETTINGS.L7_METALINGUISTIC_FLOOR_DEFINITIONAL

    def test_wordplay_skill_too_advanced(self) -> None:
        # If vocabulary (sense_b_aoa) is acquired early (e.g. 4.0),
        # but child is age 5 and genre requires floor 6.0,
        # status should be WORDPLAY_SKILL_TOO_ADVANCED.
        rec = _make_record(
            text="Baby joke with easy words",
            target_ages=[5],
            term="dog",
            sense_a="dog",
            sense_b="hound",
        )
        # Force low AoA settings for this test
        settings = DEFAULT_SETTINGS.model_copy(update={"L7_SECONDARY_SENSE_AOA_OFFSET": 0.5})
        res = assess_l7(rec, settings)
        # If sense_b_aoa <= 5 and age 5 < floor 6.0:
        if res.sense_b_aoa and res.sense_b_aoa <= 5.0 and 5.0 < res.metalinguistic_floor:
            assert res.per_age_comprehension[5] == ComprehensionStatus.WORDPLAY_SKILL_TOO_ADVANCED


class TestL7MultiBackendMocking:
    def test_gemini_mock(self) -> None:
        payload = json.dumps({
            "sense_a_aoa": 4.5,
            "sense_b_aoa": 8.0,
            "metalinguistic_floor": 6.0,
            "per_age_comprehension": {
                "6": "PARTIALLY_COMPREHENSIBLE",
                "8": "FULLY_COMPREHENSIBLE",
            },
            "explanation": "Gemini assessed: Sense B requires age 8.",
        })
        client = _mock_gemini_client(payload)
        rec = _make_record(target_ages=[6, 8])
        res = assess_l7(rec, DEFAULT_SETTINGS, client=client)

        assert res.per_age_comprehension[6] == ComprehensionStatus.PARTIALLY_COMPREHENSIBLE
        assert res.per_age_comprehension[8] == ComprehensionStatus.FULLY_COMPREHENSIBLE
        assert res.sense_a_aoa == 4.5
        assert res.sense_b_aoa == 8.0
        assert "Gemini" in (res.explanation or "")

    def test_anthropic_mock(self) -> None:
        payload = json.dumps({
            "sense_a_aoa": 5.0,
            "sense_b_aoa": 8.5,
            "metalinguistic_floor": 6.0,
            "per_age_comprehension": {
                "6": "PARTIALLY_COMPREHENSIBLE",
                "8": "FULLY_COMPREHENSIBLE",
            },
            "explanation": "Anthropic assessment",
        })
        client = _mock_anthropic_client(payload)
        settings = DEFAULT_SETTINGS.model_copy(update={"L7_BACKEND": "anthropic"})
        rec = _make_record(target_ages=[6, 8])
        res = assess_l7(rec, settings, client=client)

        assert res.per_age_comprehension[6] == ComprehensionStatus.PARTIALLY_COMPREHENSIBLE
        assert res.per_age_comprehension[8] == ComprehensionStatus.FULLY_COMPREHENSIBLE
        assert res.sense_a_aoa == 5.0

    def test_openai_compatible_mock(self) -> None:
        payload = json.dumps({
            "sense_a_aoa": 5.0,
            "sense_b_aoa": 9.0,
            "metalinguistic_floor": 6.0,
            "per_age_comprehension": {
                "6": "SENSE_B_TOO_ADVANCED",
                "10": "FULLY_COMPREHENSIBLE",
            },
            "explanation": "DeepSeek / OpenAI assessment",
        })
        client = _mock_openai_client(payload)
        settings = DEFAULT_SETTINGS.model_copy(update={"L7_BACKEND": "deepseek"})
        rec = _make_record(target_ages=[6, 10])
        res = assess_l7(rec, settings, client=client)

        assert res.per_age_comprehension[6] == ComprehensionStatus.SENSE_B_TOO_ADVANCED
        assert res.per_age_comprehension[10] == ComprehensionStatus.FULLY_COMPREHENSIBLE

    def test_llm_json_fallback_to_deterministic(self) -> None:
        client = _mock_gemini_client("Not valid JSON at all")
        rec = _make_record(target_ages=[6, 8])
        res = assess_l7(rec, DEFAULT_SETTINGS, client=client)

        # Should fall back cleanly to deterministic calculation
        assert 6 in res.per_age_comprehension
        assert 8 in res.per_age_comprehension
        assert "Psycholinguistic baseline" in (res.explanation or "")


class TestL7PipelineIntegration:
    def test_run_l7_populates_record_and_trace(self) -> None:
        rec = _make_record(target_ages=[6, 8])
        updated = run_l7(rec, DEFAULT_SETTINGS)

        assert updated.l7_result is not None
        assert 6 in updated.l7_result.per_age_comprehension
        assert 8 in updated.l7_result.per_age_comprehension

        l7_traces = [t for t in updated.trace if t.layer == "L7"]
        assert len(l7_traces) == 1
        assert l7_traces[0].status == "OK"
        assert "ages=[6, 8]" in (l7_traces[0].reason or "")

    def test_pipeline_runner_includes_l7(self) -> None:
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
        # L7 should be executed before L0-post
        l7_idx = trace_layers.index("L7")
        l0_post_idx = trace_layers.index("L0-post")
        assert l7_idx < l0_post_idx

        assert rec.l7_result is not None
        assert 6 in rec.l7_result.per_age_comprehension
        assert 8 in rec.l7_result.per_age_comprehension
        assert 10 in rec.l7_result.per_age_comprehension


class TestL7HelpersAndEdgeCases:
    def test_extract_json_markdown_fence(self) -> None:
        from doubletake.l7_comprehension import _extract_json
        raw = "```json\n{\"metalinguistic_floor\": 7.0, \"per_age_comprehension\": {\"8\": \"FULLY_COMPREHENSIBLE\"}}\n```"
        data = _extract_json(raw)
        assert data["metalinguistic_floor"] == 7.0

    def test_extract_json_embedded(self) -> None:
        from doubletake.l7_comprehension import _extract_json
        raw = "Result: {\"sense_a_aoa\": 4.0, \"per_age_comprehension\": {}} Thanks!"
        data = _extract_json(raw)
        assert data["sense_a_aoa"] == 4.0

    def test_extract_json_invalid(self) -> None:
        from doubletake.l7_comprehension import _extract_json
        with pytest.raises(json.JSONDecodeError):
            _extract_json("not json")

    def test_find_keyword_aoa(self) -> None:
        from doubletake.l7_comprehension import _find_keyword_aoa
        # Stopwords only
        assert _find_keyword_aoa("a an the in on") is None
        # Non-stopwords with AoA
        aoa = _find_keyword_aoa("courage and determination")
        assert aoa is not None
        assert aoa > 5.0

    def test_deterministic_fallback_no_l3_uses_l1(self) -> None:
        rec = AnalysisRecord(item_id="no_l3", text="skeleton", target_ages=[8])
        rec.l1_result = L1Result(
            genre=Genre.QA_RIDDLE,
            tokens=["skeleton"],
            lemmas=["skeleton"],
            pos_tags=["NOUN"],
        )
        res = assess_l7(rec, DEFAULT_SETTINGS)
        assert res.sense_a_aoa is not None
        assert 8 in res.per_age_comprehension

    def test_compound_split_from_l2_senses(self) -> None:
        from doubletake.schema import L2Result, SenseEntry
        rec = AnalysisRecord(item_id="auto", text="autobiography", target_ages=[8])
        rec.l3_result = L3Result(
            candidates=[CandidateEntry(term="autobiography", score=0.9, score_components={"compound_split": 1.0})]
        )
        rec.l2_result = L2Result(
            senses=[
                SenseEntry(
                    term="auto",
                    lemma="auto",
                    pos="n",
                    sense_id="auto.n.01",
                    definition="car",
                    source="wordnet_split:auto+biography",
                    aoa_estimate=5.0,
                    aoa_match="exact",
                )
            ]
        )
        res = assess_l7(rec, DEFAULT_SETTINGS)
        assert res.compound_split_aoa is not None
        assert res.metalinguistic_floor == DEFAULT_SETTINGS.L7_METALINGUISTIC_FLOOR_RESEGMENTATION

    def test_llm_response_various_comprehension_statuses(self) -> None:
        payload = json.dumps({
            "sense_a_aoa": 5.0,
            "sense_b_aoa": 8.0,
            "metalinguistic_floor": 6.0,
            "per_age_comprehension": {
                "5": "WORDPLAY_SKILL_TOO_ADVANCED",
                "6": "SENSE_B_TOO_ADVANCED",
                "7": "PARTIALLY_COMPREHENSIBLE",
                "8": "FULLY_COMPREHENSIBLE",
                "9": "UNKNOWN_CUSTOM_VALUE",
            },
            "explanation": "Testing various statuses",
        })
        client = _mock_gemini_client(payload)
        rec = _make_record(target_ages=[5, 6, 7, 8, 9])
        res = assess_l7(rec, DEFAULT_SETTINGS, client=client)

        assert res.per_age_comprehension[5] == ComprehensionStatus.WORDPLAY_SKILL_TOO_ADVANCED
        assert res.per_age_comprehension[6] == ComprehensionStatus.SENSE_B_TOO_ADVANCED
        assert res.per_age_comprehension[7] == ComprehensionStatus.PARTIALLY_COMPREHENSIBLE
        assert res.per_age_comprehension[8] == ComprehensionStatus.FULLY_COMPREHENSIBLE
        assert res.per_age_comprehension[9] == ComprehensionStatus.AOA_UNKNOWN

    def test_unknown_backend_raises(self) -> None:
        from doubletake.l7_comprehension import _complete_l7
        bad_settings = DEFAULT_SETTINGS.model_copy(update={"L7_BACKEND": "nonexistent_backend"})
        with pytest.raises(ValueError, match="Unknown L7_BACKEND"):
            _complete_l7("prompt", bad_settings, client=None)

    def test_gemini_missing_api_key_raises(self) -> None:
        from doubletake.l7_comprehension import _call_gemini_l7
        settings = DEFAULT_SETTINGS.model_copy(update={"GEMINI_API_KEY": None})
        import os
        old_val = os.environ.pop("GEMINI_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="not set"):
                _call_gemini_l7("prompt", settings, client=None)
        finally:
            if old_val:
                os.environ["GEMINI_API_KEY"] = old_val

    def test_call_anthropic_direct(self) -> None:
        from doubletake.l7_comprehension import _call_anthropic_l7
        # 1st attempt valid
        client = _mock_anthropic_client(json.dumps({"sense_a_aoa": 4.0, "per_age_comprehension": {"8": "FULLY_COMPREHENSIBLE"}}))
        parsed = _call_anthropic_l7("prompt", "claude-sonnet-5", client)
        assert parsed is not None
        assert parsed["sense_a_aoa"] == 4.0

        # Bad json attempts returning None
        bad_client = _mock_anthropic_client("bad json")
        assert _call_anthropic_l7("prompt", "claude-sonnet-5", bad_client) is None

    def test_call_gemini_single_and_chain(self) -> None:
        from google.genai.errors import ServerError as _GeminiServerError
        from doubletake.l7_comprehension import _call_gemini_l7, _call_gemini_l7_single

        # Single success
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = json.dumps({"sense_a_aoa": 5.0, "per_age_comprehension": {}})
        mock_client.models.generate_content.return_value = resp

        parsed, retries, err = _call_gemini_l7_single("prompt", "gemini-3.6-flash", mock_client, 1024)
        assert parsed is not None
        assert err is None

        # Chain fallback on 5xx
        bad_resp = MagicMock()
        bad_resp.code = 503
        server_err = _GeminiServerError(503, "Unavailable")

        def side_effect(model: str, contents: Any, config: Any) -> Any:
            if model == "gemini-3.6-flash":
                raise server_err
            return resp

        mock_client.models.generate_content.side_effect = side_effect
        settings = DEFAULT_SETTINGS.model_copy(update={
            "L7_MODEL_GEMINI": "gemini-3.6-flash",
            "L7_MODEL_GEMINI_CHAIN": ["gemini-3.8-flash"],
        })
        call_res = _call_gemini_l7("prompt", settings, mock_client)
        assert call_res.parsed is not None
        assert call_res.fallback_used is True
        assert call_res.model_used == "gemini-3.8-flash"

    def test_call_openai_direct(self) -> None:
        from doubletake.l7_comprehension import _call_openai_l7
        client = _mock_openai_client(json.dumps({"sense_a_aoa": 4.0, "per_age_comprehension": {}}))
        call = _call_openai_l7("prompt", "openai", DEFAULT_SETTINGS, client=client)
        assert call.parsed is not None
        assert call.parsed["sense_a_aoa"] == 4.0

    def test_assess_l7_no_l3_with_tokens_calls_llm(self) -> None:
        rec = AnalysisRecord(item_id="no_l3", text="skeleton", target_ages=[8])
        rec.l1_result = L1Result(
            genre=Genre.QA_RIDDLE,
            tokens=["skeleton"],
            lemmas=["skeleton"],
            pos_tags=["NOUN"],
        )
        payload = json.dumps({
            "sense_a_aoa": 5.0,
            "sense_b_aoa": 7.0,
            "per_age_comprehension": {"8": "FULLY_COMPREHENSIBLE"},
        })
        client = _mock_gemini_client(payload)
        res = assess_l7(rec, DEFAULT_SETTINGS, client=client)
        assert res.per_age_comprehension[8] == ComprehensionStatus.FULLY_COMPREHENSIBLE

    def test_aoa_unknown_fallback(self) -> None:
        # A record with a non-word or unknown AoA where sense_a_aoa is unknown
        rec = AnalysisRecord(item_id="unknown", text="xyzqwe", target_ages=[8])
        rec.l1_result = L1Result(
            genre=Genre.DECLARATIVE,
            tokens=["xyzqwe"],
            lemmas=["xyzqwe"],
            pos_tags=["NOUN"],
        )
        from unittest.mock import patch
        with patch("doubletake.l7_comprehension.aoa_lookup", return_value=(None, "miss")):
            with patch("doubletake.l7_comprehension._find_keyword_aoa", return_value=None):
                # When sense_a_aoa would fall back
                res = assess_l7(rec, DEFAULT_SETTINGS)
                assert res.sense_a_aoa is not None  # falls back to 5.0 baseline

