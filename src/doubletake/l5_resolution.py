"""L5: form-specific semantic resolution via LLM scoring."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import anthropic

_LOG = logging.getLogger(__name__)

from .config import Settings
from .enums import AnchoringStatus, Genre, ResolutionStatus
from .schema import (
    AnalysisRecord,
    L5DefinitionalResult,
    L5DialogueResult,
    L5QAResult,
    L5Result,
)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_MODEL = "claude-sonnet-4-6"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")

# Weights for branches not covered by settings.L5_QA_WEIGHTS.
# Each dict must sum to 1.0.
_L5_DEFINITIONAL_WEIGHTS: dict[str, float] = {
    "setup_invites_literal": 0.30,
    "punchline_exploits_split": 0.40,
    "contrast_strength": 0.30,
}
_L5_DIALOGUE_WEIGHTS: dict[str, float] = {
    "misunderstanding_plausible": 0.40,
    "contrast_clear": 0.35,
    "speaker_intention_clear": 0.25,
}

_GENRE_TO_PROMPT: dict[Genre, str] = {
    Genre.QA_RIDDLE: "l5_qa.md",
    Genre.DEFINITIONAL_ONELINER: "l5_definitional.md",
    Genre.DIALOGUE_MISUNDERSTANDING: "l5_dialogue.md",
    Genre.DECLARATIVE: "l5_dialogue.md",
}


def _load_prompt(genre: Genre) -> str:
    return (_PROMPTS_DIR / _GENRE_TO_PROMPT[genre]).read_text(encoding="utf-8")


def _extract_json(text: str) -> dict[str, Any]:
    """Parse JSON from LLM response, stripping markdown code fences if present."""
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fence:
        return json.loads(fence.group(1))
    return json.loads(text.strip())


def _call_llm(
    prompt_text: str,
    client: anthropic.Anthropic | None = None,
    *,
    required_keys: frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """Call the LLM; on JSON parse or missing-field failure retry once; return None on second failure."""
    if client is None:
        client = anthropic.Anthropic()

    for attempt in range(2):
        suffix = (
            ""
            if attempt == 0
            else (
                "\n\nIMPORTANT: Your previous response could not be parsed as JSON"
                " or was missing required fields."
                " Return ONLY a valid JSON object with no surrounding text."
            )
        )
        response = client.messages.create(
            model=_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt_text + suffix}],
        )
        raw: str = response.content[0].text
        try:
            parsed = _extract_json(raw)
            if required_keys:
                missing = required_keys - parsed.keys()
                if missing:
                    for field in sorted(missing):
                        _LOG.warning(
                            "L5 response missing required field %r (attempt %d)",
                            field, attempt,
                        )
                    raise ValueError(f"Missing required fields: {sorted(missing)}")
            return parsed
        except (json.JSONDecodeError, ValueError, IndexError):
            if attempt == 1:
                return None

    return None  # unreachable; satisfies type checker


def _weighted_score(subscores: dict[str, float], weights: dict[str, float]) -> float:
    return sum(subscores.get(k, 0.0) * w for k, w in weights.items())


def _resolution_status(score: float, threshold: float) -> ResolutionStatus:
    return (
        ResolutionStatus.RESOLUTION_PASS
        if score >= threshold
        else ResolutionStatus.RESOLUTION_FAIL
    )


def _make_insufficient(genre: Genre) -> L5Result:
    empty: dict[str, float] = {}
    if genre == Genre.QA_RIDDLE:
        return L5QAResult(
            genre=Genre.QA_RIDDLE,
            resolution_status=ResolutionStatus.INSUFFICIENT_CONTEXT,
            subscores=empty,
        )
    if genre == Genre.DEFINITIONAL_ONELINER:
        return L5DefinitionalResult(
            genre=Genre.DEFINITIONAL_ONELINER,
            resolution_status=ResolutionStatus.INSUFFICIENT_CONTEXT,
            subscores=empty,
        )
    return L5DialogueResult(
        genre=genre,
        resolution_status=ResolutionStatus.INSUFFICIENT_CONTEXT,
        subscores=empty,
    )


def resolve_l5(
    record: AnalysisRecord,
    settings: Settings,
    *,
    ambiguous_term: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> L5Result:
    """Compute the L5 resolution result for *record*.

    ambiguous_term: explicit override used in tests; if None, derived from
        l3_result candidates or falls back to sense_a_anchor_quote.
    client: injectable Anthropic client; if None, a default client is created.

    Raises ValueError if l1_result or l4_result is absent (L1 and L4 must
    have run before L5).
    """
    if record.l1_result is None:
        raise ValueError("L1 must run before L5: l1_result is None")
    if record.l4_result is None:
        raise ValueError("L4 must run before L5: l4_result is None")

    genre = record.l1_result.genre
    l4 = record.l4_result

    if l4.anchoring_status != AnchoringStatus.PASS:
        return _make_insufficient(genre)

    term = ambiguous_term
    if term is None and record.l3_result and record.l3_result.candidates:
        term = record.l3_result.candidates[0].term
    if term is None:
        term = l4.sense_a_anchor_quote

    template = _load_prompt(genre)
    variables = {
        "text": record.text,
        "ambiguous_term": term,
        "sense_a": l4.sense_a,
        "sense_a_anchor_quote": l4.sense_a_anchor_quote,
        "sense_b": l4.sense_b,
        "sense_b_anchor_quote": l4.sense_b_anchor_quote,
        "anchor_relation": (
            str(l4.anchor_relation) if l4.anchor_relation is not None else "unknown"
        ),
    }
    prompt = _PLACEHOLDER.sub(lambda m: variables.get(m.group(1), m.group(0)), template)

    if genre == Genre.QA_RIDDLE:
        weights: dict[str, float] = settings.L5_QA_WEIGHTS
    elif genre == Genre.DEFINITIONAL_ONELINER:
        weights = _L5_DEFINITIONAL_WEIGHTS
    else:
        weights = _L5_DIALOGUE_WEIGHTS

    parsed = _call_llm(prompt, client=client, required_keys=frozenset(weights))
    if parsed is None:
        return _make_insufficient(genre)

    subscores = {k: float(parsed[k]) for k in weights}
    score = _weighted_score(subscores, weights)

    if genre == Genre.QA_RIDDLE:
        return L5QAResult(
            genre=Genre.QA_RIDDLE,
            resolution_status=_resolution_status(score, settings.L5_RESOLUTION_THRESHOLD),
            resolution_score=round(score, 4),
            subscores=subscores,
        )
    if genre == Genre.DEFINITIONAL_ONELINER:
        return L5DefinitionalResult(
            genre=Genre.DEFINITIONAL_ONELINER,
            resolution_status=_resolution_status(score, settings.L5_RESOLUTION_THRESHOLD),
            resolution_score=round(score, 4),
            subscores=subscores,
        )
    return L5DialogueResult(
        genre=genre,
        resolution_status=_resolution_status(score, settings.L5_RESOLUTION_THRESHOLD),
        resolution_score=round(score, 4),
        subscores=subscores,
    )
