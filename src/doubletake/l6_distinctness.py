"""L6: Sense-distinctness and lexical-granularity check.

L6 confirms that the two meanings anchored by L4 represent genuinely distinct
conceptual interpretations rather than subtle nuances of the same underlying sense.
Supports all major providers via the unified provider abstraction.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import anthropic
import google.genai as _genai
import google.genai.types as _genai_types
from google.genai.errors import ClientError as _GeminiClientError
from google.genai.errors import ServerError as _GeminiServerError
from pydantic import BaseModel, ConfigDict

from .config import DEFAULT_SETTINGS, Settings
from .enums import AmbiguityAblation, AnchorRelation, AnchoringStatus, DistinctnessStatus, Genre
from .providers import (
    PROVIDERS,
    call_openai_compatible,
    create_client,
    resolve_api_key,
    resolve_backend,
    resolve_model,
)
from .schema import AnalysisRecord, L6Result

_LOG = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "l6_distinctness.md"
_RETRY_SUFFIX = "\n\nRespond with valid JSON only matching the schema."


# ---------------------------------------------------------------------------
# Structured LLM response schema
# ---------------------------------------------------------------------------

class _L6LLMResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sense_a_paraphrase: str
    sense_b_paraphrase: str
    suppresses_other: bool = True
    materially_different: bool = True
    distinctness_status: str
    ambiguity_ablation: Optional[str] = "SUPPORTED"
    explanation: Optional[str] = ""


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def _render_l6_prompt(
    text: str,
    genre: Genre,
    term: str,
    sense_a: str,
    anchor_a: str,
    sense_b: str,
    anchor_b: str,
) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    mapping = {
        "text": text,
        "genre": genre.value,
        "term": term,
        "sense_a": sense_a or "(not specified)",
        "anchor_a": anchor_a or term,
        "sense_b": sense_b or "(not specified)",
        "anchor_b": anchor_b or term,
    }
    for k, v in mapping.items():
        template = template.replace(f"{{{k}}}", str(v))
    return template


def _extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


# ---------------------------------------------------------------------------
# LLM callers
# ---------------------------------------------------------------------------

@dataclass
class _L6Call:
    parsed: dict[str, Any] | None
    model_used: str
    fallback_used: bool
    retries: int


def _call_anthropic_l6(
    prompt_text: str,
    model: str,
    client: anthropic.Anthropic | None = None,
) -> dict[str, Any] | None:
    if client is None:
        client = anthropic.Anthropic()

    for attempt in range(2):
        suffix = "" if attempt == 0 else _RETRY_SUFFIX
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt_text + suffix}],
        )
        raw = response.content[0].text
        try:
            return _extract_json(raw)
        except (json.JSONDecodeError, ValueError, IndexError):
            if attempt == 1:
                return None
    return None


def _call_gemini_l6_single(
    prompt_text: str,
    model: str,
    client: _genai.Client,
    max_output_tokens: int,
) -> tuple[dict[str, Any] | None, int, _GeminiClientError | None]:
    config = _genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=_L6LLMResponse,
        temperature=0.0,
        max_output_tokens=max_output_tokens,
    )
    retries = 0
    delays = (2, 4, 8)
    for attempt in range(len(delays) + 1):
        if attempt > 0:
            time.sleep(delays[attempt - 1])
            retries += 1
        try:
            for parse_try in range(2):
                suffix = "" if parse_try == 0 else _RETRY_SUFFIX
                resp = client.models.generate_content(
                    model=model, contents=prompt_text + suffix, config=config
                )
                raw = resp.text
                try:
                    return _extract_json(raw), retries, None
                except (json.JSONDecodeError, ValueError, IndexError):
                    if parse_try == 1:
                        return None, retries, None
        except _GeminiServerError as e:
            if attempt == len(delays):
                return None, retries, e
        except _GeminiClientError:
            raise
    return None, retries, None


def _call_gemini_l6(
    prompt_text: str,
    settings: Settings,
    client: _genai.Client | None,
) -> _L6Call:
    if client is None:
        api_key, key_name = resolve_api_key("gemini", settings)
        if not api_key:
            raise ValueError(f"{key_name} not set")
        client = _genai.Client(api_key=api_key)

    models = [settings.L6_MODEL_GEMINI, *settings.L6_MODEL_GEMINI_CHAIN]
    total_retries = 0
    for idx, model in enumerate(models):
        parsed, retries, err_5xx = _call_gemini_l6_single(
            prompt_text, model, client, settings.L6_MAX_OUTPUT_TOKENS
        )
        total_retries += retries
        if parsed is not None:
            return _L6Call(parsed, model, idx > 0, total_retries)
        if err_5xx is None:
            return _L6Call(None, model, idx > 0, total_retries)
        if idx < len(models) - 1:
            _LOG.warning("L6 Gemini fallback: %s -> %s", model, models[idx + 1])
        else:
            raise RuntimeError(f"L6 Gemini exhausted models, last HTTP {err_5xx.code}") from err_5xx

    return _L6Call(None, models[-1], True, total_retries)


def _call_openai_l6(
    prompt_text: str,
    backend: str,
    settings: Settings,
    client: Any | None = None,
) -> _L6Call:
    if client is None:
        client = create_client(backend, settings)
    model = resolve_model(backend, "L6", settings)
    parsed, retries, fallback_used = call_openai_compatible(
        client=client,
        model=model,
        prompt_text=prompt_text,
        max_output_tokens=settings.L6_MAX_OUTPUT_TOKENS,
        temperature=0.0,
    )
    return _L6Call(parsed, model, fallback_used, retries)


def _complete_l6(
    prompt: str,
    settings: Settings,
    client: Any,
) -> _L6Call:
    backend = resolve_backend(settings.L6_BACKEND, settings)

    # If client is a mock, dispatch according to backend and capabilities
    if client is not None:
        if backend == "gemini" and hasattr(client, "models"):
            resp = client.models.generate_content(model="mock", contents=prompt)
            raw = getattr(resp, "text", "")
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L6Call(parsed, "mock", False, 0)
        if backend == "anthropic" and hasattr(client, "messages"):
            resp = client.messages.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.content[0].text
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L6Call(parsed, "mock", False, 0)
        if backend in PROVIDERS and PROVIDERS[backend].sdk_family == "openai" and hasattr(client, "chat"):
            resp = client.chat.completions.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.choices[0].message.content
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L6Call(parsed, "mock", False, 0)

        # Fallbacks for generic mocks where backend wasn't specifically matched
        if hasattr(client, "models"):
            resp = client.models.generate_content(model="mock", contents=prompt)
            raw = getattr(resp, "text", "")
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L6Call(parsed, "mock", False, 0)
        if hasattr(client, "messages"):
            resp = client.messages.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.content[0].text
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L6Call(parsed, "mock", False, 0)
        if hasattr(client, "chat"):
            resp = client.chat.completions.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.choices[0].message.content
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L6Call(parsed, "mock", False, 0)

    if backend == "gemini":
        return _call_gemini_l6(prompt, settings, client)
    if backend == "anthropic":
        parsed = _call_anthropic_l6(prompt, settings.L6_MODEL_ANTHROPIC, client)
        return _L6Call(parsed, settings.L6_MODEL_ANTHROPIC, False, 0)
    if backend in PROVIDERS and PROVIDERS[backend].sdk_family == "openai":
        return _call_openai_l6(prompt, backend, settings, client)
    raise ValueError(f"Unknown L6_BACKEND: {settings.L6_BACKEND!r}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def distinctness_l6(
    record: AnalysisRecord,
    settings: Settings = DEFAULT_SETTINGS,
    *,
    client: Any = None,
) -> L6Result:
    """Compute the L6 sense-distinctness result for *record*."""
    # 1. Guard: L4 must have completed and passed anchoring
    if record.l4_result is None or record.l4_result.anchoring_status != AnchoringStatus.PASS:
        status_desc = record.l4_result.anchoring_status.value if record.l4_result else "None"
        return L6Result(
            distinctness_status=DistinctnessStatus.L6_SKIPPED_NO_PARAPHRASE,
            ambiguity_ablation=AmbiguityAblation.SKIPPED,
            explanation=f"L4 anchoring was not PASS ({status_desc}); distinctness check skipped.",
        )

    l4 = record.l4_result
    term = "ambiguity"
    if record.l3_result and record.l3_result.candidates:
        term = record.l3_result.candidates[0].term

    # 2. Resegmentation / compound-split items are inherently distinct lexical forms
    if l4.anchor_relation == AnchorRelation.RESEGMENTATION:
        return L6Result(
            distinctness_status=DistinctnessStatus.SENSES_DISTINCT,
            ambiguity_ablation=AmbiguityAblation.SUPPORTED,
            sense_a_paraphrase=l4.sense_a,
            sense_b_paraphrase=l4.sense_b,
            explanation="Resegmentation/compound split involves distinct lexical units.",
        )

    genre = record.l1_result.genre if record.l1_result else Genre.DECLARATIVE
    prompt = _render_l6_prompt(
        text=record.text,
        genre=genre,
        term=term,
        sense_a=l4.sense_a,
        anchor_a=l4.sense_a_anchor_quote,
        sense_b=l4.sense_b,
        anchor_b=l4.sense_b_anchor_quote,
    )

    call = _complete_l6(prompt, settings, client)
    if call.parsed is None:
        _LOG.warning("L6 parse failure for item %s — returning L6_SKIPPED_NO_PARAPHRASE", record.item_id)
        return L6Result(
            distinctness_status=DistinctnessStatus.L6_SKIPPED_NO_PARAPHRASE,
            ambiguity_ablation=AmbiguityAblation.SKIPPED,
            explanation="Failed to parse LLM response for sense distinctness.",
        )

    parsed = call.parsed

    # Parse distinctness status
    raw_status = str(parsed.get("distinctness_status", "")).upper().strip()
    if "TOO_CLOSE" in raw_status or "CLOSE" in raw_status:
        status = DistinctnessStatus.SENSES_TOO_CLOSE
    elif "DISTINCT" in raw_status:
        status = DistinctnessStatus.SENSES_DISTINCT
    else:
        status = DistinctnessStatus.L6_SKIPPED_NO_PARAPHRASE

    # Parse ablation
    raw_ablation = str(parsed.get("ambiguity_ablation", "")).upper().strip()
    if "UNSUPPORTED" in raw_ablation:
        ablation = AmbiguityAblation.UNSUPPORTED
    elif "SUPPORTED" in raw_ablation:
        ablation = AmbiguityAblation.SUPPORTED
    else:
        ablation = AmbiguityAblation.SKIPPED

    return L6Result(
        distinctness_status=status,
        ambiguity_ablation=ablation,
        sense_a_paraphrase=parsed.get("sense_a_paraphrase"),
        sense_b_paraphrase=parsed.get("sense_b_paraphrase"),
        explanation=parsed.get("explanation"),
    )
