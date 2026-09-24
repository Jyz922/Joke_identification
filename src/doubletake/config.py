"""Pipeline configuration — single source of truth for all thresholds.

Deliberate deviations from README
----------------------------------
1. L3 candidate scoring: "target-age familiarity" has been removed from the
   feature list.  Including it would make candidate ranking age-dependent,
   meaning the same text could surface a different pun word at age 6 vs.
   age 12.  Candidate ranking must be age-independent; per-age effects are
   handled in L7 (comprehension assessment) instead.

2. L5_RESOLUTION_THRESHOLD: the README specifies the QA weight formula but
   names no pass/fail cut-off.  The threshold is declared here as 0.60 so
   it has a single home and can be tuned without touching L5 logic.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    # --- L0 scope policy -------------------------------------------------
    ACCEPTED_MECHANISMS: frozenset[str] = frozenset({
        "homographic_ambiguity",
        "idiomatic_expression_with_homograph",
        "compound_split",
        "resegmentation",
    })
    EXCLUDED_MECHANISMS: frozenset[str] = frozenset({
        "heterographic_homophone",
        "rhyming_joke",
        "absurdist_situation",
        "cultural_reference",
        "sarcasm",
        "social_context_only",
    })

    # --- Input validation (L0-pre) ---------------------------------------
    MAX_INPUT_CHARS: int = 500
    MIN_INPUT_CHARS: int = 3
    # Fraction of characters that may be non-ASCII before the text is
    # rejected as non-English or encoding garbage.
    MAX_NON_ASCII_RATIO: float = 0.15

    # --- L3 candidate ranking --------------------------------------------
    # NOTE: target-age familiarity is intentionally excluded from the
    # candidate score — see module docstring, deviation 1.
    L3_TOP_K: int = 3

    # --- L5 backend ------------------------------------------------------
    L5_BACKEND: Literal["gemini", "anthropic"] = "gemini"
    # Pin exact IDs — never use -latest aliases; availability varies by account age.
    L5_MODEL_GEMINI: str = "gemini-3.6-flash"
    # Ordered fallback chain tried after the primary exhausts its 5xx retries.
    L5_MODEL_GEMINI_CHAIN: list[str] = ["gemini-3.8-flash"]
    L5_MODEL_ANTHROPIC: str = "claude-sonnet-5"
    # Max output tokens per Gemini call. Gemini 3.x counts THINKING tokens
    # against this cap — measured thinking was 487 then 969 on the same temp-0
    # prompt (2x variance), and the dialogue/definitional branches have longer,
    # untested prompts. 8192 leaves ample margin; we pay for tokens generated,
    # not the cap. Do NOT lower to "save" tokens: too small a cap truncates the
    # JSON mid-emit (finish_reason=MAX_TOKENS) and used to masquerade as a
    # parse failure — see ResolutionStatus.TRUNCATED_OUTPUT.
    L5_MAX_OUTPUT_TOKENS: int = 8192

    # --- L5 QA resolution ------------------------------------------------
    # Weights must sum to 1.0 (asserted below).
    L5_QA_WEIGHTS: dict[str, float] = {
        "polarity_or_direction": 0.45,
        "answer_relevance": 0.25,
        "causal": 0.15,
        "agent": 0.10,
        "tense_aspect": 0.05,
    }
    # Pass/fail cut-off for the weighted resolution score.
    # Not named in README — declared here as a single source of truth.
    # See module docstring, deviation 2.
    L5_RESOLUTION_THRESHOLD: float = 0.60
    # Pause between API calls in the calibration script.
    # Free-tier Gemini is ~10–15 req/min → 6 s keeps us well inside the limit.
    L5_CALL_PAUSE_SECONDS: float = 6.0

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> "Settings":
        total = sum(self.L5_QA_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, (
            f"L5_QA_WEIGHTS must sum to 1.0, got {total:.6f}"
        )
        return self


DEFAULT_SETTINGS = Settings()
