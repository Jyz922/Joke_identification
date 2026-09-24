"""Regression test: missing LLM subscores must trigger retry and return INSUFFICIENT_CONTEXT.

RED test for issue d.  Before the fix, missing fields silently default to 0.0,
causing RESOLUTION_FAIL.  After the fix they trigger a retry then
INSUFFICIENT_CONTEXT with resolution_score=None.
"""
from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import pytest

from doubletake.config import DEFAULT_SETTINGS
from doubletake.enums import AnchorRelation, AnchoringStatus, Genre, ResolutionStatus
from doubletake.l5_resolution import resolve_l5
from doubletake.schema import AnalysisRecord, L1Result, L4Result

_QA_TEXT = "Why don't skeletons fight? They have no guts."
_QA_SUBSCORES = list(DEFAULT_SETTINGS.L5_QA_WEIGHTS.keys())


def _qa_record() -> AnalysisRecord:
    record = AnalysisRecord(item_id="d-test", text=_QA_TEXT, target_ages=[8])
    record.l1_result = L1Result(genre=Genre.QA_RIDDLE, tokens=[], lemmas=[], pos_tags=[])
    record.l4_result = L4Result(
        sense_a="courage",
        sense_a_anchor_quote="no guts",
        sense_b="internal organs",
        sense_b_anchor_quote="skeletons",
        anchor_relation=AnchorRelation.SEPARATE_CONTEXTS,
        anchoring_status=AnchoringStatus.PASS,
        resolving_sense="sense_a",
    )
    return record


def _client_always_omitting(field: str) -> MagicMock:
    """Mock client that always returns a response missing *field*.

    Mocks both backends so the same client object works regardless of which
    backend is active.  Only the active backend's mock is actually called.
    """
    complete = {k: 0.8 for k in DEFAULT_SETTINGS.L5_QA_WEIGHTS}
    incomplete = json.dumps({k: v for k, v in complete.items() if k != field})
    client = MagicMock()
    # Anthropic path
    r_anthropic = MagicMock()
    r_anthropic.content = [MagicMock(text=incomplete)]
    client.messages.create.return_value = r_anthropic
    # Gemini path
    r_gemini = MagicMock()
    r_gemini.text = incomplete
    client.models.generate_content.return_value = r_gemini
    return client


@pytest.mark.parametrize("missing_field", _QA_SUBSCORES)
def test_missing_qa_subscore_triggers_retry_and_insufficient_context(
    missing_field: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A response omitting a required subscore must:
    - trigger exactly one retry (two total LLM calls)
    - yield INSUFFICIENT_CONTEXT, not RESOLUTION_FAIL
    - set resolution_score to None, not 0.0
    - log the missing field name as a warning
    """
    record = _qa_record()
    client = _client_always_omitting(missing_field)
    with caplog.at_level(logging.WARNING, logger="doubletake.l5_resolution"):
        result = resolve_l5(record, DEFAULT_SETTINGS, ambiguous_term="guts", client=client)

    if DEFAULT_SETTINGS.L5_BACKEND == "gemini":
        call_count = client.models.generate_content.call_count
    else:
        call_count = client.messages.create.call_count
    assert call_count == 2, (
        f"Expected 2 LLM calls (initial + 1 retry), got {call_count}"
    )
    assert result.resolution_status == ResolutionStatus.INSUFFICIENT_CONTEXT, (
        f"Missing {missing_field!r} should yield INSUFFICIENT_CONTEXT, "
        f"got {result.resolution_status}"
    )
    assert result.resolution_score is None, (
        f"resolution_score must be None when fields are missing, "
        f"got {result.resolution_score}"
    )
    assert missing_field in caplog.text, (
        f"Expected {missing_field!r} in warning log, got: {caplog.text!r}"
    )
