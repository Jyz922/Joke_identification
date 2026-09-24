"""L3: deterministic, AGE-FREE ambiguity-candidate ranking over L2 senses.

aoa_estimate is never read here (README deviation 1: age effects live in L7).

Every WordNet sense is credible; there is no frequency gate (SemCor is small
and hand-tagged: shingles, net-as-income, ex all have count 0).

score = W_CONTRAST * contrast + W_BALANCE * balance
  contrast (strong)  1.0 if two senses carry different WordNet lexname()s, else 0.
  balance  (weak)    (c2 + 1) / (c1 + 1): c1 = SemCor count of the top sense,
                     c2 = best count in a DIFFERENT lexname. Add-one smoothing, so
                     unseen-in-SemCor senses are neutral rather than disqualifying.
Contrast outweighs balance, so every contrastive term ranks above every
non-contrastive one.

Compound splits (source "wordnet_split:a+b"): contrast = a part's top lexname
differs from the whole word's; balance is between the two parts' top counts.

Multiword expressions (source "wordnet_mwe:<lemma>"): the idiomatic reading
(MWE senses) vs the literal readings of its content words. contrast = some
word's top lexname differs from the MWE's; balance is between the MWE's top
count and that word's.
"""

from __future__ import annotations

from collections import defaultdict

from .schema import CandidateEntry, L3Result, SenseEntry

W_CONTRAST = 0.7
W_BALANCE = 0.3


def _count(s: SenseEntry) -> int:
    return s.semcor_count or 0


def _top(senses: list[SenseEntry]) -> SenseEntry:
    # max() keeps the first of equal counts, i.e. WordNet's own sense order.
    return max(senses, key=_count)


def _entry(term: str, contrast: bool, c1: int, c2: int, split: bool) -> CandidateEntry:
    balance = (c2 + 1) / (c1 + 1) if contrast else 0.0
    return CandidateEntry(
        term=term,
        score=round(W_CONTRAST * contrast + W_BALANCE * balance, 4),
        score_components={
            "contrast": float(contrast), "balance": round(balance, 4),
            "top_count": float(c1), "contrast_count": float(c2),
            "compound_split": float(split),
        },
    )


def _homograph(term: str, whole: list[SenseEntry]) -> CandidateEntry:
    top = _top(whole)
    others = [s for s in whole if s.lexname != top.lexname]
    if not others:
        return _entry(term, False, _count(top), 0, split=False)
    return _entry(term, True, _count(top), _count(_top(others)), split=False)


def _split(term: str, source: str, whole: list[SenseEntry], parts: list[SenseEntry]) -> CandidateEntry | None:
    if not whole:
        return None
    tops = []
    # ponytail: a part-sense belongs to part p iff its lemma is p; a part WordNet
    # only knows by an inflected form ("pets") is dropped rather than guessed.
    for p in source.split(":", 1)[1].split("+"):
        mine = [s for s in parts if s.lemma.lower() == p]
        if not mine:
            return None
        tops.append(_top(mine))
    contrast = any(t.lexname != _top(whole).lexname for t in tops)
    c1, c2 = sorted((_count(t) for t in tops), reverse=True)
    return _entry(term, contrast, c1, c2, split=True)


def _mwe(phrase: str, mwe: list[SenseEntry], whole: dict[str, list[SenseEntry]]) -> CandidateEntry | None:
    words = [whole[w] for w in phrase.split() if w in whole]
    if not words:
        return None
    top = _top(mwe)
    literal = [_top(ss) for ss in words]
    contrasting = [t for t in literal if t.lexname != top.lexname]
    other = _top(contrasting) if contrasting else _top(literal)
    c1, c2 = sorted((_count(top), _count(other)), reverse=True)
    return _entry(phrase, bool(contrasting), c1, c2, split=False)


def rank(senses: list[SenseEntry], top_k: int) -> L3Result:
    whole: dict[str, list[SenseEntry]] = defaultdict(list)
    splits: dict[tuple[str, str], list[SenseEntry]] = defaultdict(list)
    mwes: dict[str, list[SenseEntry]] = defaultdict(list)
    for s in senses:
        if s.source == "wordnet":
            whole[s.term].append(s)
        elif s.source.startswith("wordnet_mwe:"):
            mwes[s.term].append(s)
        else:
            splits[(s.term, s.source)].append(s)
    cands = [_homograph(t, ss) for t, ss in whole.items()]
    cands += [c for (t, src), ss in splits.items() if (c := _split(t, src, whole[t], ss))]
    cands += [c for t, ss in mwes.items() if (c := _mwe(t, ss, whole))]
    cands.sort(key=lambda c: (-c.score, c.term))
    # One slot per term: a word can be both a homograph and a split (life ->
    # li + fe); keep its best-scoring reading so top-k holds k distinct terms.
    best: dict[str, CandidateEntry] = {}
    for c in cands:
        best.setdefault(c.term, c)
    return L3Result(candidates=list(best.values())[:top_k])
