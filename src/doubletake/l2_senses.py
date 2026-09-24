"""L2: deterministic sense retrieval — WordNet senses + SemCor counts + Kuperman AoA.

Data lives under <repo>/data/ (gitignored):
  - nltk_data/  WordNet 3.0, downloaded on first use.
  - aoa_kuperman.csv  produced by scripts/fetch_aoa.py (not auto-downloaded:
    the fetch pins a checksum and should be run deliberately).

SemCor tag counts come from WordNet's Lemma.count() (the cntlist WordNet
derives from the SemCor concordance); the raw SemCor corpus is not needed.

AoA join — the trap: Kuperman rates SURFACE forms ("banks", "ran" are unrated;
"bank" is rated), WordNet lemmas are base forms with "_" for spaces. A naive
dict lookup silently drops words. aoa_lookup() walks a fallback chain and
reports which stage matched, so a miss is visible downstream (L7), never silent:
  1. exact       lemma with "_" -> " "
  2. lowercase   case-folded ("Monday" vs "monday")
  3. lemmatized  AoA words indexed by their WordNet base form (min AoA wins)
  4. miss        aoa_estimate=None, aoa_match="miss"
"""

from __future__ import annotations

import csv
from collections import Counter
from functools import lru_cache
from pathlib import Path

import nltk

from .schema import SenseEntry

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
NLTK_DIR = DATA_DIR / "nltk_data"
AOA_CSV = DATA_DIR / "aoa_kuperman.csv"

AOA_STAGES = ("exact", "lowercase", "lemmatized", "miss")

# ponytail: hand list of function words; WordNet has senses for "have", "in",
# "it" etc. that would otherwise flood L3. Swap for a real stoplist if needed.
STOPWORDS = frozenset("""
a an the and or but if so as at by for from in into of on onto to with without
about over under up down out off than then there here this that these those
i me my mine you your yours he him his she her hers it its we us our they them
their what which who whom whose why how when where not no nor do does did done
be is am are was were been being have has had having will would shall should
can could may might must just very too also only own same such both each all
any some few more most other again once because until while don t s
""".split())


@lru_cache(maxsize=1)
def wordnet():
    """WordNet corpus reader; downloads to data/nltk_data on first use."""
    if str(NLTK_DIR) not in nltk.data.path:
        nltk.data.path.insert(0, str(NLTK_DIR))
    try:
        nltk.data.find("corpora/wordnet")
    except LookupError:
        nltk.download("wordnet", download_dir=str(NLTK_DIR), quiet=True, raise_on_error=True)
    from nltk.corpus import wordnet as wn
    return wn


@lru_cache(maxsize=1)
def _aoa_tables() -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """(exact, lowercase, lemmatized) AoA indexes built from the Kuperman CSV."""
    if not AOA_CSV.exists():
        raise FileNotFoundError(
            f"{AOA_CSV} missing — run `py -3.11 scripts/fetch_aoa.py` once."
        )
    wn = wordnet()
    exact: dict[str, float] = {}
    with AOA_CSV.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            exact[row["word"]] = float(row["aoa"])
    lower: dict[str, float] = {}
    lemma: dict[str, float] = {}
    for word, aoa in exact.items():
        lw = word.lower()
        lower[lw] = min(aoa, lower.get(lw, aoa))
        for pos in "nvar":
            base = wn.morphy(lw, pos)
            if base:
                lemma[base] = min(aoa, lemma.get(base, aoa))
    return exact, lower, lemma


def aoa_lookup(lemma: str) -> tuple[float | None, str]:
    """AoA for a WordNet lemma name, plus the fallback stage that matched."""
    exact, lower, lemmatized = _aoa_tables()
    w = lemma.replace("_", " ")
    if w in exact:
        return exact[w], "exact"
    lw = w.lower()
    if lw in lower:
        return lower[lw], "lowercase"
    if lw in lemmatized:
        return lemmatized[lw], "lemmatized"
    return None, "miss"


def aoa_coverage(lemmas) -> dict[str, float]:
    """Cumulative % of *lemmas* resolved by each fallback stage (plus 'miss')."""
    lemmas = list(lemmas)
    counts = Counter(aoa_lookup(l)[1] for l in lemmas)
    out, running = {}, 0
    for stage in AOA_STAGES[:-1]:
        running += counts[stage]
        out[stage] = 100 * running / len(lemmas)
    out["miss"] = 100 * counts["miss"] / len(lemmas)
    return out


def _base_forms(word: str) -> set[str]:
    wn = wordnet()
    w = word.lower()
    return {w} | {b for p in "nvar" if (b := wn.morphy(w, p))}


def senses_for(word: str, *, term: str | None = None, source: str = "wordnet") -> list[SenseEntry]:
    """One SenseEntry per WordNet synset of *word* (any POS)."""
    wn = wordnet()
    bases = _base_forms(word)
    out = []
    for syn in wn.synsets(word):
        lem = next((l for l in syn.lemmas() if l.name().lower() in bases), syn.lemmas()[0])
        aoa, stage = aoa_lookup(lem.name())
        out.append(SenseEntry(
            term=term or word,
            lemma=lem.name(),
            pos=syn.pos(),
            sense_id=syn.name(),
            definition=syn.definition(),
            example=(syn.examples() or [None])[0],
            aoa_estimate=aoa,
            aoa_match=stage,
            lexname=syn.lexname(),
            semcor_count=lem.count(),
            source=source,
        ))
    return out


def compound_splits(word: str, min_part: int = 2) -> list[tuple[str, str]]:
    """Two-way splits where both halves are WordNet lemmas (autobiography ->
    auto + biography). Exact lemma names only: wn.lemmas() skips morphy, so
    "lain" (-> lie) doesn't count as a part.
    ponytail: two-way only; recurse if a three-part split ever matters."""
    wn = wordnet()
    w = word.lower()
    return [
        (w[:i], w[i:])
        for i in range(min_part, len(w) - min_part + 1)
        if wn.lemmas(w[:i]) and wn.lemmas(w[i:])
    ]


def retrieve(tokens: list[str]) -> list[SenseEntry]:
    """Senses for every content token, plus part-senses for compound splits.

    Split-part senses keep term=<whole word> and source="wordnet_split:<a>+<b>".
    """
    out: list[SenseEntry] = []
    seen: set[str] = set()
    for tok in tokens:
        t = tok.lower()
        if t in seen or t in STOPWORDS or not t.isalpha():
            continue
        seen.add(t)
        out += senses_for(t)
        for a, b in compound_splits(t):
            src = f"wordnet_split:{a}+{b}"
            out += senses_for(a, term=t, source=src) + senses_for(b, term=t, source=src)
    return out


if __name__ == "__main__":
    # AoA coverage report over the whole WordNet vocabulary.
    wn = wordnet()
    all_names = {l.name() for s in wn.all_synsets() for l in s.lemmas()}
    single = {n for n in all_names if "_" not in n and "-" not in n}
    credible = {
        l.name() for s in wn.all_synsets() for l in s.lemmas()
        if l.count() > 0 and "_" not in l.name()
    }
    for label, pop in [
        ("all WordNet lemma names", all_names),
        ("single-word lemmas", single),
        ("single-word lemmas with semcor_count>0", credible),
    ]:
        cov = aoa_coverage(pop)
        print(f"{label} (n={len(pop)}): " + ", ".join(f"{k} {v:.1f}%" for k, v in cov.items()))
