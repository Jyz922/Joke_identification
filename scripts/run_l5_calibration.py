"""Run L5 calibration: 5 passes × 6 fixture items → docs/L5_CALIBRATION.md.

Usage:
    py -3.11 scripts/run_l5_calibration.py

Requires ANTHROPIC_API_KEY to be set in the environment.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add src to import path when running as a script from the project root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from doubletake.config import DEFAULT_SETTINGS
from doubletake.enums import AnchoringStatus, Genre, ResolutionStatus
from doubletake.l5_resolution import resolve_l5
from doubletake.schema import AnalysisRecord, L1Result, L4Result

_FIXTURES_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "l5_anchors.jsonl"
_OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "L5_CALIBRATION.md"
_N_RUNS = 5


def _build_record(fixture: dict) -> tuple[AnalysisRecord, str]:
    l4d = fixture["l4_result"]
    l4 = L4Result(
        sense_a=l4d["sense_a"],
        sense_a_anchor_quote=l4d["sense_a_anchor_quote"],
        sense_b=l4d["sense_b"],
        sense_b_anchor_quote=l4d["sense_b_anchor_quote"],
        anchor_relation=l4d.get("anchor_relation"),
        anchoring_status=l4d["anchoring_status"],
    )
    record = AnalysisRecord(
        item_id=fixture["id"], text=fixture["text"], target_ages=[8]
    )
    record.l1_result = L1Result(
        genre=Genre(fixture["genre"]), tokens=[], lemmas=[], pos_tags=[]
    )
    record.l4_result = l4
    return record, fixture["ambiguous_term"]


def main() -> None:
    fixtures = [
        json.loads(line)
        for line in _FIXTURES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    # results[item_id][run_index] = {"status": ..., "score": ..., "subscores": ...}
    results: dict[str, list[dict]] = {f["id"]: [] for f in fixtures}

    print(f"Running {_N_RUNS} passes over {len(fixtures)} fixtures...")
    for run_idx in range(_N_RUNS):
        print(f"\n--- Run {run_idx + 1}/{_N_RUNS} ---")
        for fixture in fixtures:
            record, term = _build_record(fixture)
            t0 = time.monotonic()
            result = resolve_l5(record, DEFAULT_SETTINGS, ambiguous_term=term)
            elapsed = round((time.monotonic() - t0) * 1000)
            results[fixture["id"]].append({
                "status": result.resolution_status,
                "score": result.resolution_score,
                "subscores": result.subscores,
                "elapsed_ms": elapsed,
            })
            expected = fixture["expected_l5_status"]
            match = "✓" if result.resolution_status == expected else "✗"
            print(
                f"  {fixture['id']:3s} {match} "
                f"got={result.resolution_status:25s} "
                f"exp={expected:25s} "
                f"score={result.resolution_score:.3f} "
                f"({elapsed}ms)"
            )

    _write_calibration_doc(fixtures, results)
    print(f"\nCalibration written to {_OUTPUT_PATH}")


def _write_calibration_doc(
    fixtures: list[dict],
    results: dict[str, list[dict]],
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    lines.append("# L5 Calibration Report")
    lines.append("")
    lines.append(f"Generated: {ts}  ")
    lines.append(f"Model: `claude-sonnet-4-6`  ")
    lines.append(f"Runs: {_N_RUNS}  ")
    lines.append(f"Threshold: {DEFAULT_SETTINGS.L5_RESOLUTION_THRESHOLD}  ")
    lines.append("")

    lines.append("## Summary table")
    lines.append("")
    lines.append("| ID | Genre | Expected | Runs pass | Scores (min / mean / max) | Stable? |")
    lines.append("|---|---|---|---|---|---|")

    for fixture in fixtures:
        fid = fixture["id"]
        genre = fixture["genre"]
        expected = fixture["expected_l5_status"]
        runs = results[fid]
        scores = [r["score"] for r in runs]
        statuses = [r["status"] for r in runs]
        pass_count = sum(1 for s in statuses if s == expected)
        score_min = min(scores)
        score_mean = sum(scores) / len(scores)
        score_max = max(scores)
        stable = "Yes" if len(set(statuses)) == 1 else "No"
        lines.append(
            f"| {fid} | {genre} | {expected} | {pass_count}/{_N_RUNS} "
            f"| {score_min:.3f} / {score_mean:.3f} / {score_max:.3f} | {stable} |"
        )

    lines.append("")
    lines.append("## Per-item detail")
    lines.append("")

    for fixture in fixtures:
        fid = fixture["id"]
        lines.append(f"### {fid} — {fixture['text'][:70]}")
        lines.append("")
        lines.append(f"- **Genre:** {fixture['genre']}")
        lines.append(f"- **Ambiguous term:** `{fixture['ambiguous_term']}`")
        lines.append(f"- **Expected status:** `{fixture['expected_l5_status']}`")
        lines.append(f"- **Anchor relation:** `{fixture['l4_result'].get('anchor_relation', 'null')}`")
        lines.append(f"- **Anchoring status:** `{fixture['l4_result']['anchoring_status']}`")
        lines.append("")

        lines.append("| Run | Status | Score | Subscores |")
        lines.append("|---|---|---|---|")
        for i, run in enumerate(results[fid], 1):
            subscore_str = ", ".join(
                f"{k}={v:.2f}" for k, v in run["subscores"].items()
            )
            lines.append(
                f"| {i} | `{run['status']}` | {run['score']:.4f} | {subscore_str} |"
            )

        # Analysis
        statuses = [r["status"] for r in results[fid]]
        unique = set(statuses)
        expected = fixture["expected_l5_status"]
        match_count = sum(1 for s in statuses if s == expected)

        lines.append("")
        if match_count == _N_RUNS:
            lines.append(f"**Verdict:** All {_N_RUNS} runs match expected `{expected}`.")
        elif match_count == 0:
            lines.append(
                f"**Verdict:** No run matched expected `{expected}` "
                f"(got {unique}). See notes below."
            )
        else:
            lines.append(
                f"**Verdict:** {match_count}/{_N_RUNS} runs match expected `{expected}` "
                f"(unstable — statuses varied: {unique})."
            )
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- A1 (`explain`) is a deliberately weak compound-split item; "
                 "RESOLUTION_FAIL is expected if contrast_strength is scored low.")
    lines.append("- X1 (`bank`) has anchoring_status=ONE_SENSE_ONLY; L5 short-circuits "
                 "before calling the LLM and always returns INSUFFICIENT_CONTEXT.")
    lines.append("- Score variance across runs reflects model non-determinism (no "
                 "temperature=0 equivalent in SDK 1.7.0; effort=default/high).")
    lines.append("")

    _OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
