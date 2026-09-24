"""L1 genre routing (regex only)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from doubletake.config import DEFAULT_SETTINGS
from doubletake.enums import Genre
from doubletake.l1_surface import analyze, route_genre
from doubletake.layers import run_l1
from doubletake.schema import AnalysisRecord

_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = [
    json.loads(l)
    for l in (_ROOT / "tests" / "fixtures" / "l5_anchors.jsonl").read_text(encoding="utf-8").splitlines()
    if l.strip()
]


@pytest.mark.parametrize("fx", _FIXTURES, ids=[f["id"] for f in _FIXTURES])
def test_fixture_genre(fx: dict) -> None:
    assert route_genre(fx["text"]) == Genre(fx["genre"])


@pytest.mark.parametrize("text,genre", [
    # colon after a long clause is not a definition
    ("Being in politics is just like playing golf: you are trapped in one bad lie after another.",
     Genre.DECLARATIVE),
    # question without a leading wh-word is not a riddle
    ("If con is the opposite of pro, then isn't Congress the opposite of progress?", Genre.DECLARATIVE),
    # one speaker colon is not a dialogue
    ("Doctor: take two aspirin.", Genre.DEFINITIONAL_ONELINER),
])
def test_routing_edge_cases(text: str, genre: Genre) -> None:
    assert route_genre(text) == genre


def _corpus(name: str) -> list[str]:
    d = json.loads((_ROOT / name).read_text(encoding="utf-8"))
    return d if isinstance(d, list) else list(d.values())[0]


def test_corpus_distribution() -> None:
    """Pins the routing of the real corpus (27 + 17 declarative)."""
    jokes = Counter(route_genre(t) for t in _corpus("jokes.json"))
    notjokes = Counter(route_genre(t) for t in _corpus("notjokes.json"))
    assert jokes == {Genre.DECLARATIVE: 27, Genre.QA_RIDDLE: 13}
    assert notjokes == {Genre.DECLARATIVE: 17, Genre.QA_RIDDLE: 3}


def test_analyze_surface_flags() -> None:
    r = analyze("Why don't skeletons fight? Because they have no guts.")
    assert r.tokens[:3] == ["Why", "don't", "skeletons"]
    assert r.has_question and r.has_negation and not r.has_speaker_turns


def test_run_l1_sets_result_and_trace() -> None:
    record = AnalysisRecord(item_id="t", text="The bank was steep.", target_ages=[8])
    record = run_l1(record, DEFAULT_SETTINGS)
    assert record.l1_result.genre == Genre.DECLARATIVE
    assert record.trace[-1].layer == "L1"
