"""Run L5 calibration: 5 passes × 10 fixture items → docs/L5_CALIBRATION.md.

Usage:
    py -3.11 scripts/run_l5_calibration.py

Requires the active backend's API key:
  gemini   → GEMINI_API_KEY
  anthropic → ANTHROPIC_API_KEY
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
            score_str = f"{result.resolution_score:.3f}" if result.resolution_score is not None else "None"
            print(
                f"  {fixture['id']:3s} {match} "
                f"got={result.resolution_status:25s} "
                f"exp={expected:25s} "
                f"score={score_str} "
                f"({elapsed}ms)"
            )
            time.sleep(DEFAULT_SETTINGS.L5_CALL_PAUSE_SECONDS)

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
    backend = DEFAULT_SETTINGS.L5_BACKEND
    if backend == "gemini":
        model_id = DEFAULT_SETTINGS.L5_MODEL_GEMINI
    else:
        model_id = "claude-sonnet-4-6"
    lines.append(f"Generated: {ts}  ")
    lines.append(f"Backend: `{backend}`  ")
    lines.append(f"Model: `{model_id}`  ")
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
        statuses = [r["status"] for r in runs]
        pass_count = sum(1 for s in statuses if s == expected)
        numeric_scores = [r["score"] for r in runs if r["score"] is not None]
        if numeric_scores:
            score_range = (
                f"{min(numeric_scores):.3f} / "
                f"{sum(numeric_scores)/len(numeric_scores):.3f} / "
                f"{max(numeric_scores):.3f}"
            )
        else:
            score_range = "None (INSUFFICIENT_CONTEXT)"
        stable = "Yes" if len(set(statuses)) == 1 else "No"
        lines.append(
            f"| {fid} | {genre} | {expected} | {pass_count}/{_N_RUNS} "
            f"| {score_range} | {stable} |"
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
            score_cell = f"{run['score']:.4f}" if run["score"] is not None else "None"
            lines.append(
                f"| {i} | `{run['status']}` | {score_cell} | {subscore_str} |"
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
    lines.append("- P2 (`explain`) is a deliberately weak compound-split item; "
                 "RESOLUTION_FAIL is expected because the punchline does not "
                 "exploit the resegmentation contrast.")
    lines.append("- N1 (`bank`) has anchoring_status=ONE_SENSE_ONLY; L5 short-circuits "
                 "before calling the LLM and always returns INSUFFICIENT_CONTEXT "
                 "(score=None).")
    lines.append("- S1/S2 are a minimal pair for polarity: S1 (skeletons don't fight → "
                 "PASS) and S2 (skeletons do fight → FAIL) test polarity_or_direction.")
    lines.append("- Gemini backend uses temperature=0.0 via GenerateContentConfig; "
                 "score variance across runs should be lower than Anthropic.")
    lines.append("")

    _OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
