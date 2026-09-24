"""L1: surface analysis + genre routing. Regex only — no tagger, no LLM.

Routing order (first match wins):
  DIALOGUE_MISUNDERSTANDING  2+ speaker turns ("Name:" at text/sentence start)
  DEFINITIONAL_ONELINER      "Word:" / short head (<=3 words) + colon at start
  QA_RIDDLE                  starts with a wh-word and contains "?"
  DECLARATIVE                everything else

lemmas/pos_tags stay empty: regex can't lemmatize or tag; L2 lemmatizes
through WordNet morphy.
"""

from __future__ import annotations

import re

from .enums import Genre
from .schema import L1Result

_SPEAKER = re.compile(r"(?:^|[.!?]\s+)[A-Z][a-z]+:\s")
_DEFINITION = re.compile(r"^\s*[A-Z][\w'-]*(?:\s+[\w'-]+){0,2}:\s")
_WH_QUESTION = re.compile(r"^\s*(?:why|what|how|where|when|who|whom|whose|which)\b[^?]*\?", re.I)
_TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_NEGATION = re.compile(r"\b(?:not|no|never|nothing|nobody|none)\b|n't\b", re.I)


def route_genre(text: str) -> Genre:
    if len(_SPEAKER.findall(text)) >= 2:
        return Genre.DIALOGUE_MISUNDERSTANDING
    if _DEFINITION.match(text):
        return Genre.DEFINITIONAL_ONELINER
    if _WH_QUESTION.match(text):
        return Genre.QA_RIDDLE
    return Genre.DECLARATIVE


def analyze(text: str) -> L1Result:
    genre = route_genre(text)
    return L1Result(
        genre=genre,
        tokens=_TOKEN.findall(text),
        lemmas=[],
        pos_tags=[],
        has_question="?" in text,
        has_negation=bool(_NEGATION.search(text)),
        has_speaker_turns=genre == Genre.DIALOGUE_MISUNDERSTANDING,
    )
