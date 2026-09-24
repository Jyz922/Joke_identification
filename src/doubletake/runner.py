"""Pipeline runner with layer registry.

Layer registry
--------------
Layers are registered callables with signature:
    (record: AnalysisRecord, settings: Settings) -> AnalysisRecord

Register a layer:
    register_layer("L1", run_l1)

The runner calls registered layers in registration order.  Per-item
exceptions are caught and recorded as a LayerTrace(status="ERROR") rather
than crashing the whole run.

Output layout
-------------
    runs/<utc-timestamp>/
        records.jsonl   — one JSON object per input item
        run_meta.json   — config snapshot + git SHA

CLI
---
    python -m doubletake.runner --blind <path> [--output <root>]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import DEFAULT_SETTINGS, Settings
from .corpus import evaluate_run, load_blind
from .enums import AnchorRelation, AnchoringStatus, DistinctnessStatus, MainClassification, ResolutionStatus, ScopeLabel
from .l0_scope import InputValidationError, LayerEvidence, assign_scope_label, preprocess_input
from .layers import run_l1, run_l2, run_l3, run_l4, run_l5, run_l6, run_l7, run_l8
from .schema import AnalysisRecord, FinalVerdict, LayerTrace


# ---------------------------------------------------------------------------
# Layer registry
# ---------------------------------------------------------------------------

_LAYER_REGISTRY: list[tuple[str, Callable[[AnalysisRecord, Settings], AnalysisRecord]]] = []


def register_layer(
    name: str,
    fn: Callable[[AnalysisRecord, Settings], AnalysisRecord],
) -> None:
    """Append a named layer callable to the execution registry."""
    _LAYER_REGISTRY.append((name, fn))


def clear_registry() -> None:
    """Remove all registered layers.  Intended for use in tests only."""
    _LAYER_REGISTRY.clear()


# ---------------------------------------------------------------------------
# Built-in L0 layers
# ---------------------------------------------------------------------------

def _l0_pre_layer(record: AnalysisRecord, settings: Settings) -> AnalysisRecord:
    """L0-pre: validate and normalise input text."""
    start = time.monotonic()
    try:
        record.text = preprocess_input(record.text, settings)
        status, reason = "OK", None
    except InputValidationError as exc:
        status, reason = "REJECTED", str(exc)
    duration_ms = round((time.monotonic() - start) * 1000, 3)
    record.trace.append(LayerTrace(
        layer="L0-pre",
        status=status,
        reason=reason,
        duration_ms=duration_ms,
        hints_used=0,
    ))
    return record


def _l0_post_layer(record: AnalysisRecord, settings: Settings) -> AnalysisRecord:
    """L0-post: assign scope label from accumulated L2–L4 evidence."""
    start = time.monotonic()

    has_split = False
    has_homo = False
    if record.l4_result is not None and record.l4_result.anchoring_status == AnchoringStatus.PASS:
        if record.l4_result.anchor_relation == AnchorRelation.RESEGMENTATION:
            has_split = True
        else:
            has_homo = True
    elif record.l3_result is not None and record.l3_result.candidates:
        top = record.l3_result.candidates[0]
        if top.score_components.get("compound_split") == 1.0:
            has_split = True
        elif top.score > 0:
            has_homo = True

    evidence = LayerEvidence(
        has_homograph=has_homo,
        has_compound_split=has_split,
        is_homophone=False,
        is_nonlexical_joke=False,
    )
    scope_label = assign_scope_label(evidence)

    main_class = MainClassification.NO_AMBIGUITY_FOUND
    if scope_label == ScopeLabel.OUT_OF_SCOPE_HOMOPHONE:
        main_class = MainClassification.OUT_OF_SCOPE_HOMOPHONE
    elif scope_label == ScopeLabel.OUT_OF_SCOPE_NONLEXICAL_JOKE:
        main_class = MainClassification.OUT_OF_SCOPE_NONLEXICAL_JOKE
    elif record.l5_result is not None:
        if record.l5_result.resolution_status == ResolutionStatus.RESOLUTION_PASS:
            if record.l6_result is not None and record.l6_result.distinctness_status == DistinctnessStatus.SENSES_TOO_CLOSE:
                main_class = MainClassification.SENSES_TOO_CLOSE
            else:
                main_class = (
                    MainClassification.VALID_COMPOUND_SPLIT_JOKE
                    if scope_label == ScopeLabel.COMPOUND_SPLIT
                    else MainClassification.VALID_HOMOGRAPH_JOKE
                )
        elif record.l5_result.resolution_status == ResolutionStatus.RESOLUTION_FAIL:
            main_class = MainClassification.RESOLUTION_FAIL
    elif record.l4_result is not None:
        if record.l4_result.anchoring_status == AnchoringStatus.ONE_SENSE_ONLY:
            main_class = MainClassification.ONE_SENSE_ONLY
        elif record.l4_result.anchoring_status == AnchoringStatus.FAIL:
            main_class = MainClassification.ANCHORING_FAIL

    # Confidence calculation per README § L6 (lowered when L6 paraphrase is skipped)
    confidence: float | None = None
    if record.l5_result is not None and record.l5_result.resolution_score is not None:
        confidence = float(record.l5_result.resolution_score)
        if record.l6_result is not None:
            if record.l6_result.distinctness_status == DistinctnessStatus.L6_SKIPPED_NO_PARAPHRASE:
                confidence = round(confidence * 0.85, 3)
            elif record.l6_result.distinctness_status == DistinctnessStatus.SENSES_DISTINCT:
                confidence = min(1.0, round(confidence, 3))
    elif record.l3_result is not None and record.l3_result.candidates:
        confidence = round(record.l3_result.candidates[0].score, 3)
    record.confidence = confidence

    duration_ms = round((time.monotonic() - start) * 1000, 3)

    if record.final is None:
        record.final = FinalVerdict(
            main_classification=main_class,
            scope_label=scope_label,
        )
    else:
        record.final = record.final.model_copy(update={
            "scope_label": scope_label,
            "main_classification": main_class,
        })

    record.trace.append(LayerTrace(
        layer="L0-post",
        status="OK",
        reason=f"scope_label={scope_label}",
        duration_ms=duration_ms,
        hints_used=0,
    ))
    return record


register_layer("L0-pre", _l0_pre_layer)
register_layer("L1", run_l1)
register_layer("L2", run_l2)
register_layer("L3", run_l3)
register_layer("L4", run_l4)
register_layer("L5", run_l5)
register_layer("L6", run_l6)
register_layer("L7", run_l7)
register_layer("L8", run_l8)
register_layer("L0-post", _l0_post_layer)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def run(
    blind_path: str | Path,
    settings: Settings = DEFAULT_SETTINGS,
    output_root: str | Path = "runs",
) -> Path:
    """Execute all registered layers over a blind corpus.

    Returns the path to the output directory created for this run.
    """
    blind_items = load_blind(blind_path)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(output_root) / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    with (out_dir / "records.jsonl").open("w", encoding="utf-8") as fout:
        for item in blind_items:
            record = AnalysisRecord(
                item_id=item.id,
                text=item.text,
                target_ages=item.target_ages,
            )
            for layer_name, layer_fn in _LAYER_REGISTRY:
                start = time.monotonic()
                try:
                    record = layer_fn(record, settings)
                except Exception as exc:
                    duration_ms = round((time.monotonic() - start) * 1000, 3)
                    record.trace.append(LayerTrace(
                        layer=layer_name,
                        status="ERROR",
                        reason=f"{type(exc).__name__}: {exc}",
                        duration_ms=duration_ms,
                        hints_used=0,
                    ))
            fout.write(record.model_dump_json() + "\n")

    meta = {
        "timestamp": ts,
        "git_sha": _git_sha(),
        "blind_path": str(blind_path),
        "config": {
            "MAX_INPUT_CHARS": settings.MAX_INPUT_CHARS,
            "MIN_INPUT_CHARS": settings.MIN_INPUT_CHARS,
            "MAX_NON_ASCII_RATIO": settings.MAX_NON_ASCII_RATIO,
            "L3_TOP_K": settings.L3_TOP_K,
            "L4_BACKEND": settings.L4_BACKEND,
            "L5_BACKEND": settings.L5_BACKEND,
            "L6_BACKEND": settings.L6_BACKEND,
            "L7_BACKEND": settings.L7_BACKEND,
            "L8_BACKEND": settings.L8_BACKEND,
            "L5_QA_WEIGHTS": settings.L5_QA_WEIGHTS,
            "L5_RESOLUTION_THRESHOLDS": dict(settings.L5_RESOLUTION_THRESHOLDS),
        },
        "layers": [name for name, _ in _LAYER_REGISTRY],
        "item_count": len(blind_items),
    }
    (out_dir / "run_meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    return out_dir


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m doubletake.runner",
        description="Run the DoubleTake pipeline over a blind JSONL corpus.",
    )
    parser.add_argument(
        "--blind", required=True, metavar="PATH",
        help="Path to the blind JSONL corpus file.",
    )
    parser.add_argument(
        "--output", default="runs", metavar="DIR",
        help="Root directory for run output (default: runs).",
    )
    parser.add_argument(
        "--eval", default=None, metavar="GOLD_PATH",
        help="Optional path to gold JSONL corpus to evaluate run output against.",
    )
    args = parser.parse_args(argv)

    out_dir = run(blind_path=args.blind, output_root=args.output)
    print(f"Run complete. Output: {out_dir}")

    if args.eval:
        eval_res = evaluate_run(out_dir / "records.jsonl", args.eval)
        eval_file = out_dir / "evaluation.json"
        eval_file.write_text(json.dumps(eval_res, indent=2), encoding="utf-8")
        print("Evaluation summary:")
        print(f"  Classification accuracy: {eval_res['classification_accuracy']:.1%} ({eval_res['correct_classification']}/{eval_res['total_items']})")
        print(f"  Age verdict match rate:  {eval_res['age_accuracy']:.1%} ({eval_res['correct_age_evals']}/{eval_res['total_age_evals']})")
        print(f"  Report written to: {eval_file}")


if __name__ == "__main__":
    _main()
