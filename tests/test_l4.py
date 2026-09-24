"""Tests for L4 sense anchoring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from doubletake.config import DEFAULT_SETTINGS, Settings
from doubletake.enums import AnchorRelation, AnchoringStatus, Genre
from doubletake.l4_anchoring import _align_substring, _render_l4_prompt, anchor_l4
from doubletake.layers import run_l1, run_l2, run_l3, run_l4
from doubletake.schema import (
    AnalysisRecord,
    CandidateEntry,
    L1Result,
    L2Result,
    L3Result,
    L4Result,
)

_FIXTURES_PATH = Path(__file__).parent / "fixtures" / "l5_anchors.jsonl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_fixtures() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in _FIXTURES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _make_record(
    text: str,
    genre: Genre,
    candidate_term: str | None = None,
    item_id: str = "test",
) -> AnalysisRecord:
    record = AnalysisRecord(item_id=item_id, text=text, target_ages=[8])
    record.l1_result = L1Result(genre=genre, tokens=text.split(), lemmas=[], pos_tags=[])
    if candidate_term:
        record.l3_result = L3Result(
            candidates=[CandidateEntry(term=candidate_term, score=0.85)]
        )
    return record


def _mock_client(responses: list[str]) -> MagicMock:
    client = MagicMock()
    anthropic_msgs, gemini_msgs = [], []
    for text in responses:
        a = MagicMock()
        a.content = [MagicMock(text=text)]
        anthropic_msgs.append(a)
        g = MagicMock()
        g.text = text
        gemini_msgs.append(g)
    client.messages.create.side_effect = anthropic_msgs
    client.models.generate_content.side_effect = gemini_msgs
    return client


# ---------------------------------------------------------------------------
# Schema unit tests
# ---------------------------------------------------------------------------

class TestL4Schema:

    def test_pass_requires_resolving_sense(self) -> None:
        with pytest.raises(ValidationError):
            L4Result(
                sense_a="courage",
                sense_a_anchor_quote="guts",
                sense_b="organs",
                sense_b_anchor_quote="skeletons",
                anchoring_status=AnchoringStatus.PASS,
                resolving_sense=None,  # PASS requires resolving_sense
            )

    def test_one_sense_only_allows_none_resolving_sense(self) -> None:
        r = L4Result(
            sense_a="financial bank",
            sense_a_anchor_quote="bank",
            sense_b="river bank",
            sense_b_anchor_quote="bank",
            anchoring_status=AnchoringStatus.ONE_SENSE_ONLY,
            resolving_sense=None,
        )
        assert r.anchoring_status == AnchoringStatus.ONE_SENSE_ONLY
        assert r.resolving_sense is None


# ---------------------------------------------------------------------------
# Substring alignment helper tests
# ---------------------------------------------------------------------------

class TestSubstringAlignment:

    def test_exact_match(self) -> None:
        assert _align_substring("guts", "They have no guts.") == "guts"

    def test_case_insensitive_alignment(self) -> None:
        assert _align_substring("Elephants", "why do elephants have a trunk?") == "elephants"

    def test_punctuation_stripping(self) -> None:
        assert _align_substring('"no guts."', "Because they have no guts.") == "no guts"


# ---------------------------------------------------------------------------
# Offline anchor_l4 tests (mock LLM)
# ---------------------------------------------------------------------------

class TestAnchorL4Offline:

    def test_raises_when_l1_result_absent(self) -> None:
        rec = AnalysisRecord(item_id="x", text="some text", target_ages=[8])
        with pytest.raises(ValueError, match="L1 must run before L4"):
            anchor_l4(rec)

    def test_qa_homograph_anchoring_pass(self) -> None:
        text = "Why don't skeletons fight? Because they have no guts."
        rec = _make_record(text, Genre.QA_RIDDLE, candidate_term="guts")
        payload = json.dumps({
            "sense_a": "courage or determination",
            "sense_a_anchor_quote": "no guts",
            "sense_b": "internal organs",
            "sense_b_anchor_quote": "skeletons",
            "anchor_relation": "separate_contexts",
            "anchoring_status": "PASS",
            "resolving_sense": "sense_a",
        })
        res = anchor_l4(rec, client=_mock_client([payload]))
        assert res.anchoring_status == AnchoringStatus.PASS
        assert res.anchor_relation == AnchorRelation.SEPARATE_CONTEXTS
        assert res.resolving_sense == "sense_a"
        assert res.sense_a_anchor_quote == "no guts"
        assert res.sense_b_anchor_quote == "skeletons"

    def test_compound_split_anchoring_pass(self) -> None:
        text = "Autobiography: when your car starts telling you about its life."
        rec = _make_record(text, Genre.DEFINITIONAL_ONELINER, candidate_term="autobiography")
        rec.l3_result.candidates[0].score_components["compound_split"] = 1.0  # type: ignore[union-attr]
        payload = json.dumps({
            "sense_a": "written account of one's own life",
            "sense_a_anchor_quote": "autobiography",
            "sense_b": "auto (car) + biography (life story)",
            "sense_b_anchor_quote": "autobiography",
            "anchor_relation": "resegmentation",
            "anchoring_status": "PASS",
            "resolving_sense": "sense_b",
        })
        res = anchor_l4(rec, client=_mock_client([payload]))
        assert res.anchoring_status == AnchoringStatus.PASS
        assert res.anchor_relation == AnchorRelation.RESEGMENTATION
        assert res.resolving_sense == "sense_b"
        assert res.sense_a_anchor_quote == res.sense_b_anchor_quote

    def test_dialogue_misunderstanding_anchoring_pass(self) -> None:
        text = "Doctor: Take two aspirin. Patient: What if they don't work?"
        rec = _make_record(text, Genre.DIALOGUE_MISUNDERSTANDING, candidate_term="aspirin")
        payload = json.dumps({
            "sense_a": "medical drug",
            "sense_a_anchor_quote": "aspirin",
            "sense_b": "something else",
            "sense_b_anchor_quote": "don't work",
            "anchor_relation": "speaker_mismatch",
            "anchoring_status": "PASS",
            "resolving_sense": "sense_b",
        })
        res = anchor_l4(rec, client=_mock_client([payload]))
        assert res.anchoring_status == AnchoringStatus.PASS
        assert res.anchor_relation == AnchorRelation.SPEAKER_MISMATCH

    def test_one_sense_only_anchoring(self) -> None:
        text = "The bank was steep."
        rec = _make_record(text, Genre.DECLARATIVE, candidate_term="bank")
        payload = json.dumps({
            "sense_a": "sloping land",
            "sense_a_anchor_quote": "bank",
            "sense_b": "financial institution",
            "sense_b_anchor_quote": "bank",
            "anchor_relation": None,
            "anchoring_status": "ONE_SENSE_ONLY",
            "resolving_sense": None,
        })
        res = anchor_l4(rec, client=_mock_client([payload]))
        assert res.anchoring_status == AnchoringStatus.ONE_SENSE_ONLY
        assert res.resolving_sense is None

    def test_parse_failure_falls_back_gracefully_to_fail(self) -> None:
        rec = _make_record("text", Genre.DECLARATIVE, candidate_term="word")
        res = anchor_l4(rec, client=_mock_client(["invalid json string"]))
        assert res.anchoring_status == AnchoringStatus.FAIL
        assert res.resolving_sense is None

    def test_run_l4_populates_record_and_trace(self) -> None:
        text = "Why don't skeletons fight? Because they have no guts."
        rec = AnalysisRecord(item_id="t1", text=text, target_ages=[8])
        rec = run_l1(rec, DEFAULT_SETTINGS)
        payload = {
            "sense_a": "courage", "sense_a_anchor_quote": "no guts",
            "sense_b": "organs", "sense_b_anchor_quote": "skeletons",
            "anchor_relation": "separate_contexts",
            "anchoring_status": "PASS",
            "resolving_sense": "sense_a",
        }
        from unittest.mock import patch
        from doubletake.l4_anchoring import _L4Call
        with patch("doubletake.l4_anchoring._complete_l4") as mock_complete:
            mock_complete.return_value = _L4Call(payload, "mock", False, 0)
            rec = run_l4(rec, DEFAULT_SETTINGS)

        assert rec.l4_result is not None
        assert rec.l4_result.anchoring_status == AnchoringStatus.PASS
        assert rec.trace[-1].layer == "L4"
        assert rec.trace[-1].status == "OK"

    def test_anthropic_style_mock_client(self) -> None:
        class AnthropicMockMessage:
            def __init__(self, text: str):
                self.text = text

        class AnthropicMockResponse:
            def __init__(self, text: str):
                self.content = [AnthropicMockMessage(text)]

        class AnthropicMockClient:
            def __init__(self, payload: str):
                self._payload = payload

            class messages:
                @staticmethod
                def create(**kwargs: Any) -> AnthropicMockResponse:
                    return AnthropicMockResponse(kwargs.get("model", ""))

        payload = json.dumps({
            "sense_a": "organs", "sense_a_anchor_quote": "skeletons",
            "sense_b": "courage", "sense_b_anchor_quote": "no guts",
            "anchor_relation": "separate_contexts",
            "anchoring_status": "PASS",
            "resolving_sense": "sense_a",
        })

        client = MagicMock()
        client.messages.create.return_value = AnthropicMockResponse(payload)
        del client.models  # ensure it's not detected as gemini

        rec = _make_record("Because they have no guts.", Genre.DECLARATIVE, candidate_term="guts")
        res = anchor_l4(rec, client=client)
        assert res.anchoring_status == AnchoringStatus.PASS

    def test_l2_senses_included_in_prompt_context(self) -> None:
        from doubletake.schema import L2Result, SenseEntry
        rec = _make_record("He went to the bank to deposit cash.", Genre.DECLARATIVE, candidate_term="bank")
        rec.l2_result = L2Result(
            senses=[
                SenseEntry(term="bank", lemma="bank", pos="NOUN", sense_id="bank.n.01", definition="financial institution", source="wordnet"),
                SenseEntry(term="bank", lemma="bank", pos="NOUN", sense_id="bank.n.02", definition="sloping land beside water", source="wordnet"),
            ]
        )
        payload = json.dumps({
            "sense_a": "financial", "sense_a_anchor_quote": "deposit cash",
            "sense_b": "sloping land", "sense_b_anchor_quote": "bank",
            "anchor_relation": "separate_contexts",
            "anchoring_status": "PASS",
            "resolving_sense": "sense_a",
        })
        res = anchor_l4(rec, client=_mock_client([payload]))
        assert res.anchoring_status == AnchoringStatus.PASS

    def test_unknown_l4_backend_raises(self) -> None:
        from doubletake.l4_anchoring import _complete_l4
        custom_settings = DEFAULT_SETTINGS.model_copy(update={"L4_BACKEND": "unknown_backend"})
        with pytest.raises(ValueError, match="Unknown L4_BACKEND"):
            _complete_l4("test prompt", custom_settings, client=None)

    def test_relation_defaulting_when_omitted(self) -> None:
        # res with PASS but omitted relation, dialogue genre
        rec = _make_record("A: Hello B: Hi", Genre.DIALOGUE_MISUNDERSTANDING, candidate_term="Hello")
        payload = json.dumps({
            "sense_a": "greeting 1", "sense_a_anchor_quote": "Hello",
            "sense_b": "greeting 2", "sense_b_anchor_quote": "Hi",
            "anchor_relation": None,
            "anchoring_status": "PASS",
            "resolving_sense": None,
        })
        res = anchor_l4(rec, client=_mock_client([payload]))
        assert res.anchoring_status == AnchoringStatus.PASS
        assert res.anchor_relation == AnchorRelation.SPEAKER_MISMATCH
        assert res.resolving_sense == "sense_b"  # fallback default


# ---------------------------------------------------------------------------
# Fixture verification test — verifies all 10 fixtures can be parsed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fx", _load_fixtures(), ids=[f["id"] for f in _load_fixtures()])
def test_all_fixtures_l4_result_structure(fx: dict[str, Any]) -> None:
    l4_data = fx["l4_result"]
    expected_status = AnchoringStatus(l4_data["anchoring_status"])
    text = fx["text"]
    rec = _make_record(text, Genre(fx["genre"]), candidate_term=fx["ambiguous_term"], item_id=fx["id"])
    payload = json.dumps(l4_data)
    res = anchor_l4(rec, ambiguous_term=fx["ambiguous_term"], client=_mock_client([payload]))

    assert res.anchoring_status == expected_status
    if expected_status == AnchoringStatus.PASS:
        assert res.resolving_sense == l4_data["resolving_sense"]
        assert res.anchor_relation == AnchorRelation(l4_data["anchor_relation"])
        assert res.sense_a_anchor_quote.lower() in text.lower()
        assert res.sense_b_anchor_quote.lower() in text.lower()
