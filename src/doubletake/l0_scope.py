"""L0 scope: input validation (L0-pre) and scope-label assignment (L0-post).

L0-pre
------
Runs first in the pipeline.  Validates and normalises the raw input text.
Makes no judgement about the text's content or lexical mechanism — that
determination belongs to L2–L4.

Steps applied in order:
  1. NFC unicode normalisation.
  2. Strip leading/trailing whitespace; collapse internal runs to one space.
  3. Reject empty or whitespace-only input.
  4. Reject input below MIN_INPUT_CHARS.
  5. Reject input above MAX_INPUT_CHARS.
  6. Reject input whose non-ASCII character ratio exceeds MAX_NON_ASCII_RATIO
     (proxy for non-English text or encoding garbage).

L0-post
-------
Runs last in the pipeline as a pure function:

    assign_scope_label(evidence: LayerEvidence) -> ScopeLabel

Decision table (evaluated top-to-bottom; first match wins):

    ┌─────────────────────────────────────────────────────────┬──────────────────────────────┐
    │ Condition                                               │ ScopeLabel                   │
    ├─────────────────────────────────────────────────────────┼──────────────────────────────┤
    │ is_homophone AND NOT has_homograph                      │ OUT_OF_SCOPE_HOMOPHONE       │
    │ has_homograph                                           │ HOMOGRAPH                    │
    │ has_compound_split                                      │ COMPOUND_SPLIT               │
    │ is_nonlexical_joke                                      │ OUT_OF_SCOPE_NONLEXICAL_JOKE │
    │ (none of the above, incl. all-False / incomplete evid.) │ NO_SCOPE_MECHANISM           │
    └─────────────────────────────────────────────────────────┴──────────────────────────────┘

Rationale for row ordering:
  - Homophone exclusion is checked first.  The guard NOT has_homograph
    ensures a genuine homograph that happens to be pronounced the same
    (e.g. "lead") is still classified as HOMOGRAPH rather than excluded.
  - HOMOGRAPH before COMPOUND_SPLIT: homographic ambiguity is the primary
    mechanism; compound splits are a secondary variant.
  - OUT_OF_SCOPE_NONLEXICAL_JOKE after positive matches: a confirmed
    lexical mechanism takes precedence over a nonlexical flag.
  - NO_SCOPE_MECHANISM is the safe default for incomplete evidence.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .config import Settings, DEFAULT_SETTINGS
from .enums import ScopeLabel


# ---------------------------------------------------------------------------
# L0-post evidence container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LayerEvidence:
    """Accumulated evidence from L2–L4 consumed by assign_scope_label."""

    has_homograph: bool = False
    has_compound_split: bool = False
    is_homophone: bool = False
    is_nonlexical_joke: bool = False


# ---------------------------------------------------------------------------
# L0-post: pure scope-label assignment
# ---------------------------------------------------------------------------

def assign_scope_label(evidence: LayerEvidence) -> ScopeLabel:
    """Map accumulated layer evidence to a single ScopeLabel.

    Pure function — no I/O, no LLM calls, fully deterministic.
    See module docstring for the complete decision table with rationale.
    """
    if evidence.is_homophone and not evidence.has_homograph:
        return ScopeLabel.OUT_OF_SCOPE_HOMOPHONE
    if evidence.has_homograph:
        return ScopeLabel.HOMOGRAPH
    if evidence.has_compound_split:
        return ScopeLabel.COMPOUND_SPLIT
    if evidence.is_nonlexical_joke:
        return ScopeLabel.OUT_OF_SCOPE_NONLEXICAL_JOKE
    return ScopeLabel.NO_SCOPE_MECHANISM


# ---------------------------------------------------------------------------
# L0-pre: input validation and normalisation
# ---------------------------------------------------------------------------

_MULTI_WHITESPACE = re.compile(r"\s+")


class InputValidationError(ValueError):
    """Raised by preprocess_input when the text cannot be accepted."""


def preprocess_input(text: str, settings: Settings = DEFAULT_SETTINGS) -> str:
    """Validate and normalise a raw input string.

    Returns the normalised text on success.
    Raises InputValidationError with a descriptive message on failure.
    """
    if not isinstance(text, str):
        raise InputValidationError(
            f"Expected str, got {type(text).__name__}."
        )

    # Step 1: NFC unicode normalisation
    text = unicodedata.normalize("NFC", text)

    # Steps 2: strip and collapse whitespace
    text = _MULTI_WHITESPACE.sub(" ", text).strip()

    # Step 3: reject empty / whitespace-only
    if not text:
        raise InputValidationError(
            "Input text is empty or whitespace-only."
        )

    # Step 4: too short
    if len(text) < settings.MIN_INPUT_CHARS:
        raise InputValidationError(
            f"Input has {len(text)} character(s); "
            f"minimum is {settings.MIN_INPUT_CHARS}."
        )

    # Step 5: too long
    if len(text) > settings.MAX_INPUT_CHARS:
        raise InputValidationError(
            f"Input has {len(text)} characters; "
            f"maximum is {settings.MAX_INPUT_CHARS}."
        )

    # Step 6: non-ASCII ratio (proxy for non-English / encoding garbage)
    non_ascii_count = sum(1 for c in text if ord(c) > 127)
    ratio = non_ascii_count / len(text)
    if ratio > settings.MAX_NON_ASCII_RATIO:
        raise InputValidationError(
            f"Input contains {non_ascii_count}/{len(text)} non-ASCII characters "
            f"(ratio {ratio:.2f} > threshold {settings.MAX_NON_ASCII_RATIO}); "
            "expected English ASCII text."
        )

    return text
