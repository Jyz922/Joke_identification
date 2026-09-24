"""L7: Comprehension assessment (evaluated per target age).

Estimates whether a child of a given target age has acquired the necessary
vocabulary (Sense A, Sense B, idioms/compound splits) and metalinguistic
capacity to comprehend the item.
"""

from __future__ import annotations

import json
import logging
import re
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
from .enums import AnchorRelation, AnchoringStatus, ComprehensionStatus, Genre
from .l2_senses import aoa_lookup
from .providers import (
    PROVIDERS,
    call_openai_compatible,
    create_client,
    resolve_api_key,
    resolve_backend,
    resolve_model,
)
from .schema import AnalysisRecord, L7Result

_LOG = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "l7_comprehension.md"
_RETRY_SUFFIX = "\n\nRespond with valid JSON only matching the schema."


# ---------------------------------------------------------------------------
# Structured LLM response schema
# ---------------------------------------------------------------------------

class _L7LLMResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sense_a_aoa: Optional[float] = None
    sense_b_aoa: Optional[float] = None
    compound_split_aoa: Optional[float] = None
    metalinguistic_floor: Optional[float] = None
    per_age_comprehension: dict[str, str]
    explanation: Optional[str] = ""


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def _render_l7_prompt(
    text: str,
    genre: Genre,
    term: str,
    sense_a: str,
    anchor_a: str,
    sense_b: str,
    anchor_b: str,
    target_ages: list[int],
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
        "target_ages": str(target_ages),
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
class _L7Call:
    parsed: dict[str, Any] | None
    model_used: str
    fallback_used: bool
    retries: int


def _call_anthropic_l7(
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


def _call_gemini_l7_single(
    prompt_text: str,
    model: str,
    client: _genai.Client,
    max_output_tokens: int,
) -> tuple[dict[str, Any] | None, int, _GeminiClientError | None]:
    config = _genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=_L7LLMResponse,
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


def _call_gemini_l7(
    prompt_text: str,
    settings: Settings,
    client: _genai.Client | None,
) -> _L7Call:
    if client is None:
        api_key, key_name = resolve_api_key("gemini", settings)
        if not api_key:
            raise ValueError(f"{key_name} not set")
        client = _genai.Client(api_key=api_key)

    models = [settings.L7_MODEL_GEMINI, *settings.L7_MODEL_GEMINI_CHAIN]
    total_retries = 0
    for idx, model in enumerate(models):
        parsed, retries, err_5xx = _call_gemini_l7_single(
            prompt_text, model, client, settings.L7_MAX_OUTPUT_TOKENS
        )
        total_retries += retries
        if parsed is not None:
            return _L7Call(parsed, model, idx > 0, total_retries)
        if err_5xx is None:
            return _L7Call(None, model, idx > 0, total_retries)
        if idx < len(models) - 1:
            _LOG.warning("L7 Gemini fallback: %s -> %s", model, models[idx + 1])
        else:
            raise RuntimeError(f"L7 Gemini exhausted models, last HTTP {err_5xx.code}") from err_5xx

    return _L7Call(None, models[-1], True, total_retries)


def _call_openai_l7(
    prompt_text: str,
    backend: str,
    settings: Settings,
    client: Any | None = None,
) -> _L7Call:
    if client is None:
        client = create_client(backend, settings)
    model = resolve_model(backend, "L7", settings)
    parsed, retries, fallback_used = call_openai_compatible(
        client=client,
        model=model,
        prompt_text=prompt_text,
        max_output_tokens=settings.L7_MAX_OUTPUT_TOKENS,
        temperature=0.0,
    )
    return _L7Call(parsed, model, fallback_used, retries)


def _complete_l7(
    prompt: str,
    settings: Settings,
    client: Any,
) -> _L7Call:
    backend = resolve_backend(settings.L7_BACKEND, settings)

    # If client is a mock, dispatch according to backend and capabilities
    if client is not None:
        if backend == "gemini" and hasattr(client, "models"):
            resp = client.models.generate_content(model="mock", contents=prompt)
            raw = getattr(resp, "text", "")
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L7Call(parsed, "mock", False, 0)
        if backend == "anthropic" and hasattr(client, "messages"):
            resp = client.messages.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.content[0].text
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L7Call(parsed, "mock", False, 0)
        if backend in PROVIDERS and PROVIDERS[backend].sdk_family == "openai" and hasattr(client, "chat"):
            resp = client.chat.completions.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.choices[0].message.content
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L7Call(parsed, "mock", False, 0)

        # Fallbacks for generic mocks where backend wasn't specifically matched
        if hasattr(client, "models"):
            resp = client.models.generate_content(model="mock", contents=prompt)
            raw = getattr(resp, "text", "")
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L7Call(parsed, "mock", False, 0)
        if hasattr(client, "messages"):
            resp = client.messages.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.content[0].text
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L7Call(parsed, "mock", False, 0)
        if hasattr(client, "chat"):
            resp = client.chat.completions.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.choices[0].message.content
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L7Call(parsed, "mock", False, 0)

    if backend == "gemini":
        return _call_gemini_l7(prompt, settings, client)
    if backend == "anthropic":
        parsed = _call_anthropic_l7(prompt, settings.L7_MODEL_ANTHROPIC, client)
        return _L7Call(parsed, settings.L7_MODEL_ANTHROPIC, False, 0)
    if backend in PROVIDERS and PROVIDERS[backend].sdk_family == "openai":
        return _call_openai_l7(prompt, backend, settings, client)
    raise ValueError(f"Unknown L7_BACKEND: {settings.L7_BACKEND!r}")


# ---------------------------------------------------------------------------
# Deterministic psycholinguistic baseline
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset({
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "and", "or", "but", "if", "not", "no", "that", "this",
    "it", "its", "as", "one", "own", "person", "someone", "something",
})


def _find_keyword_aoa(text: str) -> float | None:
    """Extract content words from a description and return the lowest/highest AoA."""
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    content_words = [w for w in words if w not in _STOPWORDS]
    aoas: list[float] = []
    for w in content_words:
        val, stage = aoa_lookup(w)
        if val is not None and stage != "miss":
            aoas.append(val)
    return max(aoas) if aoas else None


def _deterministic_l7(
    record: AnalysisRecord,
    settings: Settings,
) -> tuple[float | None, float | None, float | None, float, dict[int, ComprehensionStatus]]:
    """Compute AoA metrics deterministically from Kuperman ratings and genre rules."""
    term = "word"
    top_cand = record.l3_result.candidates[0] if record.l3_result and record.l3_result.candidates else None
    if top_cand:
        term = top_cand.term
    elif record.l1_result and record.l1_result.tokens:
        term = record.l1_result.tokens[0]

    term_aoa, _ = aoa_lookup(term)

    # 1. Sense A AoA
    sense_a_aoa = term_aoa
    if record.l4_result and record.l4_result.sense_a:
        kw_aoa = _find_keyword_aoa(record.l4_result.sense_a)
        if kw_aoa is not None:
            sense_a_aoa = min(sense_a_aoa, kw_aoa) if sense_a_aoa is not None else kw_aoa
    if sense_a_aoa is None:
        sense_a_aoa = 5.0

    # 2. Sense B AoA
    sense_b_aoa: float | None = None
    if record.l4_result and record.l4_result.sense_b:
        sense_b_aoa = _find_keyword_aoa(record.l4_result.sense_b)
    if sense_b_aoa is None or abs(sense_b_aoa - sense_a_aoa) < 0.1:
        # Figurative/secondary meaning offset
        sense_b_aoa = round(sense_a_aoa + settings.L7_SECONDARY_SENSE_AOA_OFFSET, 2)

    # 3. Compound-split AoA
    compound_split_aoa: float | None = None
    is_split = False
    if record.l4_result and record.l4_result.anchor_relation == AnchorRelation.RESEGMENTATION:
        is_split = True
    elif top_cand and top_cand.score_components.get("compound_split", 0.0) == 1.0:
        is_split = True

    if is_split:
        parts: list[str] = []
        if record.l1_result and record.l1_result.compound_splits:
            parts = record.l1_result.compound_splits
        elif record.l2_result:
            for s in record.l2_result.senses:
                if s.source.startswith("wordnet_split:"):
                    parts = s.source.replace("wordnet_split:", "").split("+")
                    break
        if parts:
            part_aoas = [aoa_lookup(p)[0] for p in parts]
            valid_aoas = [a for a in part_aoas if a is not None]
            if valid_aoas:
                compound_split_aoa = max(valid_aoas)
                sense_b_aoa = max(sense_b_aoa or 0.0, compound_split_aoa)

    # 4. Metalinguistic floor
    genre = record.l1_result.genre if record.l1_result else Genre.DECLARATIVE
    if is_split:
        metalinguistic_floor = settings.L7_METALINGUISTIC_FLOOR_RESEGMENTATION
    elif genre == Genre.DIALOGUE_MISUNDERSTANDING:
        metalinguistic_floor = settings.L7_METALINGUISTIC_FLOOR_DIALOGUE
    elif genre == Genre.DEFINITIONAL_ONELINER:
        metalinguistic_floor = settings.L7_METALINGUISTIC_FLOOR_DEFINITIONAL
    else:
        metalinguistic_floor = settings.L7_METALINGUISTIC_FLOOR_HOMOGRAPH

    # 5. Per-age evaluation
    target_ages = record.target_ages or [8]
    per_age: dict[int, ComprehensionStatus] = {}

    for age in target_ages:
        effective_age = age + settings.L7_AOA_TOLERANCE
        if term_aoa is None and sense_a_aoa is None:
            per_age[age] = ComprehensionStatus.AOA_UNKNOWN
        elif age < metalinguistic_floor and effective_age >= (sense_b_aoa or 0.0):
            per_age[age] = ComprehensionStatus.WORDPLAY_SKILL_TOO_ADVANCED
        elif effective_age < (sense_b_aoa or 0.0) or (compound_split_aoa is not None and effective_age < compound_split_aoa):
            per_age[age] = ComprehensionStatus.PARTIALLY_COMPREHENSIBLE
        else:
            per_age[age] = ComprehensionStatus.FULLY_COMPREHENSIBLE

    return sense_a_aoa, sense_b_aoa, compound_split_aoa, metalinguistic_floor, per_age


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assess_l7(
    record: AnalysisRecord,
    settings: Settings = DEFAULT_SETTINGS,
    *,
    client: Any = None,
) -> L7Result:
    """Compute the L7 comprehension assessment result for *record*."""
    # Deterministic psycholinguistic baseline
    det_a, det_b, det_split, det_floor, det_per_age = _deterministic_l7(record, settings)

    # If client is passed (mock or live), call LLM to potentially refine/format
    if client is not None:
        genre = record.l1_result.genre if record.l1_result else Genre.DECLARATIVE
        term = "word"
        if record.l3_result and record.l3_result.candidates:
            term = record.l3_result.candidates[0].term
        elif record.l1_result and record.l1_result.tokens:
            term = record.l1_result.tokens[0]

        sense_a = record.l4_result.sense_a if record.l4_result else ""
        anchor_a = record.l4_result.sense_a_anchor_quote if record.l4_result else term
        sense_b = record.l4_result.sense_b if record.l4_result else ""
        anchor_b = record.l4_result.sense_b_anchor_quote if record.l4_result else term

        prompt = _render_l7_prompt(
            text=record.text,
            genre=genre,
            term=term,
            sense_a=sense_a,
            anchor_a=anchor_a,
            sense_b=sense_b,
            anchor_b=anchor_b,
            target_ages=record.target_ages,
        )

        call = _complete_l7(prompt, settings, client)
        if call.parsed is not None:
            parsed = call.parsed
            raw_dict = parsed.get("per_age_comprehension", {})
            llm_per_age: dict[int, ComprehensionStatus] = {}
            for k, v in raw_dict.items():
                try:
                    age_int = int(k)
                    v_str = str(v).upper().strip()
                    if "FULLY" in v_str:
                        llm_per_age[age_int] = ComprehensionStatus.FULLY_COMPREHENSIBLE
                    elif "PARTIALLY" in v_str:
                        llm_per_age[age_int] = ComprehensionStatus.PARTIALLY_COMPREHENSIBLE
                    elif "SENSE_B" in v_str:
                        llm_per_age[age_int] = ComprehensionStatus.SENSE_B_TOO_ADVANCED
                    elif "WORDPLAY" in v_str or "SKILL" in v_str:
                        llm_per_age[age_int] = ComprehensionStatus.WORDPLAY_SKILL_TOO_ADVANCED
                    else:
                        llm_per_age[age_int] = ComprehensionStatus.AOA_UNKNOWN
                except (ValueError, TypeError):
                    continue

            if llm_per_age:
                return L7Result(
                    per_age_comprehension=llm_per_age,
                    sense_a_aoa=parsed.get("sense_a_aoa", det_a),
                    sense_b_aoa=parsed.get("sense_b_aoa", det_b),
                    compound_split_aoa=parsed.get("compound_split_aoa", det_split),
                    metalinguistic_floor=parsed.get("metalinguistic_floor", det_floor),
                    explanation=parsed.get("explanation", ""),
                )

    return L7Result(
        per_age_comprehension=det_per_age,
        sense_a_aoa=det_a,
        sense_b_aoa=det_b,
        compound_split_aoa=det_split,
        metalinguistic_floor=det_floor,
        explanation=f"Psycholinguistic baseline: sense_a_aoa={det_a}, sense_b_aoa={det_b}, floor={det_floor}",
    )
