"""L5: form-specific semantic resolution via LLM scoring."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import anthropic
import google.genai as _genai
import google.genai.types as _genai_types
from google.genai.errors import ClientError as _GeminiClientError
from pydantic import BaseModel, ConfigDict

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
_MODEL = "claude-sonnet-4-6"  # Anthropic model; kept for anthropic backend
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_LOG = logging.getLogger(__name__)

_RETRY_SUFFIX = (
    "\n\nIMPORTANT: Your previous response could not be parsed as JSON"
    " or was missing required fields."
    " Return ONLY a valid JSON object with no surrounding text."
)

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


# ---------------------------------------------------------------------------
# Pydantic response models — used as Gemini response_schema.
# The SDK calls model_json_schema() and handles $defs / field conversion.
# extra="ignore" so any extra LLM fields (e.g. reasoning) don't fail validation.
# ---------------------------------------------------------------------------

class _QALLMResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    polarity_or_direction: float
    answer_relevance: float
    causal: float
    agent: float
    tense_aspect: float


class _DefinitionalLLMResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    setup_invites_literal: float
    punchline_exploits_split: float
    contrast_strength: float


class _DialogueLLMResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    misunderstanding_plausible: float
    contrast_clear: float
    speaker_intention_clear: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_prompt(genre: Genre) -> str:
    return (_PROMPTS_DIR / _GENRE_TO_PROMPT[genre]).read_text(encoding="utf-8")


def _extract_json(text: str) -> dict[str, Any]:
    """Parse JSON from LLM response, stripping markdown code fences if present."""
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fence:
        return json.loads(fence.group(1))
    return json.loads(text.strip())


def _validate_keys(
    parsed: dict[str, Any],
    required_keys: frozenset[str],
    attempt: int,
    backend: str,
) -> None:
    """Raise ValueError and log warnings if any required key is absent."""
    missing = required_keys - parsed.keys()
    if missing:
        for field in sorted(missing):
            _LOG.warning(
                "L5 %s response missing required field %r (attempt %d)",
                backend, field, attempt,
            )
        raise ValueError(f"Missing required fields: {sorted(missing)}")


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


# ---------------------------------------------------------------------------
# Anthropic backend
# ---------------------------------------------------------------------------

def _call_llm(
    prompt_text: str,
    client: anthropic.Anthropic | None = None,
    *,
    required_keys: frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """Anthropic path: retry once on JSON-parse or missing-field failure."""
    if client is None:
        client = anthropic.Anthropic()

    for attempt in range(2):
        suffix = "" if attempt == 0 else _RETRY_SUFFIX
        response = client.messages.create(
            model=_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt_text + suffix}],
        )
        raw: str = response.content[0].text
        try:
            parsed = _extract_json(raw)
            if required_keys:
                _validate_keys(parsed, required_keys, attempt, "anthropic")
            return parsed
        except (json.JSONDecodeError, ValueError, IndexError):
            if attempt == 1:
                return None

    return None  # unreachable


# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------

def _is_spend_cap_error(err: _GeminiClientError) -> bool:
    msg = (err.message or "").lower()
    return "limit: 0" in msg or "spend cap" in msg or "budget" in msg


def _extract_retry_delay(err: _GeminiClientError) -> float | None:
    """Return the retryDelay in seconds from a 429 error body, or None."""
    try:
        details = err.details  # dict or list
        details_list: list = []
        if isinstance(details, dict):
            details_list = details.get("error", {}).get("details", [])
        elif isinstance(details, list):
            details_list = details
        for item in details_list:
            if isinstance(item, dict) and "retryDelay" in item:
                return float(str(item["retryDelay"]).rstrip("s"))
    except Exception:
        pass
    return None


def _gemini_generate(
    client: _genai.Client,
    model: str,
    contents: str,
    config: _genai_types.GenerateContentConfig,
) -> _genai_types.GenerateContentResponse:
    """One Gemini call; on 429+retryDelay waits and retries once."""
    for _try in range(2):
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except _GeminiClientError as err:
            if err.code == 429 and _try == 0:
                if _is_spend_cap_error(err):
                    raise RuntimeError(
                        f"Gemini spend cap or zero-quota (non-transient): {err.message}"
                    ) from err
                delay = _extract_retry_delay(err)
                if delay is not None:
                    time.sleep(delay)
                    continue
            raise
    raise RuntimeError("unreachable")  # satisfies type checker


def _call_gemini(
    prompt_text: str,
    response_model: type,
    required_keys: frozenset[str] | None,
    model: str,
    client: _genai.Client | None = None,
) -> dict[str, Any] | None:
    """Gemini path: schema-constrained JSON, temperature=0, retry once on failure."""
    if client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        client = _genai.Client(api_key=api_key)

    config = _genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=response_model,
        temperature=0.0,
        max_output_tokens=512,
    )

    for attempt in range(2):
        suffix = "" if attempt == 0 else _RETRY_SUFFIX
        response = _gemini_generate(client, model, prompt_text + suffix, config)
        raw: str = response.text
        try:
            parsed = _extract_json(raw)
            if required_keys:
                _validate_keys(parsed, required_keys, attempt, "gemini")
            return parsed
        except (json.JSONDecodeError, ValueError, IndexError):
            if attempt == 1:
                return None

    return None  # unreachable


# ---------------------------------------------------------------------------
# Backend dispatcher
# ---------------------------------------------------------------------------

def _complete_json(
    prompt: str,
    required_keys: frozenset[str],
    response_model: type,
    settings: Settings,
    client: Any,
) -> dict[str, Any] | None:
    if settings.L5_BACKEND == "gemini":
        return _call_gemini(
            prompt, response_model, required_keys, settings.L5_MODEL_GEMINI, client
        )
    if settings.L5_BACKEND == "anthropic":
        return _call_llm(prompt, client, required_keys=required_keys)
    raise ValueError(f"Unknown L5_BACKEND: {settings.L5_BACKEND!r}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_l5(
    record: AnalysisRecord,
    settings: Settings,
    *,
    ambiguous_term: str | None = None,
    client: Any = None,
) -> L5Result:
    """Compute the L5 resolution result for *record*.

    ambiguous_term: explicit override used in tests; if None, derived from
        l3_result candidates or falls back to sense_a_anchor_quote.
    client: injectable backend client (anthropic.Anthropic or google.genai.Client);
        if None, the appropriate client is created from the environment.

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
        response_model: type = _QALLMResponse
    elif genre == Genre.DEFINITIONAL_ONELINER:
        weights = _L5_DEFINITIONAL_WEIGHTS
        response_model = _DefinitionalLLMResponse
    else:
        weights = _L5_DIALOGUE_WEIGHTS
        response_model = _DialogueLLMResponse

    parsed = _complete_json(prompt, frozenset(weights), response_model, settings, client)
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
