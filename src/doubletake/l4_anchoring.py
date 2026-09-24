"""L4: Sense anchoring — evidence that two meanings are active in the text."""

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

from .config import DEFAULT_SETTINGS, Settings
from .enums import AnchorRelation, AnchoringStatus, Genre
from .schema import AnalysisRecord, L4Result

_PROMPT_PATH = Path(__file__).parent / "prompts" / "l4_anchoring.md"
_LOG = logging.getLogger(__name__)

_RETRY_SUFFIX = (
    "\n\nIMPORTANT: Your previous response could not be parsed as JSON"
    " or was missing required fields."
    " Return ONLY a valid JSON object with no surrounding text."
)


# ---------------------------------------------------------------------------
# Pydantic response model — used as Gemini response_schema.
# ---------------------------------------------------------------------------

class _L4LLMResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sense_a: str
    sense_a_anchor_quote: str
    sense_b: str
    sense_b_anchor_quote: str
    anchor_relation: str | None = None
    anchoring_status: str
    resolving_sense: str | None = None
    reasoning: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _align_substring(quote: str, text: str) -> str:
    """Normalize and align quote to an exact verbatim substring of text."""
    if not quote:
        return quote
    if quote in text:
        return quote
    # Case-insensitive substring match
    low_text = text.lower()
    low_quote = quote.lower()
    if low_quote in low_text:
        idx = low_text.index(low_quote)
        return text[idx : idx + len(quote)]
    # Strip boundary punctuation / whitespace
    stripped = quote.strip(" \t\n\r\"'.,;:!?-")
    if stripped.lower() in low_text:
        idx = low_text.index(stripped.lower())
        return text[idx : idx + len(stripped)]
    return quote


def _render_l4_prompt(
    text: str,
    genre: Genre,
    candidate_term: str,
    candidate_details: str = "",
) -> str:
    variables = {
        "text": text,
        "genre": genre.value,
        "candidate_term": candidate_term,
        "candidate_details": candidate_details,
    }
    tmpl = _load_prompt()
    for k, v in variables.items():
        tmpl = tmpl.replace(f"{{{k}}}", v)
    return tmpl


def _extract_json(text: str) -> dict[str, Any]:
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fence:
        return json.loads(fence.group(1))
    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# Backend round-trip calls
# ---------------------------------------------------------------------------

class _L4Call(NamedTuple):
    parsed: dict[str, Any] | None
    model_used: str
    fallback_used: bool
    retries: int


def _call_anthropic_l4(
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


def _call_gemini_l4_single(
    prompt_text: str,
    model: str,
    client: _genai.Client,
    max_output_tokens: int,
) -> tuple[dict[str, Any] | None, int, _GeminiClientError | None]:
    config = _genai_types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=_L4LLMResponse,
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


def _call_gemini_l4(
    prompt_text: str,
    settings: Settings,
    client: _genai.Client | None,
) -> _L4Call:
    if client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        client = _genai.Client(api_key=api_key)

    models = [settings.L4_MODEL_GEMINI, *settings.L4_MODEL_GEMINI_CHAIN]
    total_retries = 0
    for idx, model in enumerate(models):
        parsed, retries, err_5xx = _call_gemini_l4_single(
            prompt_text, model, client, settings.L4_MAX_OUTPUT_TOKENS
        )
        total_retries += retries
        if parsed is not None:
            return _L4Call(parsed, model, idx > 0, total_retries)
        if err_5xx is None:
            return _L4Call(None, model, idx > 0, total_retries)
    return _L4Call(None, models[-1], True, total_retries)


def _complete_l4(
    prompt: str,
    settings: Settings,
    client: Any,
) -> _L4Call:
    # If client is a mock with either interface, dispatch accordingly
    if client is not None:
        if hasattr(client, "models"):
            resp = client.models.generate_content(model="mock", contents=prompt)
            raw = getattr(resp, "text", "")
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L4Call(parsed, "mock", False, 0)
        if hasattr(client, "messages"):
            resp = client.messages.create(model="mock", messages=[{"role": "user", "content": prompt}])
            raw = resp.content[0].text
            try:
                parsed = _extract_json(raw)
            except Exception:
                parsed = None
            return _L4Call(parsed, "mock", False, 0)

    if settings.L4_BACKEND == "gemini":
        return _call_gemini_l4(prompt, settings, client)
    if settings.L4_BACKEND == "anthropic":
        parsed = _call_anthropic_l4(prompt, settings.L4_MODEL_ANTHROPIC, client)
        return _L4Call(parsed, settings.L4_MODEL_ANTHROPIC, False, 0)
    raise ValueError(f"Unknown L4_BACKEND: {settings.L4_BACKEND!r}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def anchor_l4(
    record: AnalysisRecord,
    settings: Settings = DEFAULT_SETTINGS,
    *,
    ambiguous_term: str | None = None,
    client: Any = None,
    diagnostics: dict[str, Any] | None = None,
) -> L4Result:
    """Compute the L4 sense-anchoring result for *record*."""
    if record.l1_result is None:
        raise ValueError("L1 must run before L4: l1_result is None")

    genre = record.l1_result.genre

    # Candidate selection
    term = ambiguous_term
    candidate_details = ""
    is_compound_split_candidate = False

    if term is None and record.l3_result and record.l3_result.candidates:
        top_cand = record.l3_result.candidates[0]
        term = top_cand.term
        is_compound_split_candidate = top_cand.score_components.get("compound_split", 0.0) == 1.0

        # Retrieve definitions if available in L2
        if record.l2_result and record.l2_result.senses:
            matched_senses = [s for s in record.l2_result.senses if s.term.lower() == term.lower()]
            if matched_senses:
                s_lines = [f"- {s.sense_id}: {s.definition}" for s in matched_senses[:4]]
                candidate_details = f"Known dictionary senses for '{term}':\n" + "\n".join(s_lines)

    if term is None:
        # Fallback to first noun/content token if no L3 candidates
        tokens = record.l1_result.tokens
        term = tokens[0] if tokens else "wordplay"

    prompt = _render_l4_prompt(record.text, genre, term, candidate_details)
    call = _complete_l4(prompt, settings, client)

    if call.parsed is None:
        _LOG.warning("L4 parse failure for item %s — returning FAIL", record.item_id)
        return L4Result(
            sense_a="",
            sense_a_anchor_quote=term,
            sense_b="",
            sense_b_anchor_quote=term,
            anchor_relation=None,
            anchoring_status=AnchoringStatus.FAIL,
            resolving_sense=None,
        )

    parsed = call.parsed

    # Align quotes to exact substrings of record.text
    quote_a = _align_substring(parsed.get("sense_a_anchor_quote", ""), record.text)
    quote_b = _align_substring(parsed.get("sense_b_anchor_quote", ""), record.text)

    # Parse anchoring status
    raw_status = str(parsed.get("anchoring_status", "FAIL")).upper().strip()
    if "ONE_SENSE" in raw_status:
        status = AnchoringStatus.ONE_SENSE_ONLY
    elif "PASS" in raw_status:
        status = AnchoringStatus.PASS
    else:
        status = AnchoringStatus.FAIL

    # Parse anchor relation
    raw_rel = parsed.get("anchor_relation")
    relation: AnchorRelation | None = None
    if raw_rel:
        rel_str = str(raw_rel).lower().strip()
        if "resegmentation" in rel_str or "split" in rel_str or is_compound_split_candidate:
            relation = AnchorRelation.RESEGMENTATION
        elif "speaker" in rel_str or "mismatch" in rel_str or genre == Genre.DIALOGUE_MISUNDERSTANDING:
            relation = AnchorRelation.SPEAKER_MISMATCH
        else:
            relation = AnchorRelation.SEPARATE_CONTEXTS
    elif status == AnchoringStatus.PASS:
        if is_compound_split_candidate:
            relation = AnchorRelation.RESEGMENTATION
        elif genre == Genre.DIALOGUE_MISUNDERSTANDING:
            relation = AnchorRelation.SPEAKER_MISMATCH
        else:
            relation = AnchorRelation.SEPARATE_CONTEXTS

    # Check same-span constraint
    if quote_a.lower() == quote_b.lower():
        if relation != AnchorRelation.RESEGMENTATION:
            if is_compound_split_candidate:
                relation = AnchorRelation.RESEGMENTATION
            else:
                # Same span for non-resegmentation indicates only one context span found
                status = AnchoringStatus.ONE_SENSE_ONLY

    # Resolving sense determination
    resolving_sense: str | None = None
    if status == AnchoringStatus.PASS:
        res = parsed.get("resolving_sense")
        if res in ("sense_a", "sense_b"):
            resolving_sense = res
        else:
            # Default to sense_b for PASS if unspecified
            resolving_sense = "sense_b"
    else:
        resolving_sense = None
        if status != AnchoringStatus.PASS:
            relation = None

    return L4Result(
        sense_a=parsed.get("sense_a", ""),
        sense_a_anchor_quote=quote_a,
        sense_b=parsed.get("sense_b", ""),
        sense_b_anchor_quote=quote_b,
        anchor_relation=relation,
        anchoring_status=status,
        resolving_sense=resolving_sense,  # type: ignore[arg-type]
    )
