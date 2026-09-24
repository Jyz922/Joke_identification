"""L5: form-specific semantic resolution via LLM scoring."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, NamedTuple

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
    L4Result,
    L5DeclarativeResult,
    L5DefinitionalResult,
    L5DialogueResult,
    L5QAResult,
    L5Result,
)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
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
# Modelled on the definitional branch (punchline-sense term weighted highest).
# UNVALIDATED: no declarative fixture has been run live yet.
_L5_DECLARATIVE_WEIGHTS: dict[str, float] = {
    "both_readings_available": 0.30,
    "punchline_sense_is_unexpected": 0.40,
    "incongruity_present": 0.30,
}

_GENRE_TO_PROMPT: dict[Genre, str] = {
    Genre.QA_RIDDLE: "l5_qa.md",
    Genre.DEFINITIONAL_ONELINER: "l5_definitional.md",
    Genre.DIALOGUE_MISUNDERSTANDING: "l5_dialogue.md",
    Genre.DECLARATIVE: "l5_declarative.md",
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


class _DeclarativeLLMResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    both_readings_available: float
    punchline_sense_is_unexpected: float
    incongruity_present: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_prompt(genre: Genre) -> str:
    return (_PROMPTS_DIR / _GENRE_TO_PROMPT[genre]).read_text(encoding="utf-8")


def _render_prompt(genre: Genre, text: str, term: str, l4: L4Result) -> str:
    """Fill the genre template. {resolving_sense}/{other_sense} are chosen via
    l4.resolving_sense, so prompts never depend on sense_a/sense_b order."""
    res, other = (
        ("sense_a", "sense_b") if l4.resolving_sense == "sense_a" else ("sense_b", "sense_a")
    )
    variables = {
        "text": text,
        "ambiguous_term": term,
        "sense_a": l4.sense_a,
        "sense_a_anchor_quote": l4.sense_a_anchor_quote,
        "sense_b": l4.sense_b,
        "sense_b_anchor_quote": l4.sense_b_anchor_quote,
        "resolving_sense": getattr(l4, res),
        "resolving_sense_anchor_quote": getattr(l4, f"{res}_anchor_quote"),
        "other_sense": getattr(l4, other),
        "other_sense_anchor_quote": getattr(l4, f"{other}_anchor_quote"),
        "anchor_relation": (
            str(l4.anchor_relation) if l4.anchor_relation is not None else "unknown"
        ),
    }
    return _PLACEHOLDER.sub(lambda m: variables.get(m.group(1), m.group(0)), _load_prompt(genre))


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


class _L5Call(NamedTuple):
    """Outcome of a completed L5 model round-trip, before result construction."""
    parsed: dict[str, Any] | None
    model_used: str
    fallback_used: bool
    retries: int
    truncated: bool = False          # finish_reason == MAX_TOKENS
    thoughts_tokens: int | None = None


def _thoughts_tokens(response: Any) -> int | None:
    um = getattr(response, "usage_metadata", None)
    return getattr(um, "thoughts_token_count", None) if um is not None else None


def _empty_result(
    genre: Genre,
    *,
    status: ResolutionStatus = ResolutionStatus.INSUFFICIENT_CONTEXT,
    model_used: str = "",
    fallback_used: bool = False,
    retries: int = 0,
) -> L5Result:
    """Build an empty (no-subscore) L5 result carrying *status*.

    Used for both INSUFFICIENT_CONTEXT (short-circuit / unparseable) and
    TRUNCATED_OUTPUT (MAX_TOKENS) — resolution_score stays None either way.
    """
    empty: dict[str, float] = {}
    kw = dict(model_used=model_used, fallback_used=fallback_used, retries=retries)
    if genre == Genre.QA_RIDDLE:
        return L5QAResult(
            genre=Genre.QA_RIDDLE,
            resolution_status=status,
            subscores=empty,
            **kw,
        )
    if genre == Genre.DEFINITIONAL_ONELINER:
        return L5DefinitionalResult(
            genre=Genre.DEFINITIONAL_ONELINER,
            resolution_status=status,
            subscores=empty,
            **kw,
        )
    if genre == Genre.DECLARATIVE:
        return L5DeclarativeResult(
            genre=Genre.DECLARATIVE,
            resolution_status=status,
            subscores=empty,
            **kw,
        )
    return L5DialogueResult(
        genre=genre,
        resolution_status=status,
        subscores=empty,
        **kw,
    )


# ---------------------------------------------------------------------------
# Anthropic backend
# ---------------------------------------------------------------------------

def _call_llm(
    prompt_text: str,
    model: str,
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
            model=model,
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
    max_output_tokens: int,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, int, "_GeminiClientError | None", bool, int | None]:
    """One model: up to _5XX_MAX attempts with exponential backoff on 5xx.

    Returns (parsed, retries, last_5xx_err, truncated, thoughts_tokens):
    - Success:           (dict, retries, None, False, thoughts)
    - Truncated:         (None, retries, None, True, thoughts)   finish_reason=MAX_TOKENS
    - Parse failure:     (None, retries, None, False, thoughts)
    - 5xx exhausted:     (None, retries, GeminiClientError, False, None)

    Truncation returns immediately without a parse retry: a cut-off response is
    not a parse problem, and retrying the same prompt just truncates again.
    """
    config = _genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=response_model,
        temperature=0.0,
        max_output_tokens=max_output_tokens,
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
                thoughts = _thoughts_tokens(response)
                _cand = response.candidates[0] if response.candidates else None
                _finish = getattr(_cand, "finish_reason", None) if _cand is not None else None
                if diagnostics is not None:
                    # Persist the model's ACTUAL response so failed parses are
                    # not silently discarded (last attempt wins).
                    diagnostics["raw_text"] = raw if raw is not None else ""
                    diagnostics["finish_reason"] = str(_finish) if _finish is not None else ""
                    diagnostics["thoughts_tokens"] = thoughts

                if _finish == _genai_types.FinishReason.MAX_TOKENS:
                    # Cut off before emitting complete JSON — surface distinctly,
                    # do NOT parse or retry (would just truncate again).
                    return None, retries, None, True, thoughts

                try:
                    parsed = _extract_json(raw)
                    if required_keys:
                        _validate_keys(parsed, required_keys, parse_attempt, "gemini")
                    return parsed, retries, None, False, thoughts
                except (json.JSONDecodeError, ValueError, IndexError):
                    if parse_attempt == 1:
                        return None, retries, None, False, thoughts

        except _GeminiServerError as e:
            if e.code in (500, 502, 503, 504):
                last_5xx = e
                _LOG.warning(
                    "L5 5xx: model=%s attempt=%d/%d code=%d",
                    model, _5xx_attempt + 1, _5XX_MAX, e.code,
                )
            else:
                raise

    return None, retries, last_5xx, False, None


def _call_gemini_with_chain(
    prompt_text: str,
    response_model: type,
    required_keys: frozenset[str] | None,
    settings: Settings,
    client: _genai.Client | None,
    diagnostics: dict[str, Any] | None = None,
) -> _L5Call:
    """Try primary model then each fallback in chain on 5xx exhaustion.

    Raises RuntimeError if all models exhaust their 5xx retries.
    Parse failure or truncation on any model returns immediately without trying
    the fallback chain (neither is fixed by switching models).
    """
    if client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        client = _genai.Client(api_key=api_key)

    models = [settings.L5_MODEL_GEMINI, *settings.L5_MODEL_GEMINI_CHAIN]
    total_retries = 0

    for model_idx, model in enumerate(models):
        parsed, retries, err_5xx, truncated, thoughts = _call_gemini_single(
            prompt_text, response_model, required_keys, model, client,
            settings.L5_MAX_OUTPUT_TOKENS, diagnostics,
        )
        total_retries += retries
        fallback_used = model_idx > 0

        if truncated:
            return _L5Call(None, model, fallback_used, total_retries, True, thoughts)

        if parsed is not None:
            return _L5Call(parsed, model, fallback_used, total_retries, False, thoughts)

        if err_5xx is None:
            # parse failure — don't try fallback, caller returns INSUFFICIENT_CONTEXT
            return _L5Call(None, model, fallback_used, total_retries, False, thoughts)

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
    diagnostics: dict[str, Any] | None = None,
) -> _L5Call:
    if settings.L5_BACKEND == "gemini":
        return _call_gemini_with_chain(
            prompt, response_model, required_keys, settings, client, diagnostics
        )
    if settings.L5_BACKEND == "anthropic":
        result = _call_llm(prompt, settings.L5_MODEL_ANTHROPIC, client, required_keys=required_keys)
        return _L5Call(result, settings.L5_MODEL_ANTHROPIC, False, 0)
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
    diagnostics: dict[str, Any] | None = None,
) -> L5Result:
    """Compute the L5 resolution result for *record*.

    ambiguous_term: explicit override used in tests; if None, derived from
        l3_result candidates or falls back to sense_a_anchor_quote.
    client: injectable backend client (anthropic.Anthropic or google.genai.Client);
        if None, the appropriate client is created from the environment.
    diagnostics: optional dict sink; if provided, the Gemini path fills it with
        "raw_text" (verbatim response.text of the last model call) and
        "finish_reason". Lets callers persist the actual model output even when
        parsing fails — without bloating the L5Result that flows into every record.

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
        return _empty_result(genre)

    if (l4.sense_a_anchor_quote == l4.sense_b_anchor_quote
            and l4.anchor_relation != AnchorRelation.RESEGMENTATION):
        _LOG.warning(
            "L5 short-circuit: %s — identical anchor spans %r but anchor_relation=%s"
            " (RESEGMENTATION required for same-span anchors), no LLM call",
            record.item_id, l4.sense_a_anchor_quote, l4.anchor_relation,
        )
        return _empty_result(genre)

    term = ambiguous_term
    if term is None and record.l3_result and record.l3_result.candidates:
        term = record.l3_result.candidates[0].term
    if term is None:
        term = l4.sense_a_anchor_quote

    prompt = _render_prompt(genre, record.text, term, l4)

    if genre == Genre.QA_RIDDLE:
        weights: dict[str, float] = settings.L5_QA_WEIGHTS
        response_model: type = _QALLMResponse
    elif genre == Genre.DEFINITIONAL_ONELINER:
        weights = _L5_DEFINITIONAL_WEIGHTS
        response_model = _DefinitionalLLMResponse
    elif genre == Genre.DECLARATIVE:
        weights = _L5_DECLARATIVE_WEIGHTS
        response_model = _DeclarativeLLMResponse
    else:
        weights = _L5_DIALOGUE_WEIGHTS
        response_model = _DialogueLLMResponse

    call = _complete_json(
        prompt, frozenset(weights), response_model, settings, client, diagnostics
    )

    if call.truncated:
        _LOG.error(
            "L5 TRUNCATED_OUTPUT: %s — finish_reason=MAX_TOKENS, thoughts_token_count=%s, "
            "model=%s hit max_output_tokens=%d before emitting complete JSON. "
            "This is a truncation, NOT a model verdict.",
            record.item_id, call.thoughts_tokens, call.model_used,
            settings.L5_MAX_OUTPUT_TOKENS,
        )
        return _empty_result(
            genre,
            status=ResolutionStatus.TRUNCATED_OUTPUT,
            model_used=call.model_used,
            fallback_used=call.fallback_used,
            retries=call.retries,
        )

    if call.parsed is None:
        return _empty_result(
            genre,
            model_used=call.model_used,
            fallback_used=call.fallback_used,
            retries=call.retries,
        )

    subscores = {k: float(call.parsed[k]) for k in weights}
    score = _weighted_score(subscores, weights)
    kw = dict(
        resolution_score=round(score, 4),
        subscores=subscores,
        model_used=call.model_used,
        fallback_used=call.fallback_used,
        retries=call.retries,
    )

    if genre == Genre.QA_RIDDLE:
        return L5QAResult(
            genre=Genre.QA_RIDDLE,
            resolution_status=_resolution_status(score, settings.L5_RESOLUTION_THRESHOLDS[genre]),
            **kw,
        )
    if genre == Genre.DEFINITIONAL_ONELINER:
        return L5DefinitionalResult(
            genre=Genre.DEFINITIONAL_ONELINER,
            resolution_status=_resolution_status(score, settings.L5_RESOLUTION_THRESHOLDS[genre]),
            **kw,
        )
    if genre == Genre.DECLARATIVE:
        return L5DeclarativeResult(
            genre=Genre.DECLARATIVE,
            resolution_status=_resolution_status(score, settings.L5_RESOLUTION_THRESHOLDS[genre]),
            **kw,
        )
    return L5DialogueResult(
        genre=genre,
        resolution_status=_resolution_status(score, settings.L5_RESOLUTION_THRESHOLDS[genre]),
        **kw,
    )
