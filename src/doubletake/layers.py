"""Typed stubs for pipeline layers L1–L8.

Each function carries the correct signature and type annotations but raises
NotImplementedError.  Replace the body to implement a layer; the runner
and trace machinery require no other changes.

Layer contract
--------------
    (record: AnalysisRecord, settings: Settings) -> AnalysisRecord

The function receives the current record, populates its corresponding
layer-result field (e.g. record.l1_result), appends a LayerTrace, and
returns the updated record.  The runner catches exceptions per item so
an unimplemented layer does not crash the whole run.
"""

from __future__ import annotations

import time

from .config import Settings
from .l2_senses import retrieve
from .l5_resolution import resolve_l5
from .schema import AnalysisRecord, L2Result, LayerTrace


def run_l1(record: AnalysisRecord, settings: Settings) -> AnalysisRecord:
    """L1: Surface analysis and genre routing."""
    raise NotImplementedError("L1 (surface analysis) is not implemented.")


def run_l2(record: AnalysisRecord, settings: Settings) -> AnalysisRecord:
    """L2: Sense retrieval from lexical resources."""
    if record.l1_result is None:
        raise ValueError("L1 must run before L2: l1_result is None")
    start = time.monotonic()
    senses = retrieve(record.l1_result.tokens)
    record.l2_result = L2Result(senses=senses)
    misses = sum(s.aoa_match == "miss" for s in senses)
    record.trace.append(LayerTrace(
        layer="L2",
        status="OK",
        reason=f"senses={len(senses)} aoa_miss={misses}",
        duration_ms=round((time.monotonic() - start) * 1000, 3),
        hints_used=0,
    ))
    return record


def run_l3(record: AnalysisRecord, settings: Settings) -> AnalysisRecord:
    """L3: Candidate ranking (top-k ambiguity sites)."""
    raise NotImplementedError("L3 (candidate ranking) is not implemented.")


def run_l4(record: AnalysisRecord, settings: Settings) -> AnalysisRecord:
    """L4: Sense anchoring — evidence that two meanings are active in the text."""
    raise NotImplementedError("L4 (sense anchoring) is not implemented.")


def run_l5(record: AnalysisRecord, settings: Settings) -> AnalysisRecord:
    """L5: Form-specific semantic resolution."""
    start = time.monotonic()
    result = resolve_l5(record, settings)
    duration_ms = round((time.monotonic() - start) * 1000, 3)
    record.l5_result = result
    record.trace.append(LayerTrace(
        layer="L5",
        status="OK",
        reason=f"resolution_status={result.resolution_status}",
        duration_ms=duration_ms,
        hints_used=0,
    ))
    return record


def run_l6(record: AnalysisRecord, settings: Settings) -> AnalysisRecord:
    """L6: Sense-distinctness and lexical-granularity check."""
    raise NotImplementedError("L6 (sense distinctness) is not implemented.")


def run_l7(record: AnalysisRecord, settings: Settings) -> AnalysisRecord:
    """L7: Comprehension assessment (evaluated per target age)."""
    raise NotImplementedError("L7 (comprehension assessment) is not implemented.")


def run_l8(record: AnalysisRecord, settings: Settings) -> AnalysisRecord:
    """L8: Two-axis appropriateness assessment (evaluated per target age)."""
    raise NotImplementedError("L8 (appropriateness assessment) is not implemented.")
