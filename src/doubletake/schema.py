"""Pydantic v2 models for the shared analysis record.

Invariant enforced by model_validator on AnalysisRecord:
    Detection fields (scope, ambiguous_term, senses, anchors, resolution)
    MUST NOT be nested under per_age.  Detection is computed once for the
    whole text and is age-independent.  Per-age slots hold only
    comprehension and appropriateness assessments.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import (
    AgeAppropriatenessVerdict,
    AmbiguityAblation,
    AnchorRelation,
    AnchoringStatus,
    ComprehensionStatus,
    DistinctnessStatus,
    Genre,
    MainClassification,
    ResolutionStatus,
    ScopeLabel,
)


# ---------------------------------------------------------------------------
# Sense and candidate sub-models (used by L2 and L3 results)
# ---------------------------------------------------------------------------

class SenseEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str
    lemma: str
    pos: str
    sense_id: str
    definition: str
    example: Optional[str] = None
    sense_frequency: Optional[float] = None
    aoa_estimate: Optional[float] = None
    source: str


class CandidateEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str
    score: float
    score_components: dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-layer result models (typed stubs; populated when layers run)
# ---------------------------------------------------------------------------

class L1Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    genre: Genre
    tokens: list[str]
    lemmas: list[str]
    pos_tags: list[str]
    compound_splits: list[str] = Field(default_factory=list)
    multiword_expressions: list[str] = Field(default_factory=list)
    has_question: bool = False
    has_negation: bool = False
    has_speaker_turns: bool = False


class L2Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    senses: list[SenseEntry] = Field(default_factory=list)


class L3Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateEntry] = Field(default_factory=list)


class L4Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sense_a: str
    sense_a_anchor_quote: str
    sense_b: str
    sense_b_anchor_quote: str
    anchor_relation: Optional[AnchorRelation] = None
    anchoring_status: AnchoringStatus


class L5QAResult(BaseModel):
    """Resolution result for QA_RIDDLE jokes.

    Subscores map the five keys from L5_QA_WEIGHTS: polarity_or_direction,
    answer_relevance, causal, agent, tense_aspect.
    resolution_score is None for INSUFFICIENT_CONTEXT (incomplete LLM response).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    genre: Literal[Genre.QA_RIDDLE]
    resolution_status: ResolutionStatus
    resolution_score: Optional[float] = None
    subscores: dict[str, float]


class L5DefinitionalResult(BaseModel):
    """Resolution result for DEFINITIONAL_ONELINER jokes.

    Subscores: setup_invites_literal, punchline_exploits_split, contrast_strength.
    Note: same-span anchors are permitted when anchor_relation == RESEGMENTATION.
    See ARCHITECTURE.md § L5 Decision 2.
    resolution_score is None for INSUFFICIENT_CONTEXT (incomplete LLM response).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    genre: Literal[Genre.DEFINITIONAL_ONELINER]
    resolution_status: ResolutionStatus
    resolution_score: Optional[float] = None
    subscores: dict[str, float]


class L5DialogueResult(BaseModel):
    """Resolution result for DIALOGUE_MISUNDERSTANDING and DECLARATIVE jokes.

    Subscores: misunderstanding_plausible, contrast_clear, speaker_intention_clear.
    resolution_score is None for INSUFFICIENT_CONTEXT (incomplete LLM response).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    genre: Literal[Genre.DIALOGUE_MISUNDERSTANDING, Genre.DECLARATIVE]
    resolution_status: ResolutionStatus
    resolution_score: Optional[float] = None
    subscores: dict[str, float]


L5Result = Annotated[
    Union[L5QAResult, L5DefinitionalResult, L5DialogueResult],
    Field(discriminator="genre"),
]


class L6Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distinctness_status: DistinctnessStatus
    ambiguity_ablation: Optional[AmbiguityAblation] = None


class L7Result(BaseModel):
    """Comprehension assessment — results are per target age."""

    model_config = ConfigDict(extra="forbid")

    per_age_comprehension: dict[int, ComprehensionStatus] = Field(default_factory=dict)


class L8Result(BaseModel):
    """Two-axis appropriateness assessment — results are per target age."""

    model_config = ConfigDict(extra="forbid")

    per_age_verdict: dict[int, AgeAppropriatenessVerdict] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Trace and verdict models
# ---------------------------------------------------------------------------

class LayerTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str
    status: str
    reason: Optional[str] = None
    duration_ms: float
    hints_used: int = 0


class AgeVerdict(BaseModel):
    """Per-age assessment holding ONLY age-dependent outputs.

    Detection fields (scope_label, ambiguous_term, sense_a, sense_b,
    anchoring_status, resolution_status, etc.) must NEVER appear here.
    They are age-independent and live at the AnalysisRecord or layer-result
    level.  extra="forbid" enforces this at instantiation time; the
    model_validator on AnalysisRecord provides an explicit, readable error
    for programmatic misuse.
    """

    model_config = ConfigDict(extra="forbid")

    comprehension: ComprehensionStatus
    appropriateness: AgeAppropriatenessVerdict


class FinalVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_classification: MainClassification
    scope_label: ScopeLabel
    per_age: dict[int, AgeVerdict] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Top-level analysis record
# ---------------------------------------------------------------------------

_DETECTION_FIELD_NAMES: frozenset[str] = frozenset({
    "scope_label",
    "ambiguous_term",
    "sense_a",
    "sense_b",
    "sense_a_anchor_quote",
    "sense_b_anchor_quote",
    "anchoring_status",
    "resolution_status",
    "anchor_relation",
    "resolution_score",
})


class AnalysisRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    text: str
    target_ages: list[int]

    l1_result: Optional[L1Result] = None
    l2_result: Optional[L2Result] = None
    l3_result: Optional[L3Result] = None
    l4_result: Optional[L4Result] = None
    l5_result: Optional[L5Result] = None
    l6_result: Optional[L6Result] = None
    l7_result: Optional[L7Result] = None
    l8_result: Optional[L8Result] = None

    trace: list[LayerTrace] = Field(default_factory=list)
    final: Optional[FinalVerdict] = None
    confidence: Optional[float] = None

    @model_validator(mode="after")
    def _no_detection_fields_in_per_age(self) -> "AnalysisRecord":
        """Fail loudly if any detection field is placed inside per_age.

        AgeVerdict already carries extra="forbid", so pydantic catches unknown
        fields at construction.  This validator adds a human-readable error
        message for cases where detection data is present as valid AgeVerdict
        fields set — which cannot happen with the current typed schema but
        makes the invariant explicit and self-documenting.
        """
        if self.final is None:
            return self
        for age, verdict in self.final.per_age.items():
            leaking = _DETECTION_FIELD_NAMES & verdict.model_fields_set
            if leaking:
                raise ValueError(
                    f"Detection fields {sorted(leaking)} found in per_age[{age}]. "
                    "Detection is age-independent; store these at the record or "
                    "layer-result level, not inside AgeVerdict."
                )
        return self
