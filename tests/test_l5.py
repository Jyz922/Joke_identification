"""Tests for L5 form-specific semantic resolution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from doubletake.config import DEFAULT_SETTINGS
from doubletake.enums import AnchorRelation, AnchoringStatus, Genre, ResolutionStatus
from doubletake.l5_resolution import (
    _L5_DEFINITIONAL_WEIGHTS,
    _L5_DIALOGUE_WEIGHTS,
    resolve_l5,
)
from doubletake.schema import (
    AnalysisRecord,
    L1Result,
    L4Result,
    L5DefinitionalResult,
    L5DialogueResult,
    L5QAResult,
)

_FIXTURES_PATH = Path(__file__).parent / "fixtures" / "l5_anchors.jsonl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    text: str,
    genre: Genre,
    l4_result: L4Result,
    item_id: str = "test",
) -> AnalysisRecord:
    record = AnalysisRecord(item_id=item_id, text=text, target_ages=[8])
    record.l1_result = L1Result(genre=genre, tokens=[], lemmas=[], pos_tags=[])
    record.l4_result = l4_result
    return record


def _mock_client(responses: list[str]) -> MagicMock:
    """Return a mock Anthropic client whose messages.create() yields each response in turn."""
    client = MagicMock()
    msgs = []
    for text in responses:
        m = MagicMock()
        m.content = [MagicMock(text=text)]
        msgs.append(m)
    client.messages.create.side_effect = msgs
    return client


def _load_fixtures() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in _FIXTURES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _fixture_ids() -> list[str]:
    return [item["id"] for item in _load_fixtures()]


def _build_l4(data: dict[str, Any]) -> L4Result:
    return L4Result(
        sense_a=data["sense_a"],
        sense_a_anchor_quote=data["sense_a_anchor_quote"],
        sense_b=data["sense_b"],
        sense_b_anchor_quote=data["sense_b_anchor_quote"],
        anchor_relation=data.get("anchor_relation"),
        anchoring_status=data["anchoring_status"],
    )


# ---------------------------------------------------------------------------
# Schema unit tests — no network
# ---------------------------------------------------------------------------

class TestL5Schema:

    def test_qa_result_construction(self) -> None:
        r = L5QAResult(
            genre=Genre.QA_RIDDLE,
            resolution_status=ResolutionStatus.RESOLUTION_PASS,
            resolution_score=0.75,
            subscores={"polarity_or_direction": 0.9, "answer_relevance": 0.8,
                       "causal": 0.6, "agent": 0.7, "tense_aspect": 0.5},
        )
        assert r.genre == Genre.QA_RIDDLE
        assert r.resolution_score == 0.75

    def test_definitional_result_construction(self) -> None:
        r = L5DefinitionalResult(
            genre=Genre.DEFINITIONAL_ONELINER,
            resolution_status=ResolutionStatus.RESOLUTION_PASS,
            resolution_score=0.80,
            subscores={"setup_invites_literal": 0.9,
                       "punchline_exploits_split": 0.8, "contrast_strength": 0.7},
        )
        assert r.genre == Genre.DEFINITIONAL_ONELINER

    def test_dialogue_result_for_dialogue_genre(self) -> None:
        r = L5DialogueResult(
            genre=Genre.DIALOGUE_MISUNDERSTANDING,
            resolution_status=ResolutionStatus.RESOLUTION_PASS,
            resolution_score=0.72,
            subscores={"misunderstanding_plausible": 0.8,
                       "contrast_clear": 0.7, "speaker_intention_clear": 0.6},
        )
        assert r.genre == Genre.DIALOGUE_MISUNDERSTANDING

    def test_dialogue_result_for_declarative_genre(self) -> None:
        r = L5DialogueResult(
            genre=Genre.DECLARATIVE,
            resolution_status=ResolutionStatus.RESOLUTION_FAIL,
            resolution_score=0.30,
            subscores={},
        )
        assert r.genre == Genre.DECLARATIVE

    def test_frozen_qa_result_rejects_mutation(self) -> None:
        r = L5QAResult(
            genre=Genre.QA_RIDDLE,
            resolution_status=ResolutionStatus.RESOLUTION_PASS,
            resolution_score=0.75,
            subscores={},
        )
        with pytest.raises((ValidationError, TypeError)):
            r.resolution_score = 0.99  # type: ignore[misc]

    def test_record_accepts_any_l5_branch(self) -> None:
        record = AnalysisRecord(item_id="x", text="test", target_ages=[8])
        record.l5_result = L5QAResult(
            genre=Genre.QA_RIDDLE,
            resolution_status=ResolutionStatus.RESOLUTION_PASS,
            resolution_score=0.75,
            subscores={},
        )
        assert record.l5_result is not None
        assert record.l5_result.genre == Genre.QA_RIDDLE

        record.l5_result = L5DefinitionalResult(
            genre=Genre.DEFINITIONAL_ONELINER,
            resolution_status=ResolutionStatus.RESOLUTION_PASS,
            resolution_score=0.80,
            subscores={},
        )
        assert record.l5_result.genre == Genre.DEFINITIONAL_ONELINER

    def test_record_l5_result_defaults_to_none(self) -> None:
        assert AnalysisRecord(item_id="x", text="test", target_ages=[8]).l5_result is None


# ---------------------------------------------------------------------------
# Offline resolve_l5 tests — mock LLM, no network
# ---------------------------------------------------------------------------

class TestResolveL5Offline:

    _QA_TEXT = "Why don't skeletons fight? Because they have no guts."
    _DEF_TEXT = "Autobiography: when your car starts telling you about its life."
    _DLG_TEXT = "Patient: I think I'm a pair of curtains. Doctor: Pull yourself together!"

    def _qa_l4(self) -> L4Result:
        return L4Result(
            sense_a="courage",
            sense_a_anchor_quote="no guts",
            sense_b="internal organs",
            sense_b_anchor_quote="no guts",
            anchor_relation=AnchorRelation.SEPARATE_CONTEXTS,
            anchoring_status=AnchoringStatus.PASS,
        )

    def _definitional_l4(self) -> L4Result:
        return L4Result(
            sense_a="a written account of one's own life",
            sense_a_anchor_quote="autobiography",
            sense_b="auto (car) + biography (life story)",
            sense_b_anchor_quote="autobiography",  # same-span — resegmentation
            anchor_relation=AnchorRelation.RESEGMENTATION,
            anchoring_status=AnchoringStatus.PASS,
        )

    def _dialogue_l4(self) -> L4Result:
        return L4Result(
            sense_a="compose oneself emotionally",
            sense_a_anchor_quote="Pull yourself together",
            sense_b="physically close curtains by pulling",
            sense_b_anchor_quote="Pull yourself together",
            anchor_relation=AnchorRelation.SPEAKER_MISMATCH,
            anchoring_status=AnchoringStatus.PASS,
        )

    def test_qa_pass_with_high_scores(self) -> None:
        record = _make_record(self._QA_TEXT, Genre.QA_RIDDLE, self._qa_l4())
        payload = json.dumps({
            "polarity_or_direction": 0.9, "answer_relevance": 0.9,
            "causal": 0.9, "agent": 0.9, "tense_aspect": 0.9,
            "reasoning": "Strong polarity flip.",
        })
        result = resolve_l5(
            record, DEFAULT_SETTINGS,
            ambiguous_term="guts", client=_mock_client([payload]),
        )
        assert isinstance(result, L5QAResult)
        assert result.resolution_status == ResolutionStatus.RESOLUTION_PASS
        assert result.resolution_score > DEFAULT_SETTINGS.L5_RESOLUTION_THRESHOLD

    def test_qa_fail_with_low_scores(self) -> None:
        record = _make_record(self._QA_TEXT, Genre.QA_RIDDLE, self._qa_l4())
        payload = json.dumps({
            "polarity_or_direction": 0.1, "answer_relevance": 0.1,
            "causal": 0.1, "agent": 0.1, "tense_aspect": 0.1,
            "reasoning": "Weak.",
        })
        result = resolve_l5(
            record, DEFAULT_SETTINGS,
            ambiguous_term="guts", client=_mock_client([payload]),
        )
        assert isinstance(result, L5QAResult)
        assert result.resolution_status == ResolutionStatus.RESOLUTION_FAIL

    def test_definitional_pass_same_span_anchor_allowed(self) -> None:
        """Resegmentation items have identical anchor quotes — must not be penalised."""
        record = _make_record(self._DEF_TEXT, Genre.DEFINITIONAL_ONELINER, self._definitional_l4())
        payload = json.dumps({
            "setup_invites_literal": 0.9, "punchline_exploits_split": 0.9,
            "contrast_strength": 0.9, "reasoning": "Strong compound split.",
        })
        result = resolve_l5(
            record, DEFAULT_SETTINGS,
            ambiguous_term="autobiography", client=_mock_client([payload]),
        )
        assert isinstance(result, L5DefinitionalResult)
        assert result.resolution_status == ResolutionStatus.RESOLUTION_PASS

    def test_dialogue_pass(self) -> None:
        record = _make_record(self._DLG_TEXT, Genre.DIALOGUE_MISUNDERSTANDING, self._dialogue_l4())
        payload = json.dumps({
            "misunderstanding_plausible": 0.9, "contrast_clear": 0.9,
            "speaker_intention_clear": 0.9, "reasoning": "Clear misunderstanding.",
        })
        result = resolve_l5(
            record, DEFAULT_SETTINGS,
            ambiguous_term="pull yourself together", client=_mock_client([payload]),
        )
        assert isinstance(result, L5DialogueResult)
        assert result.resolution_status == ResolutionStatus.RESOLUTION_PASS

    def test_insufficient_context_when_anchoring_not_pass(self) -> None:
        l4 = L4Result(
            sense_a="financial institution",
            sense_a_anchor_quote="bank",
            sense_b="riverbank",
            sense_b_anchor_quote="bank",
            anchor_relation=None,
            anchoring_status=AnchoringStatus.ONE_SENSE_ONLY,
        )
        record = _make_record("The bank was steep.", Genre.DECLARATIVE, l4)
        # No LLM call should occur — pass a client that would fail if called.
        failing_client = MagicMock()
        failing_client.messages.create.side_effect = AssertionError("LLM must not be called")
        result = resolve_l5(record, DEFAULT_SETTINGS, client=failing_client)
        assert result.resolution_status == ResolutionStatus.INSUFFICIENT_CONTEXT
        assert result.resolution_score == 0.0
        failing_client.messages.create.assert_not_called()

    def test_insufficient_context_after_two_json_failures(self) -> None:
        record = _make_record(self._QA_TEXT, Genre.QA_RIDDLE, self._qa_l4())
        result = resolve_l5(
            record, DEFAULT_SETTINGS,
            ambiguous_term="guts",
            client=_mock_client(["not json", "still not json"]),
        )
        assert result.resolution_status == ResolutionStatus.INSUFFICIENT_CONTEXT

    def test_retry_succeeds_on_second_attempt(self) -> None:
        """First response is malformed; second is valid — must return a real verdict."""
        record = _make_record(self._QA_TEXT, Genre.QA_RIDDLE, self._qa_l4())
        good = json.dumps({
            "polarity_or_direction": 0.8, "answer_relevance": 0.8,
            "causal": 0.8, "agent": 0.8, "tense_aspect": 0.8,
            "reasoning": "Retry success.",
        })
        result = resolve_l5(
            record, DEFAULT_SETTINGS,
            ambiguous_term="guts",
            client=_mock_client(["not json at all", good]),
        )
        assert result.resolution_status == ResolutionStatus.RESOLUTION_PASS

    def test_raises_when_l1_result_absent(self) -> None:
        record = AnalysisRecord(item_id="x", text="test", target_ages=[8])
        record.l4_result = self._qa_l4()
        with pytest.raises(ValueError, match="l1_result"):
            resolve_l5(record, DEFAULT_SETTINGS)

    def test_raises_when_l4_result_absent(self) -> None:
        record = AnalysisRecord(item_id="x", text="test", target_ages=[8])
        record.l1_result = L1Result(genre=Genre.QA_RIDDLE, tokens=[], lemmas=[], pos_tags=[])
        with pytest.raises(ValueError, match="l4_result"):
            resolve_l5(record, DEFAULT_SETTINGS)

    def test_qa_score_uses_correct_weights(self) -> None:
        """Verify the weighted score formula against known inputs."""
        record = _make_record(self._QA_TEXT, Genre.QA_RIDDLE, self._qa_l4())
        # All subscores = 1.0 → weighted sum must equal 1.0
        payload = json.dumps({k: 1.0 for k in DEFAULT_SETTINGS.L5_QA_WEIGHTS} | {"reasoning": "all max"})
        result = resolve_l5(
            record, DEFAULT_SETTINGS,
            ambiguous_term="guts", client=_mock_client([payload]),
        )
        assert isinstance(result, L5QAResult)
        assert abs(result.resolution_score - 1.0) < 1e-4

    def test_definitional_score_uses_correct_weights(self) -> None:
        record = _make_record(self._DEF_TEXT, Genre.DEFINITIONAL_ONELINER, self._definitional_l4())
        payload = json.dumps({k: 1.0 for k in _L5_DEFINITIONAL_WEIGHTS} | {"reasoning": "all max"})
        result = resolve_l5(
            record, DEFAULT_SETTINGS,
            ambiguous_term="autobiography", client=_mock_client([payload]),
        )
        assert isinstance(result, L5DefinitionalResult)
        assert abs(result.resolution_score - 1.0) < 1e-4

    def test_dialogue_score_uses_correct_weights(self) -> None:
        record = _make_record(self._DLG_TEXT, Genre.DIALOGUE_MISUNDERSTANDING, self._dialogue_l4())
        payload = json.dumps({k: 1.0 for k in _L5_DIALOGUE_WEIGHTS} | {"reasoning": "all max"})
        result = resolve_l5(
            record, DEFAULT_SETTINGS,
            ambiguous_term="pull yourself together", client=_mock_client([payload]),
        )
        assert isinstance(result, L5DialogueResult)
        assert abs(result.resolution_score - 1.0) < 1e-4


# ---------------------------------------------------------------------------
# Parameterised offline test against all six fixture items
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture", _load_fixtures(), ids=_fixture_ids())
def test_fixture_item_offline(fixture: dict[str, Any]) -> None:
    """Verifies branch selection and score routing for each fixture item.

    Mock scores are chosen to produce the expected_l5_status.  LLM judgment
    is NOT tested here — that is the live test's job.
    """
    l4 = _build_l4(fixture["l4_result"])
    genre = Genre(fixture["genre"])
    record = _make_record(fixture["text"], genre, l4, item_id=fixture["id"])
    expected = ResolutionStatus(fixture["expected_l5_status"])

    if l4.anchoring_status != AnchoringStatus.PASS:
        result = resolve_l5(
            record, DEFAULT_SETTINGS, ambiguous_term=fixture["ambiguous_term"]
        )
        assert result.resolution_status == expected
        return

    if expected == ResolutionStatus.RESOLUTION_PASS:
        score_val = 0.9
    else:
        score_val = 0.1

    if genre == Genre.QA_RIDDLE:
        keys = list(DEFAULT_SETTINGS.L5_QA_WEIGHTS.keys())
    elif genre == Genre.DEFINITIONAL_ONELINER:
        keys = list(_L5_DEFINITIONAL_WEIGHTS.keys())
    else:
        keys = list(_L5_DIALOGUE_WEIGHTS.keys())

    payload = json.dumps({k: score_val for k in keys} | {"reasoning": "mock"})
    result = resolve_l5(
        record, DEFAULT_SETTINGS,
        ambiguous_term=fixture["ambiguous_term"],
        client=_mock_client([payload]),
    )
    assert result.resolution_status == expected, (
        f"Fixture {fixture['id']}: expected {expected}, got {result.resolution_status}"
    )


# ---------------------------------------------------------------------------
# Live tests — real API calls, excluded from offline runs
# ---------------------------------------------------------------------------

@pytest.mark.live
@pytest.mark.parametrize("fixture", _load_fixtures(), ids=_fixture_ids())
def test_fixture_item_live(fixture: dict[str, Any]) -> None:
    """Run each fixture against the real Anthropic API.

    A verdict that differs from expected_l5_status is a valid calibration
    result.  This test asserts structure only, not correctness, so calibration
    data is not distorted by prompt-tuning for fixtures.
    """
    l4 = _build_l4(fixture["l4_result"])
    genre = Genre(fixture["genre"])
    record = _make_record(fixture["text"], genre, l4, item_id=fixture["id"])

    result = resolve_l5(
        record, DEFAULT_SETTINGS, ambiguous_term=fixture["ambiguous_term"]
    )
    assert result.resolution_status in ResolutionStatus
    assert isinstance(result.resolution_score, float)
    assert 0.0 <= result.resolution_score <= 1.0
    assert isinstance(result.subscores, dict)
