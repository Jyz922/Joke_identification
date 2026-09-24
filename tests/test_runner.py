"""Tests for doubletake.runner and layer execution registry."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from doubletake.config import DEFAULT_SETTINGS, Settings
from doubletake.enums import (
    AnchorRelation,
    AnchoringStatus,
    DistinctnessStatus,
    Genre,
    MainClassification,
    ResolutionStatus,
    ScopeLabel,
)
from doubletake.layers import (
    run_l1,
    run_l2,
    run_l3,
    run_l4,
    run_l5,
    run_l6,
    run_l7,
    run_l8,
)
from doubletake.runner import (
    _LAYER_REGISTRY,
    _l0_post_layer,
    _l0_pre_layer,
    _main,
    clear_registry,
    register_layer,
    run,
)
from doubletake.schema import AnalysisRecord, FinalVerdict, L4Result, L5QAResult, L6Result, LayerTrace

_SAMPLE_BLIND = Path(__file__).parent / "fixtures" / "sample_blind.jsonl"
_SAMPLE_GOLD = Path(__file__).parent / "fixtures" / "sample_gold.jsonl"


class TestRunnerPipeline:

    def test_run_executes_pipeline_and_produces_artifacts(self, tmp_path: Path) -> None:
        """Integration test: runner executes over blind items, writes records and run_meta."""
        out_root = tmp_path / "runs"
        run_dir = run(_SAMPLE_BLIND, DEFAULT_SETTINGS, output_root=out_root)

        assert run_dir.exists()
        records_file = run_dir / "records.jsonl"
        meta_file = run_dir / "run_meta.json"
        assert records_file.exists()
        assert meta_file.exists()

        records = [json.loads(line) for line in records_file.read_text(encoding="utf-8").splitlines() if line]
        assert len(records) == 3  # sample_blind.jsonl has 3 items (J01, J02, J03)

        first = records[0]
        assert first["item_id"] == "J01"
        assert first["l1_result"] is not None
        assert first["l1_result"]["genre"] == Genre.QA_RIDDLE
        assert first["l2_result"] is not None
        assert len(first["l2_result"]["senses"]) > 0
        assert first["l3_result"] is not None
        assert len(first["l3_result"]["candidates"]) > 0
        assert first["final"] is not None
        assert first["final"]["scope_label"] in [s.value for s in ScopeLabel]

        # Traces confirm all pipeline layers ran
        trace_layers = [t["layer"] for t in first["trace"]]
        assert "L0-pre" in trace_layers
        assert "L1" in trace_layers
        assert "L2" in trace_layers
        assert "L3" in trace_layers
        assert "L4" in trace_layers
        assert "L5" in trace_layers
        assert "L6" in trace_layers
        assert "L7" in trace_layers
        assert "L8" in trace_layers
        assert "L0-post" in trace_layers

        # Meta snapshot
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        assert "git_sha" in meta
        assert "config" in meta

    def test_run_with_eval_cli(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        out_root = tmp_path / "runs"
        _main([
            "--blind", str(_SAMPLE_BLIND),
            "--eval", str(_SAMPLE_GOLD),
            "--output", str(out_root),
        ])
        captured = capsys.readouterr().out
        assert "Run complete" in captured
        assert "Evaluation summary" in captured
        eval_files = list(out_root.glob("*/evaluation.json"))
        assert len(eval_files) == 1
        eval_data = json.loads(eval_files[0].read_text(encoding="utf-8"))
        assert eval_data["total_items"] == 3
        assert "confusion_matrix" in eval_data

    def test_runner_catches_layer_exceptions_and_continues(self, tmp_path: Path) -> None:
        """Issue e: runner catches any layer exception and records LayerTrace(status='ERROR')."""
        saved_registry = list(_LAYER_REGISTRY)
        clear_registry()
        try:
            def bad_layer(rec: AnalysisRecord, st: Settings) -> AnalysisRecord:
                raise RuntimeError("Controlled crash for testing")

            def good_layer(rec: AnalysisRecord, st: Settings) -> AnalysisRecord:
                rec.text = rec.text.upper()
                rec.trace.append(LayerTrace(layer="GoodLayer", status="OK", duration_ms=1.0))
                return rec

            register_layer("GoodLayer", good_layer)
            register_layer("FailingLayer", bad_layer)

            blind_file = tmp_path / "test_blind.jsonl"
            blind_file.write_text(
                json.dumps({"id": "T01", "text": "test item", "target_ages": [8]}) + "\n",
                encoding="utf-8",
            )

            out_dir = run(blind_file, DEFAULT_SETTINGS, output_root=tmp_path / "runs")
            records = [json.loads(line) for line in (out_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()]
            assert len(records) == 1
            rec = records[0]

            assert rec["text"] == "TEST ITEM"
            traces = {t["layer"]: t for t in rec["trace"]}
            assert traces["GoodLayer"]["status"] == "OK"
            assert traces["FailingLayer"]["status"] == "ERROR"
            assert "Controlled crash" in traces["FailingLayer"]["reason"]
        finally:
            clear_registry()
            _LAYER_REGISTRY.extend(saved_registry)

    def test_registry_clearing_and_register(self) -> None:
        saved_registry = list(_LAYER_REGISTRY)
        clear_registry()
        try:
            assert len(_LAYER_REGISTRY) == 0
            register_layer("L0-pre", _l0_pre_layer)
            assert len(_LAYER_REGISTRY) == 1
            assert _LAYER_REGISTRY[0][0] == "L0-pre"
        finally:
            clear_registry()
            _LAYER_REGISTRY.extend(saved_registry)


class TestLayerSignatures:
    """Issue f: assert every layer function in layers.py satisfies (record, settings) -> record."""

    @pytest.mark.parametrize("layer_fn", [
        run_l1, run_l2, run_l3, run_l4, run_l5, run_l6, run_l7, run_l8,
    ])
    def test_layer_callable_signature(self, layer_fn: object) -> None:
        sig = inspect.signature(layer_fn)  # type: ignore[arg-type]
        params = list(sig.parameters.values())
        assert len(params) == 2, f"{layer_fn.__name__} must take exactly 2 arguments"
        assert params[0].name == "record"
        assert params[1].name == "settings"


class TestL0PostEvidenceHandling:

    def test_l0_post_recognizes_resegmentation_as_compound_split(self) -> None:
        rec = AnalysisRecord(item_id="auto", text="autobiography", target_ages=[8])
        rec.l4_result = L4Result(
            sense_a="self life story",
            sense_a_anchor_quote="autobiography",
            sense_b="car life story",
            sense_b_anchor_quote="autobiography",
            anchor_relation=AnchorRelation.RESEGMENTATION,
            anchoring_status=AnchoringStatus.PASS,
            resolving_sense="sense_b",
        )
        rec = _l0_post_layer(rec, DEFAULT_SETTINGS)
        assert rec.final is not None
        assert rec.final.scope_label == ScopeLabel.COMPOUND_SPLIT

    def test_l0_post_recognizes_homograph_when_anchored(self) -> None:
        rec = AnalysisRecord(item_id="trunk", text="elephant trunk", target_ages=[8])
        rec.l4_result = L4Result(
            sense_a="nose",
            sense_a_anchor_quote="elephant",
            sense_b="chest",
            sense_b_anchor_quote="trunk",
            anchor_relation=AnchorRelation.SEPARATE_CONTEXTS,
            anchoring_status=AnchoringStatus.PASS,
            resolving_sense="sense_b",
        )
        rec = _l0_post_layer(rec, DEFAULT_SETTINGS)
        assert rec.final is not None
        assert rec.final.scope_label == ScopeLabel.HOMOGRAPH

    def test_l0_post_assigns_confidence_score(self) -> None:
        rec = AnalysisRecord(item_id="conf_test", text="test text", target_ages=[8])
        rec.l5_result = L5QAResult(
            genre=Genre.QA_RIDDLE,
            resolution_status=ResolutionStatus.RESOLUTION_PASS,
            resolution_score=0.90,
            subscores={"polarity_or_direction": 0.9},
        )
        rec.l6_result = L6Result(
            distinctness_status=DistinctnessStatus.L6_SKIPPED_NO_PARAPHRASE,
        )
        rec = _l0_post_layer(rec, DEFAULT_SETTINGS)
        assert rec.confidence is not None
        assert rec.confidence == round(0.90 * 0.85, 3)

    def test_l0_post_handles_out_of_scope(self) -> None:
        from doubletake.l0_scope import LayerEvidence, assign_scope_label
        rec = AnalysisRecord(item_id="oos_test", text="homophone joke", target_ages=[8])
        evidence = LayerEvidence(is_homophone=True, has_homograph=False)
        rec.final = FinalVerdict(
            main_classification=MainClassification.OUT_OF_SCOPE_HOMOPHONE,
            scope_label=assign_scope_label(evidence),
        )
        rec = _l0_post_layer(rec, DEFAULT_SETTINGS)
        assert rec.final.scope_label in (ScopeLabel.OUT_OF_SCOPE_HOMOPHONE, ScopeLabel.NO_SCOPE_MECHANISM)
