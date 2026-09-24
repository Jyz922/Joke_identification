"""L3: deterministic, AGE-FREE ambiguity-candidate ranking over L2 senses.

aoa_estimate is never read here (README deviation 1: age effects live in L7).

Credible sense  = semcor_count > 0.
Domain contrast = two credible senses with different WordNet lexname().
Gap             = |c1 - c2| / (c1 + c2), c1 = top credible count,
                  c2 = best credible count in a DIFFERENT lexname than c1's.
score = 1 - gap: a term whose two readings are about equally common ranks
first; a term whose second reading is vanishingly rare ranks last.

Compound splits (source "wordnet_split:a+b"): both parts need a credible
sense; contrast = a part's top lexname differs from the whole word's; gap is
between the two parts' top counts. NOT whole-vs-split: rare whole words
(autobiography: count 0) would always score 0 and never reach top-k, though
the whole word's rarity says nothing about whether the split reading is live.
"""

from __future__ import annotations

from collections import defaultdict

from .schema import CandidateEntry, L3Result, SenseEntry


def _count(s: SenseEntry) -> int:
    return s.semcor_count or 0


def _entry(term: str, c1: int, c2: int, split: bool) -> CandidateEntry:
    gap = abs(c1 - c2) / (c1 + c2)
    return CandidateEntry(term=term, score=round(1 - gap, 4), score_components={
        "top_count": float(c1), "contrast_count": float(c2),
        "gap": round(gap, 4), "compound_split": float(split),
    })


def _homograph(term: str, whole: list[SenseEntry]) -> CandidateEntry | None:
    credible = [s for s in whole if _count(s) > 0]
    if not credible:
        return None
    top = max(credible, key=_count)
    others = [s for s in credible if s.lexname != top.lexname]
    if not others:
        return None
    return _entry(term, _count(top), _count(max(others, key=_count)), split=False)


def _split(term: str, source: str, whole: list[SenseEntry], parts: list[SenseEntry]) -> CandidateEntry | None:
    if not whole:
        return None
    whole_top = max(whole, key=_count)
    tops = []
    # ponytail: a part-sense belongs to part p iff its lemma is p; a part WordNet
    # only knows by an inflected form ("pets") is dropped rather than guessed.
    for p in source.split(":", 1)[1].split("+"):
        credible = [s for s in parts if s.lemma.lower() == p and _count(s) > 0]
        if not credible:
            return None
        tops.append(max(credible, key=_count))
    if all(t.lexname == whole_top.lexname for t in tops):
        return None
    c1, c2 = sorted((_count(t) for t in tops), reverse=True)
    return _entry(term, c1, c2, split=True)


def rank(senses: list[SenseEntry], top_k: int) -> L3Result:
    whole: dict[str, list[SenseEntry]] = defaultdict(list)
    splits: dict[tuple[str, str], list[SenseEntry]] = defaultdict(list)
    for s in senses:
        if s.source == "wordnet":
            whole[s.term].append(s)
        else:
            splits[(s.term, s.source)].append(s)
    cands = [c for t, ss in whole.items() if (c := _homograph(t, ss))]
    cands += [c for (t, src), ss in splits.items() if (c := _split(t, src, whole[t], ss))]
    cands.sort(key=lambda c: (-c.score, c.term))
    return L3Result(candidates=cands[:top_k])
