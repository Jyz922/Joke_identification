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
from google.genai.errors import ServerError as _GeminiServerError
from pydantic import BaseModel, ConfigDict

from .config import Settings
from .enums import AnchorRelation, AnchoringStatus, Genre, ResolutionStatus
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


def _make_insufficient(
    genre: Genre,
    model_used: str = "",
    fallback_used: bool = False,
    retries: int = 0,
) -> L5Result:
    empty: dict[str, float] = {}
    kw = dict(model_used=model_used, fallback_used=fallback_used, retries=retries)
    if genre == Genre.QA_RIDDLE:
        return L5QAResult(
            genre=Genre.QA_RIDDLE,
            resolution_status=ResolutionStatus.INSUFFICIENT_CONTEXT,
            subscores=empty,
            **kw,
        )
    if genre == Genre.DEFINITIONAL_ONELINER:
        return L5DefinitionalResult(
            genre=Genre.DEFINITIONAL_ONELINER,
            resolution_status=ResolutionStatus.INSUFFICIENT_CONTEXT,
            subscores=empty,
            **kw,
        )
    return L5DialogueResult(
        genre=genre,
        resolution_status=ResolutionStatus.INSUFFICIENT_CONTEXT,
        subscores=empty,
        **kw,
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
    """One Gemini call; on 429 with a positive retryDelay waits and retries once.

    429 with retryDelay=0s or no retryDelay is non-retryable (daily quota / spend-cap)
    and raises RuntimeError immediately without sleeping.
    """
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
                if delay:  # positive seconds only — genuinely transient rate limit
                    time.sleep(delay)
                    continue
                raise RuntimeError(
                    f"Gemini quota exhausted (non-retryable, retryDelay=0): {err.message}"
                ) from err
            raise
    raise RuntimeError("unreachable")  # satisfies type checker


# Exponential backoff delays between 5xx retry attempts (seconds).
# _5XX_MAX = 5 total attempts per model → at most 4 sleeps using delays[0..3].
_5XX_DELAYS: tuple[int, ...] = (2, 4, 8, 16, 32)
_5XX_MAX: int = 5


def _call_gemini_single(
    prompt_text: str,
    response_model: type,
    required_keys: frozenset[str] | None,
    model: str,
    client: _genai.Client,
) -> tuple[dict[str, Any] | None, int, "_GeminiClientError | None"]:
    """One model: up to _5XX_MAX attempts with exponential backoff on 5xx.

    Returns (parsed, retries, last_5xx_err):
    - Success:           (dict, retries, None)
    - Parse failure:     (None, retries, None)
    - 5xx exhausted:     (None, retries, GeminiClientError)
    """
    config = _genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=response_model,
        temperature=0.0,
        max_output_tokens=512,
    )
    retries = 0
    last_5xx: _GeminiClientError | None = None

    for _5xx_attempt in range(_5XX_MAX):
        if _5xx_attempt > 0:
            delay = _5XX_DELAYS[_5xx_attempt - 1]
            _LOG.warning(
                "L5 5xx retry: model=%s attempt=%d/%d code=%d sleeping=%ds",
                model, _5xx_attempt + 1, _5XX_MAX,
                last_5xx.code if last_5xx else 0, delay,
            )
            time.sleep(delay)
            retries += 1

        try:
            for parse_attempt in range(2):
                suffix = "" if parse_attempt == 0 else _RETRY_SUFFIX
                response = _gemini_generate(client, model, prompt_text + suffix, config)
                raw: str = response.text
                try:
                    parsed = _extract_json(raw)
                    if required_keys:
                        _validate_keys(parsed, required_keys, parse_attempt, "gemini")
                    return parsed, retries, None
                except (json.JSONDecodeError, ValueError, IndexError):
                    if parse_attempt == 1:
                        return None, retries, None

        except _GeminiServerError as e:
            if e.code in (500, 502, 503, 504):
                last_5xx = e
                _LOG.warning(
                    "L5 5xx: model=%s attempt=%d/%d code=%d",
                    model, _5xx_attempt + 1, _5XX_MAX, e.code,
                )
            else:
                raise

    return None, retries, last_5xx


def _call_gemini_with_chain(
    prompt_text: str,
    response_model: type,
    required_keys: frozenset[str] | None,
    settings: Settings,
    client: _genai.Client | None,
) -> tuple[dict[str, Any] | None, str, bool, int]:
    """Try primary model then each fallback in chain on 5xx exhaustion.

    Returns (parsed, model_used, fallback_used, total_retries).
    Raises RuntimeError if all models exhaust their 5xx retries.
    Parse failure on any model returns (None, model, fallback_used, retries)
    without trying the fallback chain.
    """
    if client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        client = _genai.Client(api_key=api_key)

    models = [settings.L5_MODEL_GEMINI, *settings.L5_MODEL_GEMINI_CHAIN]
    total_retries = 0

    for model_idx, model in enumerate(models):
        parsed, retries, err_5xx = _call_gemini_single(
            prompt_text, response_model, required_keys, model, client
        )
        total_retries += retries

        if parsed is not None:
            return parsed, model, model_idx > 0, total_retries

        if err_5xx is None:
            # parse failure — don't try fallback, caller returns INSUFFICIENT_CONTEXT
            return None, model, model_idx > 0, total_retries

        # 5xx exhausted; try next model if available
        if model_idx < len(models) - 1:
            _LOG.warning(
                "L5 fallback switch: %s → %s (HTTP %d)",
                model, models[model_idx + 1], err_5xx.code,
            )
        else:
            raise RuntimeError(
                f"L5 Gemini: all models exhausted after retries, last HTTP {err_5xx.code}"
            ) from err_5xx

    raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------
# Backend dispatcher
# ---------------------------------------------------------------------------

def _complete_json(
    prompt: str,
    required_keys: frozenset[str],
    response_model: type,
    settings: Settings,
    client: Any,
) -> tuple[dict[str, Any] | None, str, bool, int]:
    """Returns (parsed, model_used, fallback_used, retries)."""
    if settings.L5_BACKEND == "gemini":
        return _call_gemini_with_chain(
            prompt, response_model, required_keys, settings, client
        )
    if settings.L5_BACKEND == "anthropic":
        result = _call_llm(prompt, client, required_keys=required_keys)
        return result, _MODEL, False, 0
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
        _LOG.warning(
            "L5 short-circuit: %s — anchoring_status=%s, no LLM call",
            record.item_id, l4.anchoring_status,
        )
        return _make_insufficient(genre)

    if (l4.sense_a_anchor_quote == l4.sense_b_anchor_quote
            and l4.anchor_relation != AnchorRelation.RESEGMENTATION):
        _LOG.warning(
            "L5 short-circuit: %s — identical anchor spans %r but anchor_relation=%s"
            " (RESEGMENTATION required for same-span anchors), no LLM call",
            record.item_id, l4.sense_a_anchor_quote, l4.anchor_relation,
        )
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

    parsed, model_used, fallback_used, retries = _complete_json(
        prompt, frozenset(weights), response_model, settings, client
    )
    if parsed is None:
        return _make_insufficient(
            genre, model_used=model_used, fallback_used=fallback_used, retries=retries
        )

    subscores = {k: float(parsed[k]) for k in weights}
    score = _weighted_score(subscores, weights)
    kw = dict(
        resolution_score=round(score, 4),
        subscores=subscores,
        model_used=model_used,
        fallback_used=fallback_used,
        retries=retries,
    )

    if genre == Genre.QA_RIDDLE:
        return L5QAResult(
            genre=Genre.QA_RIDDLE,
            resolution_status=_resolution_status(score, settings.L5_RESOLUTION_THRESHOLD),
            **kw,
        )
    if genre == Genre.DEFINITIONAL_ONELINER:
        return L5DefinitionalResult(
            genre=Genre.DEFINITIONAL_ONELINER,
            resolution_status=_resolution_status(score, settings.L5_RESOLUTION_THRESHOLD),
            **kw,
        )
    return L5DialogueResult(
        genre=genre,
        resolution_status=_resolution_status(score, settings.L5_RESOLUTION_THRESHOLD),
        **kw,
    )
