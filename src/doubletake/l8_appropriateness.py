"""L8: Two-axis appropriateness assessment (evaluated per target age).

Assesses:
1. Content Appropriateness: topic and language of the text itself (violence,
   death, sexuality, substances, profanity, adult themes).
2. Inference Appropriateness: knowledge or reasoning required to reach the
   alternative meaning (adult knowledge, political symbolism, professional
   knowledge, abstract metaphorical reasoning).

Combines L7 comprehension status and both L8 dimensions to produce the final
AgeAppropriatenessVerdict per target age.
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
from pydantic import BaseModel, ConfigDict, Field

from .config import DEFAULT_SETTINGS, Settings
from .enums import AgeAppropriatenessVerdict, ComprehensionStatus, Genre
from .providers import (
    PROVIDERS,
    call_openai_compatible,
    create_client,
    resolve_api_key,
    resolve_backend,
    resolve_model,
)
from .schema import AnalysisRecord, L8Result

_LOG = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "l8_appropriateness.md"
_RETRY_SUFFIX = "\n\nRespond with valid JSON only matching the schema."


# ---------------------------------------------------------------------------
# Structured LLM response schema
# ---------------------------------------------------------------------------

class _L8LLMResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content_appropriate: dict[str, bool] = Field(default_factory=dict)
    inference_appropriate: dict[str, bool] = Field(default_factory=dict)
    per_age_verdict: dict[str, str]
    content_issues: list[str] = Field(default_factory=list)
    inference_issues: list[str] = Field(default_factory=list)
    explanation: Optional[str] = ""


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------

def _render_l8_prompt(
    text: str,
    genre: Genre,
    term: str,
    sense_a: str,
    sense_b: str,
    target_ages: list[int],
    l7_comprehension: dict[int, str],
) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    mapping = {
        "text": text,
        "genre": genre.value,
        "term": term,
        "sense_a": sense_a or "(not specified)",
        "sense_b": sense_b or "(not specified)",
        "target_ages": str(target_ages),
        "l7_comprehension": json.dumps({str(k): v for k, v in l7_comprehension.items()}),
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
class _L8Call:
    parsed: dict[str, Any] | None
    model_used: str
    fallback_used: bool
    retries: int


def _call_anthropic_l8(
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


def _call_gemini_l8_single(
    prompt_text: str,
    model: str,
    client: _genai.Client,
    max_output_tokens: int,
) -> tuple[dict[str, Any] | None, int, _GeminiClientError | None]:
    config = _genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=_L8LLMResponse,
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


def _call_gemini_l8(
    prompt_text: str,
    settings: Settings,
    client: _genai.Client | None,
) -> _L8Call:
    if client is None:
        api_key, key_name = resolve_api_key("gemini", settings)
        if not api_key:
            raise ValueError(f"{key_name} not set")
        client = _genai.Client(api_key=api_key)

    models = [settings.L8_MODEL_GEMINI, *settings.L8_MODEL_GEMINI_CHAIN]
    total_retries = 0
    for idx, model in enumerate(models):
        parsed, retries, err_5xx = _call_gemini_l8_single(
            prompt_text, model, client, settings.L8_MAX_OUTPUT_TOKENS
        )
        total_retries += retries
        if parsed is not None:
            return _L8Call(parsed, model, idx > 0, total_retries)
        if err_5xx is None:
            return _L8Call(None, model, idx > 0, total_retries)
        if idx < len(models) - 1:
            _LOG.warning("L8 Gemini fallback: %s -> %s", model, models[idx + 1])
        else:
            raise RuntimeError(f"L8 Gemini exhausted models, last HTTP {err_5xx.code}") from err_5xx

    return _L8Call(None, models[-1], True, total_retries)


def _call_openai_l8(
    prompt_text: str,
    backend: str,
    settings: Settings,
    client: Any | None = None,
) -> _L8Call:
    if client is None:
        client = create_client(backend, settings)
    model = resolve_model(backend, "L8", settings)
    parsed, retries, fallback_used = call_openai_compatible(
        client=client,
        model=model,
        prompt_text=prompt_text,
        max_output_tokens=settings.L8_MAX_OUTPUT_TOKENS,
        temperature=0.0,
    )
    return _L8Call(parsed, model, fallback_used, retries)


def _complete_l8(
    prompt: str,
    settings: Settings,
    client: Any,
) -> _L8Call:
    backend = resolve_backend(settings.L8_BACKEND, settings)

    # Mock dispatch
    if client is not None:
        if backend == "gemini" and hasattr(client, "models"):
            resp = client.models.generate_content(model="mock", contents=prompt)
            raw = getattr(resp, "text", "")
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L8Call(parsed, "mock", False, 0)
        if backend == "anthropic" and hasattr(client, "messages"):
            resp = client.messages.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.content[0].text
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L8Call(parsed, "mock", False, 0)
        if backend in PROVIDERS and PROVIDERS[backend].sdk_family == "openai" and hasattr(client, "chat"):
            resp = client.chat.completions.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.choices[0].message.content
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L8Call(parsed, "mock", False, 0)

        # Fallbacks for generic mocks
        if hasattr(client, "models"):
            resp = client.models.generate_content(model="mock", contents=prompt)
            raw = getattr(resp, "text", "")
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L8Call(parsed, "mock", False, 0)
        if hasattr(client, "messages"):
            resp = client.messages.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.content[0].text
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L8Call(parsed, "mock", False, 0)
        if hasattr(client, "chat"):
            resp = client.chat.completions.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.choices[0].message.content
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L8Call(parsed, "mock", False, 0)

    if backend == "gemini":
        return _call_gemini_l8(prompt, settings, client)
    if backend == "anthropic":
        parsed = _call_anthropic_l8(prompt, settings.L8_MODEL_ANTHROPIC, client)
        return _L8Call(parsed, settings.L8_MODEL_ANTHROPIC, False, 0)
    if backend in PROVIDERS and PROVIDERS[backend].sdk_family == "openai":
        return _call_openai_l8(prompt, backend, settings, client)
    raise ValueError(f"Unknown L8_BACKEND: {settings.L8_BACKEND!r}")


# ---------------------------------------------------------------------------
# Deterministic baseline
# ---------------------------------------------------------------------------

_CONTENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "substances": re.compile(
        r"\b(beer|wine|vodka|whiskey|liquor|alcohol|drunk|drugs|weed|marijuana|cocaine|heroin|tobacco|cigarette|cigar|smoke|vape)\b",
        re.IGNORECASE,
    ),
    "violence": re.compile(
        r"\b(kill|murder|slaughter|assassinate|stab|shoot|gun|pistol|rifle|blood|corpse|execution|torture)\b",
        re.IGNORECASE,
    ),
    "sexuality": re.compile(
        r"\b(sex|sexy|naked|nude|porn|erotic|affair|adultery|hooker|prostitute)\b",
        re.IGNORECASE,
    ),
    "profanity": re.compile(
        r"\b(damn|hell|ass|bitch|bastard|shit|fuck|crap)\b",
        re.IGNORECASE,
    ),
}

_INFERENCE_PATTERNS: dict[str, re.Pattern[str]] = {
    "finance_legal": re.compile(
        r"\b(mortgage|subpoena|lawsuit|attorney|dividend|stockbroker|taxation|irs|auditor|bankruptcy|corporate|merger|acquisition)\b",
        re.IGNORECASE,
    ),
    "political_civic": re.compile(
        r"\b(senator|congressman|parliament|impeachment|partisan|bureaucracy)\b",
        re.IGNORECASE,
    ),
}


def _deterministic_l8(
    record: AnalysisRecord,
    settings: Settings,
) -> tuple[dict[int, AgeAppropriatenessVerdict], list[str], list[str], str]:
    """Compute appropriateness verdicts deterministically using heuristic scans and L7 output."""
    text_corpus = record.text.lower()
    if record.l4_result:
        text_corpus += f" {record.l4_result.sense_a.lower()} {record.l4_result.sense_b.lower()}"

    content_issues: list[str] = []
    for issue_name, pat in _CONTENT_PATTERNS.items():
        if pat.search(text_corpus):
            content_issues.append(issue_name)

    inference_issues: list[str] = []
    for issue_name, pat in _INFERENCE_PATTERNS.items():
        if pat.search(text_corpus):
            inference_issues.append(issue_name)

    target_ages = record.target_ages or [8]
    per_age: dict[int, AgeAppropriatenessVerdict] = {}

    l7_comp = record.l7_result.per_age_comprehension if record.l7_result else {}

    for age in target_ages:
        comp_status = l7_comp.get(age, ComprehensionStatus.AOA_UNKNOWN)

        # 1. Content appropriateness check
        if content_issues and age < 14:
            per_age[age] = AgeAppropriatenessVerdict.CONTENT_NOT_APPROPRIATE
            continue

        # 2. Inference appropriateness check
        if inference_issues and age < 12:
            per_age[age] = AgeAppropriatenessVerdict.CONTENT_OK_INFERENCE_TOO_ADVANCED
            continue

        # 3. L7 Comprehension alignment
        if comp_status == ComprehensionStatus.WORDPLAY_SKILL_TOO_ADVANCED:
            per_age[age] = AgeAppropriatenessVerdict.CONTENT_OK_INFERENCE_TOO_ADVANCED
        elif comp_status in (
            ComprehensionStatus.SENSE_B_TOO_ADVANCED,
            ComprehensionStatus.PARTIALLY_COMPREHENSIBLE,
            ComprehensionStatus.AOA_UNKNOWN,
        ):
            per_age[age] = AgeAppropriatenessVerdict.VOCABULARY_TOO_ADVANCED
        else:
            per_age[age] = AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE

    explanation = (
        f"Deterministic baseline: content_issues={content_issues}, "
        f"inference_issues={inference_issues}"
    )
    return per_age, content_issues, inference_issues, explanation


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assess_l8(
    record: AnalysisRecord,
    settings: Settings = DEFAULT_SETTINGS,
    *,
    client: Any = None,
) -> L8Result:
    """Compute the L8 two-axis appropriateness result for *record*."""
    # Deterministic baseline
    det_per_age, det_c_issues, det_i_issues, det_expl = _deterministic_l8(record, settings)

    # LLM execution if client is provided
    if client is not None:
        genre = record.l1_result.genre if record.l1_result else Genre.DECLARATIVE
        term = "word"
        if record.l3_result and record.l3_result.candidates:
            term = record.l3_result.candidates[0].term
        elif record.l1_result and record.l1_result.tokens:
            term = record.l1_result.tokens[0]

        sense_a = record.l4_result.sense_a if record.l4_result else ""
        sense_b = record.l4_result.sense_b if record.l4_result else ""

        l7_map: dict[int, str] = {}
        if record.l7_result:
            for age_val, status_val in record.l7_result.per_age_comprehension.items():
                l7_map[age_val] = status_val.value

        prompt = _render_l8_prompt(
            text=record.text,
            genre=genre,
            term=term,
            sense_a=sense_a,
            sense_b=sense_b,
            target_ages=record.target_ages,
            l7_comprehension=l7_map,
        )

        call = _complete_l8(prompt, settings, client)
        if call.parsed is not None:
            parsed = call.parsed
            raw_dict = parsed.get("per_age_verdict", {})
            llm_per_age: dict[int, AgeAppropriatenessVerdict] = {}
            for k, v in raw_dict.items():
                try:
                    age_int = int(k)
                    v_str = str(v).upper().strip()
                    if "NOT_APPROPRIATE" in v_str:
                        llm_per_age[age_int] = AgeAppropriatenessVerdict.CONTENT_NOT_APPROPRIATE
                    elif "INFERENCE" in v_str:
                        llm_per_age[age_int] = AgeAppropriatenessVerdict.CONTENT_OK_INFERENCE_TOO_ADVANCED
                    elif "VOCABULARY" in v_str:
                        llm_per_age[age_int] = AgeAppropriatenessVerdict.VOCABULARY_TOO_ADVANCED
                    elif "FULLY" in v_str:
                        llm_per_age[age_int] = AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE
                    else:
                        llm_per_age[age_int] = det_per_age.get(
                            age_int, AgeAppropriatenessVerdict.FULLY_AGE_APPROPRIATE
                        )
                except (ValueError, TypeError):
                    continue

            if llm_per_age:
                return L8Result(
                    per_age_verdict=llm_per_age,
                    content_issues=parsed.get("content_issues", det_c_issues),
                    inference_issues=parsed.get("inference_issues", det_i_issues),
                    explanation=parsed.get("explanation", ""),
                )

    return L8Result(
        per_age_verdict=det_per_age,
        content_issues=det_c_issues,
        inference_issues=det_i_issues,
        explanation=det_expl,
    )
