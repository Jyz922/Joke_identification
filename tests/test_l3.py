"""L3 candidate ranking — deterministic and age-free."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from doubletake.config import DEFAULT_SETTINGS
from doubletake.l1_surface import analyze
from doubletake.l2_senses import retrieve
from doubletake.l3_candidates import rank
from doubletake.layers import run_l1, run_l2, run_l3
from doubletake.schema import AnalysisRecord

_FIXTURES = {
    (x := json.loads(l))["id"]: x
    for l in (Path(__file__).parent / "fixtures" / "l5_anchors.jsonl").read_text(encoding="utf-8").splitlines()
    if l.strip()
}


def _top3(fid: str) -> list[str]:
    fx = _FIXTURES[fid]
    return [c.term for c in rank(retrieve(analyze(fx["text"]).tokens), 3).candidates]


@pytest.mark.parametrize("fid", ["S1", "S2", "E1", "X1", "A1", "P1", "N1"])
def test_gold_term_in_top3(fid: str) -> None:
    assert _FIXTURES[fid]["ambiguous_term"].lower() in _top3(fid)


@pytest.mark.parametrize("fid", ["D1", "P2", "P3"])
def test_known_unreachable(fid: str) -> None:
    """Pinned limitation: shingles/ex have semcor_count 0 on every sense;
    'pull yourself together' is multiword. If this starts failing, L3 got
    better — move the id to the list above."""
    assert _FIXTURES[fid]["ambiguous_term"].lower() not in _top3(fid)


def test_ranking_is_age_free() -> None:
    senses = retrieve(analyze(_FIXTURES["E1"]["text"]).tokens)
    shifted = [s.model_copy(update={"aoa_estimate": 99.0}) for s in senses]
    assert rank(senses, 3) == rank(shifted, 3)


def test_compound_split_candidate_flagged() -> None:
    fx = _FIXTURES["A1"]
    cands = rank(retrieve(analyze(fx["text"]).tokens), 3).candidates
    auto = next(c for c in cands if c.term == "autobiography")
    assert auto.score_components["compound_split"] == 1.0


def test_run_l3_respects_top_k() -> None:
    record = AnalysisRecord(item_id="t", text=_FIXTURES["P3"]["text"], target_ages=[8])
    for layer in (run_l1, run_l2, run_l3):
        record = layer(record, DEFAULT_SETTINGS)
    assert len(record.l3_result.candidates) == DEFAULT_SETTINGS.L3_TOP_K
    assert record.trace[-1].layer == "L3"
