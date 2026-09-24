"""L2 sense retrieval. Needs data/ (WordNet auto-downloads; AoA via
scripts/fetch_aoa.py) — no paid API."""

from __future__ import annotations

import pytest

from doubletake.l2_senses import aoa_coverage, aoa_lookup, compound_splits, retrieve, senses_for


@pytest.mark.parametrize("lemma,stage", [
    ("bank", "exact"),
    ("ACE", "lowercase"),          # AoA has only "ace"
    ("accredit", "lemmatized"),    # AoA has only "accredited"
    ("assets", "lemmatized"),      # query side lemmatized: AoA has only "asset"
    ("porkchop", "derived_from_parts"),       # compound: max(pork, chop)
    ("liquid_assets", "derived_from_parts"),  # MWE: max(liquid, asset)
    ("New_York", "miss"),
])
def test_aoa_fallback_stage(lemma: str, stage: str) -> None:
    aoa, got = aoa_lookup(lemma)
    assert got == stage
    assert (aoa is None) == (stage == "miss")


def test_aoa_coverage_is_cumulative() -> None:
    cov = aoa_coverage(["bank", "ACE", "accredit", "porkchop", "New_York"])
    assert cov == {"exact": 20.0, "lowercase": 40.0, "lemmatized": 60.0,
                   "derived_from_parts": 80.0, "miss": 20.0}


def test_derived_takes_the_later_learned_part() -> None:
    parts = [aoa_lookup(p)[0] for p in ("liquid", "assets")]
    assert aoa_lookup("liquid_assets")[0] == max(parts)


def test_senses_carry_lexname_semcor_and_aoa() -> None:
    senses = senses_for("guts")
    courage = next(s for s in senses if s.sense_id == "backbone.n.02")
    assert courage.lemma == "guts"
    assert courage.lexname == "noun.attribute"
    assert courage.semcor_count == 2
    assert courage.aoa_match == "exact" and courage.aoa_estimate is not None
    assert {"noun.body", "noun.attribute"} <= {s.lexname for s in senses}


def test_compound_split_autobiography_reachable() -> None:
    assert ("auto", "biography") in compound_splits("autobiography")
    # exact lemma names only: "lain" is an inflection of "lie", not a lemma
    assert ("exp", "lain") not in compound_splits("explain")


def test_retrieve_skips_stopwords_and_adds_split_senses() -> None:
    senses = retrieve(["The", "autobiography", "is", "autobiography"])
    assert {s.term for s in senses} == {"autobiography"}
    split = [s for s in senses if s.source == "wordnet_split:auto+biography"]
    assert {s.lemma for s in split} >= {"auto", "biography"}


def test_run_l2_populates_record_from_l1_tokens() -> None:
    from doubletake.config import DEFAULT_SETTINGS
    from doubletake.enums import Genre
    from doubletake.layers import run_l2
    from doubletake.schema import AnalysisRecord, L1Result

    record = AnalysisRecord(item_id="t", text="The trunk.", target_ages=[8])
    with pytest.raises(ValueError):
        run_l2(record, DEFAULT_SETTINGS)
    record.l1_result = L1Result(genre=Genre.DECLARATIVE, tokens=["The", "trunk"], lemmas=[], pos_tags=[])
    record = run_l2(record, DEFAULT_SETTINGS)
    assert record.l2_result.senses and {s.term for s in record.l2_result.senses} == {"trunk"}
    assert record.trace[-1].layer == "L2"


def test_mwe_scan_handles_reflexive_and_inflection() -> None:
    from doubletake.l2_senses import mwe_spans
    assert mwe_spans(["Pull", "yourself", "together"]) == [("Pull yourself together", "pull_together")]
    assert ("going after", "go_after") in mwe_spans(["going", "after", "liquid", "assets"])
    assert ("liquid assets", "liquid_assets") in mwe_spans(["going", "after", "liquid", "assets"])


def test_mwe_scan_skips_function_word_only_grams() -> None:
    from doubletake.l2_senses import mwe_spans
    assert mwe_spans(["at", "all"]) == []  # at_all is a WordNet lemma


def test_retrieve_tags_mwe_senses() -> None:
    senses = retrieve(["liquid", "assets"])
    mwe = [s for s in senses if s.source == "wordnet_mwe:liquid_assets"]
    assert mwe and {s.term for s in mwe} == {"liquid assets"}
