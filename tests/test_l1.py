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


def test_curly_apostrophe_stays_in_token() -> None:
    r = analyze("We couldn’t imagine it.")
    assert r.tokens[:2] == ["We", "couldn’t"]
    assert r.has_negation


def test_run_l1_sets_result_and_trace() -> None:
    record = AnalysisRecord(item_id="t", text="The bank was steep.", target_ages=[8])
    record = run_l1(record, DEFAULT_SETTINGS)
    assert record.l1_result.genre == Genre.DECLARATIVE
    assert record.trace[-1].layer == "L1"


# Real strings from jokes.json, which uses U+2019 (’), not ASCII '.
_CURLY = [t for t in _corpus("jokes.json") if "’" in t]


def test_corpus_really_uses_curly_apostrophes() -> None:
    assert len(_CURLY) == 3


@pytest.mark.parametrize("text", _CURLY)
def test_curly_and_ascii_apostrophes_analyze_identically(text: str) -> None:
    curly, ascii_ = analyze(text), analyze(text.replace("’", "'"))
    assert curly.genre == ascii_.genre
    assert curly.has_negation == ascii_.has_negation
    assert [t.replace("’", "'") for t in curly.tokens] == ascii_.tokens


def test_negation_on_real_curly_strings() -> None:
    by_word = {w: t for t in _CURLY for w in ("couldn’t", "isn’t", "Dan’s") if w in t}
    assert analyze(by_word["couldn’t"]).has_negation
    assert analyze(by_word["isn’t"]).has_negation
    assert not analyze(by_word["Dan’s"]).has_negation  # possessive, not negation


def test_definition_head_with_curly_apostrophe() -> None:
    assert route_genre("Cat’s cradle: a game of string.") == Genre.DEFINITIONAL_ONELINER
