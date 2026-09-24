"""Pipeline configuration — single source of truth for all thresholds.

Deliberate deviations from README
----------------------------------
1. L3 candidate scoring: "target-age familiarity" has been removed from the
   feature list.  Including it would make candidate ranking age-dependent,
   meaning the same text could surface a different pun word at age 6 vs.
   age 12.  Candidate ranking must be age-independent; per-age effects are
   handled in L7 (comprehension assessment) instead.

2. L5_RESOLUTION_THRESHOLDS: the README specifies the QA weight formula but
   names no pass/fail cut-off.  Cut-offs are declared here, one per genre,
   so they have a single home and can be tuned without touching L5 logic.
   Per-genre because each branch has a different subscore set and the
   scores land on different scales (see docs/L5_CALIBRATION.md).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from .enums import Genre
from .providers import BackendType


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

    # --- L4 backend ------------------------------------------------------
    L4_BACKEND: BackendType = "gemini"
    L4_MODEL: str | None = None
    L4_MODEL_GEMINI: str = "gemini-3.6-flash"
    L4_MODEL_GEMINI_CHAIN: list[str] = ["gemini-3.8-flash"]
    L4_MODEL_ANTHROPIC: str = "claude-sonnet-5"
    L4_MODEL_OPENAI: str = "gpt-4o-mini"
    L4_MODEL_DEEPSEEK: str = "deepseek-chat"
    L4_MAX_OUTPUT_TOKENS: int = 4096
    L4_CALL_PAUSE_SECONDS: float = 6.0

    # --- L5 backend ------------------------------------------------------
    L5_BACKEND: BackendType = "gemini"
    L5_MODEL: str | None = None
    # Pin exact IDs — never use -latest aliases; availability varies by account age.
    L5_MODEL_GEMINI: str = "gemini-3.6-flash"
    # Ordered fallback chain tried after the primary exhausts its 5xx retries.
    L5_MODEL_GEMINI_CHAIN: list[str] = ["gemini-3.8-flash"]
    L5_MODEL_ANTHROPIC: str = "claude-sonnet-5"
    L5_MODEL_OPENAI: str = "gpt-4o-mini"
    L5_MODEL_DEEPSEEK: str = "deepseek-chat"
    # Max output tokens per Gemini call. Gemini 3.x counts THINKING tokens
    # against this cap — measured thinking was 487 then 969 on the same temp-0
    # prompt (2x variance), and the dialogue/definitional branches have longer,
    # untested prompts. 8192 leaves ample margin; we pay for tokens generated,
    # not the cap. Do NOT lower to "save" tokens: too small a cap truncates the
    # JSON mid-emit (finish_reason=MAX_TOKENS) and used to masquerade as a
    L5_MAX_OUTPUT_TOKENS: int = 8192
    L5_CALL_PAUSE_SECONDS: float = 6.0

    # --- L6 backend ------------------------------------------------------
    L6_BACKEND: BackendType = "gemini"
    L6_MODEL: str | None = None
    L6_MODEL_GEMINI: str = "gemini-3.6-flash"
    L6_MODEL_GEMINI_CHAIN: list[str] = ["gemini-3.8-flash"]
    L6_MODEL_ANTHROPIC: str = "claude-sonnet-5"
    L6_MODEL_OPENAI: str = "gpt-4o-mini"
    L6_MODEL_DEEPSEEK: str = "deepseek-chat"
    L6_MAX_OUTPUT_TOKENS: int = 4096
    L6_CALL_PAUSE_SECONDS: float = 6.0

    # --- L7 Comprehension backend & thresholds ---------------------------
    L7_BACKEND: BackendType = "gemini"
    L7_MODEL: str | None = None
    L7_MODEL_GEMINI: str = "gemini-3.6-flash"
    L7_MODEL_GEMINI_CHAIN: list[str] = ["gemini-3.8-flash"]
    L7_MODEL_ANTHROPIC: str = "claude-sonnet-5"
    L7_MODEL_OPENAI: str = "gpt-4o-mini"
    L7_MODEL_DEEPSEEK: str = "deepseek-chat"
    L7_MAX_OUTPUT_TOKENS: int = 4096
    L7_CALL_PAUSE_SECONDS: float = 6.0

    L7_METALINGUISTIC_FLOOR_HOMOGRAPH: float = 6.0
    L7_METALINGUISTIC_FLOOR_DEFINITIONAL: float = 7.0
    L7_METALINGUISTIC_FLOOR_DIALOGUE: float = 7.5
    L7_METALINGUISTIC_FLOOR_RESEGMENTATION: float = 8.0
    L7_SECONDARY_SENSE_AOA_OFFSET: float = 2.0
    L7_AOA_TOLERANCE: float = 0.5

    # --- L8 Appropriateness backend & models ----------------------------
    L8_BACKEND: BackendType = "gemini"
    L8_MODEL: str | None = None
    L8_MODEL_GEMINI: str = "gemini-3.6-flash"
    L8_MODEL_GEMINI_CHAIN: list[str] = ["gemini-3.8-flash"]
    L8_MODEL_ANTHROPIC: str = "claude-sonnet-5"
    L8_MODEL_OPENAI: str = "gpt-4o-mini"
    L8_MODEL_DEEPSEEK: str = "deepseek-chat"
    L8_MAX_OUTPUT_TOKENS: int = 4096
    L8_CALL_PAUSE_SECONDS: float = 6.0

    # --- Provider API keys & custom base URLs ----------------------------
    OPENAI_API_KEY: str | None = None
    DEEPSEEK_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    MISTRAL_API_KEY: str | None = None
    DASHSCOPE_API_KEY: str | None = None
    MOONSHOT_API_KEY: str | None = None
    ZHIPUAI_API_KEY: str | None = None
    SILICONFLOW_API_KEY: str | None = None

    OPENAI_BASE_URL: str | None = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # --- L5 QA resolution ------------------------------------------------
    # Weights must sum to 1.0 (asserted below).
    L5_QA_WEIGHTS: dict[str, float] = {
        "polarity_or_direction": 0.45,
        "answer_relevance": 0.25,
        "causal": 0.15,
        "agent": 0.10,
        "tense_aspect": 0.05,
    }
    # Per-genre pass/fail cut-off for the weighted resolution score.
    # Not named in README — see module docstring, deviation 2.
    # Verdicts are per run, so cut-offs are set from per-run ranges, not means.
    L5_RESOLUTION_THRESHOLDS: dict[Genre, float] = {
        # 5-run calibration: X1 (negative) max 0.417, E1 (positive) min 0.507.
        # 0.46 separates them on every run. NO threshold fixes S2 (negative,
        # 0.59-0.86 > S1 positive's 0.58-0.68): that is sense-labelling
        # (polarity inversion), not threshold.
        Genre.QA_RIDDLE: 0.46,
        # A1 0.935 stable; P2 0.865-0.930 (both positives). No validated negative yet.
        Genre.DEFINITIONAL_ONELINER: 0.60,
        # D1 0.858-0.927, P3 0.897-0.917. Positives only; no negative yet.
        Genre.DIALOGUE_MISUNDERSTANDING: 0.60,
        # UNVALIDATED: no declarative item has been scored live. Placeholder
        # until the annotated corpus's declarative jokes/non-jokes are run.
        Genre.DECLARATIVE: 0.60,
    }
    # Pause between API calls in the calibration script.
    # Free-tier Gemini is ~10–15 req/min → 6 s keeps us well inside the limit.
    L5_CALL_PAUSE_SECONDS: float = 6.0

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> "Settings":
        total = sum(self.L5_QA_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, (
            f"L5_QA_WEIGHTS must sum to 1.0, got {total:.6f}"
        )
        missing = set(Genre) - self.L5_RESOLUTION_THRESHOLDS.keys()
        assert not missing, f"L5_RESOLUTION_THRESHOLDS missing genres: {missing}"
        return self


DEFAULT_SETTINGS = Settings()
