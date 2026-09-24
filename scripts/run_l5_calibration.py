"""Resumable L5 calibration: 5 passes × 10 fixtures → runs/l5_calibration.jsonl
                                                          → docs/L5_CALIBRATION.md

Usage:
    py -3.11 scripts/run_l5_calibration.py [--resume | --fresh] [--probe]

Flags:
    --resume   (default) Skip (item_id, run_index) pairs already in the JSONL.
    --fresh    Delete the JSONL and start from scratch.
    --probe    Make one cheap call; print OK/UNAVAILABLE and exit without running.

Requires GEMINI_API_KEY (or ANTHROPIC_API_KEY when L5_BACKEND=anthropic).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from doubletake.config import DEFAULT_SETTINGS
from doubletake.enums import AnchoringStatus, Genre, ResolutionStatus
from doubletake.l5_resolution import resolve_l5
from doubletake.schema import AnalysisRecord, L1Result, L4Result

_FIXTURES_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "l5_anchors.jsonl"
_RUNS_DIR = Path(__file__).parent.parent / "runs"
_JSONL_PATH = _RUNS_DIR / "l5_calibration.jsonl"
_RAW_DIR = _RUNS_DIR / "raw"
_OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "L5_CALIBRATION.md"
_N_RUNS = 5


# ---------------------------------------------------------------------------
# Record building
# ---------------------------------------------------------------------------

def _load_fixtures() -> list[dict]:
    return [
        json.loads(line)
        for line in _FIXTURES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _build_record(fixture: dict) -> tuple[AnalysisRecord, str]:
    l4d = fixture["l4_result"]
    l4 = L4Result(
        sense_a=l4d["sense_a"],
        sense_a_anchor_quote=l4d["sense_a_anchor_quote"],
        sense_b=l4d["sense_b"],
        sense_b_anchor_quote=l4d["sense_b_anchor_quote"],
        anchor_relation=l4d.get("anchor_relation"),
        anchoring_status=l4d["anchoring_status"],
        resolving_sense=l4d.get("resolving_sense"),
    )
    record = AnalysisRecord(
        item_id=fixture["id"], text=fixture["text"], target_ages=[8]
    )
    record.l1_result = L1Result(
        genre=Genre(fixture["genre"]), tokens=[], lemmas=[], pos_tags=[]
    )
    record.l4_result = l4
    return record, fixture["ambiguous_term"]


# ---------------------------------------------------------------------------
# Resume support
# ---------------------------------------------------------------------------

def _load_completed() -> set[tuple[str, int]]:
    if not _JSONL_PATH.exists():
        return set()
    completed: set[tuple[str, int]] = set()
    for line in _JSONL_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            completed.add((row["item_id"], row["run_index"]))
    return completed


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

def probe() -> None:
    fixtures = _load_fixtures()
    fixture = fixtures[0]
    record, term = _build_record(fixture)
    print(f"Probe: {DEFAULT_SETTINGS.L5_BACKEND} / {DEFAULT_SETTINGS.L5_MODEL_GEMINI}, fixture {fixture['id']}")
    try:
        result = resolve_l5(record, DEFAULT_SETTINGS, ambiguous_term=term)
        print(f"OK: verdict={result.resolution_status} model={result.model_used} retries={result.retries}")
        sys.exit(0)
    except Exception as e:
        print(f"UNAVAILABLE: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main run loop
# ---------------------------------------------------------------------------

def run(fresh: bool) -> None:
    _RUNS_DIR.mkdir(exist_ok=True)
    _RAW_DIR.mkdir(exist_ok=True)

    if fresh and _JSONL_PATH.exists():
        _JSONL_PATH.unlink()
        print("--fresh: deleted existing JSONL")

    fixtures = _load_fixtures()
    completed = _load_completed() if not fresh else set()
    total = _N_RUNS * len(fixtures)
    remaining = total - len(completed)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] fixtures={len(fixtures)} runs={_N_RUNS} completed={len(completed)} remaining={remaining}")

    with _JSONL_PATH.open("a", encoding="utf-8") as jf:
        for run_idx in range(_N_RUNS):
            print(f"\n--- Run {run_idx + 1}/{_N_RUNS} ---")
            for fixture in fixtures:
                pair = (fixture["id"], run_idx)
                if pair in completed:
                    print(f"  {fixture['id']:3s} run={run_idx} SKIP")
                    continue

                record, term = _build_record(fixture)
                diag: dict = {}
                t0 = time.monotonic()
                try:
                    result = resolve_l5(
                        record, DEFAULT_SETTINGS, ambiguous_term=term, diagnostics=diag
                    )
                except Exception as e:
                    print(f"  {fixture['id']:3s} run={run_idx} ERROR ({type(e).__name__}): {e}")
                    continue  # not written; will retry on resume

                elapsed_ms = round((time.monotonic() - t0) * 1000)

                # Persist the model's ACTUAL response (verbatim text + finish_reason),
                # not our parsed subscores — otherwise failed parses leave no evidence.
                # diag is empty for short-circuited items (no LLM call, e.g. N1).
                raw_path = _RAW_DIR / f"{fixture['id']}_{run_idx:02d}.json"
                raw_path.write_text(
                    json.dumps(
                        {
                            "raw_text": diag.get("raw_text", ""),
                            "finish_reason": diag.get("finish_reason", ""),
                            "thoughts_token_count": diag.get("thoughts_tokens"),
                            "subscores": result.subscores,
                        },
                        indent=2,
                        default=str,
                    ),
                    encoding="utf-8",
                )

                row = {
                    "item_id": fixture["id"],
                    "run_index": run_idx,
                    "backend": DEFAULT_SETTINGS.L5_BACKEND,
                    "model_used": result.model_used,
                    "fallback_used": result.fallback_used,
                    "subscores": result.subscores,
                    "resolution_score": result.resolution_score,
                    "verdict": str(result.resolution_status),
                    "finish_reason": diag.get("finish_reason", ""),
                    "thoughts_token_count": diag.get("thoughts_tokens"),
                    "retries": result.retries,
                    "wall_clock_ms": elapsed_ms,
                    "raw_response_path": str(raw_path.relative_to(Path(__file__).parent.parent)),
                }
                jf.write(json.dumps(row) + "\n")
                jf.flush()

                match = "OK" if str(result.resolution_status) == fixture["expected_l5_status"] else "!!"
                score_str = f"{result.resolution_score:.3f}" if result.resolution_score is not None else "None"
                print(
                    f"  {fixture['id']:3s} {match} verdict={str(result.resolution_status):30s} "
                    f"score={score_str} model={result.model_used}"
                    f"{' [fallback]' if result.fallback_used else ''} "
                    f"retries={result.retries} ({elapsed_ms}ms)"
                )

                time.sleep(DEFAULT_SETTINGS.L5_CALL_PAUSE_SECONDS)

    _write_calibration_doc()
    print(f"\nCalibration doc written to {_OUTPUT_PATH}")


# ---------------------------------------------------------------------------
# Document generation (built entirely from the JSONL)
# ---------------------------------------------------------------------------

def _write_calibration_doc() -> None:
    fixtures = _load_fixtures()
    fixture_ids = [f["id"] for f in fixtures]
    fixture_map = {f["id"]: f for f in fixtures}

    # Load all rows into grid[item_id][run_index] = row
    grid: dict[str, dict[int, dict]] = {fid: {} for fid in fixture_ids}
    if _JSONL_PATH.exists():
        for line in _JSONL_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                grid[row["item_id"]][row["run_index"]] = row

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    lines += [
        "# L5 Calibration Report",
        "",
        f"Generated: {ts}  ",
        f"Backend: `{DEFAULT_SETTINGS.L5_BACKEND}`  ",
        f"Primary model: `{DEFAULT_SETTINGS.L5_MODEL_GEMINI}`  ",
        f"Fallback chain: `{DEFAULT_SETTINGS.L5_MODEL_GEMINI_CHAIN}`  ",
        f"Target runs: {_N_RUNS}  ",
        f"Thresholds: { {str(g): t for g, t in DEFAULT_SETTINGS.L5_RESOLUTION_THRESHOLDS.items()} }  ",
        "",
    ]

    # --- Q1: Full table ---
    lines += ["## 1. Full result table", ""]
    header = "| ID | Genre | Expected | " + " | ".join(f"Run {i+1}" for i in range(_N_RUNS)) + " | Stable |"
    sep = "|---|---|---|" + "|".join(["---"] * _N_RUNS) + "|---|"
    lines += [header, sep]

    for fid in fixture_ids:
        f = fixture_map[fid]
        expected = f["expected_l5_status"]
        runs_data = grid[fid]
        cells = []
        verdicts = []
        for r in range(_N_RUNS):
            if r in runs_data:
                row = runs_data[r]
                v = row["verdict"]
                score = row["resolution_score"]
                s = f"{score:.3f}" if score is not None else "None"
                match = "OK" if v == expected else "!!"
                cells.append(f"{match} {v.replace('RESOLUTION_', '')[:4]} {s}")
                verdicts.append(v)
            else:
                cells.append("INCOMPLETE")
        stable = "Yes" if len(set(verdicts)) == 1 and len(verdicts) == _N_RUNS else (
            "INCOMPLETE" if len(verdicts) < _N_RUNS else "No"
        )
        lines.append(f"| {fid} | {f['genre'].replace('_', ' ')} | {expected} | " +
                     " | ".join(cells) + f" | {stable} |")

    lines.append("")

    # --- Per-item detail with subscores ---
    lines += ["## Per-item subscores", ""]
    qa_weights = DEFAULT_SETTINGS.L5_QA_WEIGHTS

    for fid in fixture_ids:
        f = fixture_map[fid]
        runs_data = grid[fid]
        lines += [f"### {fid} — {f['text'][:70]}", ""]
        lines += [f"- **Genre:** {f['genre']}", f"- **Expected:** `{f['expected_l5_status']}`",
                  f"- **Ambiguous term:** `{f['ambiguous_term']}`", ""]

        if not runs_data:
            lines += ["*No data yet.*", ""]
            continue

        # Build subscore header from first available run
        first_row = next(iter(runs_data.values()))
        subscore_keys = list(first_row["subscores"].keys()) if first_row["subscores"] else []

        if subscore_keys:
            lines.append("| Run | Verdict | Score | " + " | ".join(subscore_keys) + " | Model | Retries |")
            lines.append("|---|---|---|" + "|".join(["---"] * len(subscore_keys)) + "|---|---|")
            for r in range(_N_RUNS):
                if r in runs_data:
                    row = runs_data[r]
                    score_str = f"{row['resolution_score']:.4f}" if row["resolution_score"] is not None else "None"
                    subscore_cells = [f"{row['subscores'].get(k, 'N/A'):.2f}" if isinstance(row['subscores'].get(k), float) else "N/A"
                                      for k in subscore_keys]
                    model_label = row["model_used"] + (" [fb]" if row["fallback_used"] else "")
                    lines.append(f"| {r+1} | `{row['verdict']}` | {score_str} | " +
                                 " | ".join(subscore_cells) + f" | {model_label} | {row['retries']} |")
                else:
                    lines.append(f"| {r+1} | INCOMPLETE | — |" + " — |" * len(subscore_keys) + " — | — |")
        else:
            lines.append("| Run | Verdict | Score | Model |")
            lines.append("|---|---|---|---|")
            for r in range(_N_RUNS):
                if r in runs_data:
                    row = runs_data[r]
                    score_str = f"{row['resolution_score']:.4f}" if row["resolution_score"] is not None else "None"
                    lines.append(f"| {r+1} | `{row['verdict']}` | {score_str} | {row['model_used']} |")
                else:
                    lines.append(f"| {r+1} | INCOMPLETE | — | — |")

        lines.append("")

    # --- Q2: Is polarity_or_direction binary? ---
    lines += ["## 2. polarity_or_direction: binary or graded?", ""]
    polarity_vals: list[float] = []
    for fid in fixture_ids:
        for row in grid[fid].values():
            v = row["subscores"].get("polarity_or_direction")
            if v is not None:
                polarity_vals.append(float(v))

    if not polarity_vals:
        lines += ["*No data yet.*", ""]
    else:
        near_binary = sum(1 for v in polarity_vals if v < 0.1 or v > 0.9)
        graded = len(polarity_vals) - near_binary
        lines += [
            f"Observed `polarity_or_direction` values across {len(polarity_vals)} QA/applicable calls:",
            f"- Near-binary (< 0.1 or > 0.9): **{near_binary}** ({100*near_binary//len(polarity_vals)}%)",
            f"- Graded (0.1–0.9): **{graded}**",
            "",
            f"Min: {min(polarity_vals):.3f}, Max: {max(polarity_vals):.3f}, "
            f"Mean: {sum(polarity_vals)/len(polarity_vals):.3f}",
            "",
        ]
        if graded == 0:
            lines += [
                "**Verdict: BINARY** — all observed values are near 0.0 or 1.0. "
                "The model treats polarity as a binary signal.",
                "",
            ]
        else:
            lines += [
                "**Verdict: GRADED** — some values fall between 0.1 and 0.9.",
                "",
            ]

    # --- Q3: Does polarity alone determine the verdict? ---
    lines += ["## 3. Does polarity alone determine the verdict?", ""]
    qa_t = DEFAULT_SETTINGS.L5_RESOLUTION_THRESHOLDS[Genre.QA_RIDDLE]
    pol_w = DEFAULT_SETTINGS.L5_QA_WEIGHTS["polarity_or_direction"]
    others_max = 1.0 - pol_w
    lines += [
        f"With weight `polarity_or_direction = {pol_w}` and QA threshold `{qa_t}`:",
        "",
        f"- If `polarity = 0.0`: maximum score from other four features = {others_max:.2f}"
        + (f" < {qa_t} → **always FAIL** regardless of others." if others_max < qa_t
           else f" ≥ {qa_t} → can still PASS on the other features alone."),
        f"- If `polarity = 1.0`: score ≥ {pol_w}"
        + (" → **guaranteed PASS**." if pol_w >= qa_t
           else f". Needs other features ≥ {qa_t - pol_w:.2f} for PASS."),
        "",
    ]

    # From actual data: find any case where polarity=1 but FAIL, or polarity=0 but PASS
    polarity_1_fail = []
    polarity_0_pass = []
    for fid in fixture_ids:
        for r, row in grid[fid].items():
            p = row["subscores"].get("polarity_or_direction")
            v = row["verdict"]
            if p is not None:
                if p > 0.9 and v == "RESOLUTION_FAIL":
                    polarity_1_fail.append(f"{fid}/run{r+1}")
                if p < 0.1 and v == "RESOLUTION_PASS":
                    polarity_0_pass.append(f"{fid}/run{r+1}")

    if not polarity_vals:
        lines += ["*No data yet.*", ""]
    else:
        if polarity_1_fail:
            lines += [f"**Data confirms non-inert threshold**: polarity=1 but FAIL in: {polarity_1_fail}", ""]
        else:
            lines += ["From the data: no case where polarity≈1.0 led to RESOLUTION_FAIL. "
                      "In practice polarity dominates, but the threshold is not mathematically inert.", ""]
        if polarity_0_pass:
            lines += [f"Polarity=0 but PASS (should be impossible): {polarity_0_pass}", ""]

    # --- Q4: S1 vs S2 separation ---
    lines += ["## 4. S1 vs S2 separation (polarity minimal pair)", ""]
    s1_scores = [grid["S1"][r]["resolution_score"] for r in range(_N_RUNS) if r in grid["S1"] and grid["S1"][r]["resolution_score"] is not None]
    s2_scores = [grid["S2"][r]["resolution_score"] for r in range(_N_RUNS) if r in grid["S2"] and grid["S2"][r]["resolution_score"] is not None]

    if s1_scores and s2_scores:
        s1_mean = sum(s1_scores) / len(s1_scores)
        s2_mean = sum(s2_scores) / len(s2_scores)
        gap = s1_mean - s2_mean
        lines += [
            f"- S1 (PASS expected): scores {[f'{s:.3f}' for s in s1_scores]}, mean = **{s1_mean:.3f}**",
            f"- S2 (FAIL expected): scores {[f'{s:.3f}' for s in s2_scores]}, mean = **{s2_mean:.3f}**",
            f"- Gap (S1 − S2): **{gap:.3f}**",
            "",
        ]
        if gap < 0.1:
            lines += ["**Warning**: gap < 0.10 — L5 is barely separating the polarity minimal pair.", ""]
        elif gap < 0.3:
            lines += ["Gap is modest. L5 separates the pair but polarity signal is weak.", ""]
        else:
            lines += ["Gap is substantial. L5 reliably separates the polarity minimal pair.", ""]
    elif s1_scores or s2_scores:
        lines += ["*S1 or S2 partially complete — gap cannot be computed yet.*", ""]
    else:
        lines += ["*No data yet.*", ""]

    # --- Q5: E1 vs X1 separation ---
    lines += ["## 5. E1 vs X1 separation (relevance minimal pair)", ""]
    e1_scores = [grid["E1"][r]["resolution_score"] for r in range(_N_RUNS) if r in grid["E1"] and grid["E1"][r]["resolution_score"] is not None]
    x1_scores = [grid["X1"][r]["resolution_score"] for r in range(_N_RUNS) if r in grid["X1"] and grid["X1"][r]["resolution_score"] is not None]

    if e1_scores and x1_scores:
        e1_mean = sum(e1_scores) / len(e1_scores)
        x1_mean = sum(x1_scores) / len(x1_scores)
        gap = e1_mean - x1_mean
        lines += [
            f"- E1 (PASS expected — trunk/pockets joke): scores {[f'{s:.3f}' for s in e1_scores]}, mean = **{e1_mean:.3f}**",
            f"- X1 (FAIL expected — trunk/grey mammals non-joke): scores {[f'{s:.3f}' for s in x1_scores]}, mean = **{x1_mean:.3f}**",
            f"- Gap (E1 − X1): **{gap:.3f}**",
            "",
        ]
        if gap < 0.1:
            lines += ["**Warning**: gap < 0.10 — L5 is not separating the relevance minimal pair. "
                      "This is the most informative number in the run.", ""]
        elif gap < 0.3:
            lines += ["Modest gap — L5 partially distinguishes joke from non-joke (relevance pair). "
                      "This is the most informative number in the run.", ""]
        else:
            lines += ["Strong gap — L5 reliably separates the relevance minimal pair.", ""]
    elif e1_scores or x1_scores:
        lines += ["*E1 or X1 partially complete — gap cannot be computed yet.*", ""]
    else:
        lines += ["*No data yet — E1/X1 has never been tested; this is the most informative number in the run.*", ""]

    # --- Q6: Run-to-run variance ---
    lines += ["## 6. Run-to-run variance", ""]
    unstable = []
    for fid in fixture_ids:
        runs_data = grid[fid]
        if len(runs_data) < _N_RUNS:
            continue
        verdicts = [runs_data[r]["verdict"] for r in range(_N_RUNS)]
        if len(set(verdicts)) > 1:
            unstable.append(f"{fid}: {verdicts}")

    complete_items = [fid for fid in fixture_ids if len(grid[fid]) == _N_RUNS]
    if not complete_items:
        lines += ["*Not enough data to assess variance.*", ""]
    elif not unstable:
        lines += [f"All {len(complete_items)} complete items stable across {_N_RUNS} runs (verdict identical in all runs).", ""]
    else:
        lines += [f"{len(unstable)} item(s) with unstable verdict:", ""]
        for item in unstable:
            lines += [f"- {item}", ""]
        lines += ["Note: temperature=0 does not guarantee determinism with Gemini schema-constrained output.", ""]

    # --- Q7: Failure accounting ---
    lines += ["## 7. Failure accounting", ""]
    all_rows = [grid[fid][r] for fid in fixture_ids for r in range(_N_RUNS) if r in grid[fid]]
    n_total = len(all_rows)
    n_5xx = sum(1 for row in all_rows if row["retries"] > 0)
    n_fallback = sum(1 for row in all_rows if row["fallback_used"])
    insufficient = [row for row in all_rows if row["verdict"] == "INSUFFICIENT_CONTEXT"]
    n_insufficient = len(insufficient)
    # N1 is always INSUFFICIENT_CONTEXT by design (anchoring pre-check, no LLM call)
    n_insufficient_by_design = sum(1 for row in insufficient if row["item_id"] == "N1")
    n_insufficient_schema = n_insufficient - n_insufficient_by_design

    if n_total == 0:
        lines += ["*No data yet.*", ""]
    else:
        lines += [
            f"- Completed rows: **{n_total}** / {_N_RUNS * len(fixture_ids)}",
            f"- Rows with 5xx retries: **{n_5xx}** ({100*n_5xx//n_total}%)",
            f"- Rows using fallback model: **{n_fallback}** ({100*n_fallback//n_total}%)",
            f"- INSUFFICIENT_CONTEXT total: **{n_insufficient}**",
            f"  - By design (N1 anchoring pre-check, no LLM call): **{n_insufficient_by_design}**",
            f"  - Schema/parse failure (LLM called but response unparseable): **{n_insufficient_schema}**",
            "",
        ]
        if n_insufficient_schema > 0:
            schema_items = [row["item_id"] for row in insufficient if row["item_id"] != "N1"]
            lines += [f"  Items with unexpected INSUFFICIENT_CONTEXT: {schema_items}", ""]

    # --- Q7b: Thinking-token distribution & truncation check ---
    lines += ["## 7b. Thinking tokens & truncation (proves the cap held)", ""]
    thoughts = [
        row["thoughts_token_count"]
        for row in all_rows
        if row.get("thoughts_token_count") is not None
    ]
    finish_counts: dict[str, int] = {}
    for row in all_rows:
        fr = row.get("finish_reason") or "(none)"
        finish_counts[fr] = finish_counts.get(fr, 0) + 1
    n_truncated = sum(
        1 for row in all_rows
        if "MAX_TOKENS" in (row.get("finish_reason") or "")
    )

    if not all_rows:
        lines += ["*No data yet.*", ""]
    else:
        lines += [f"- finish_reason counts: {finish_counts}", ""]
        if thoughts:
            lines += [
                f"- thoughts_token_count over {len(thoughts)} model calls: "
                f"min {min(thoughts)}, max {max(thoughts)}, "
                f"mean {sum(thoughts)/len(thoughts):.0f}",
                f"- Configured cap `L5_MAX_OUTPUT_TOKENS` = "
                f"{DEFAULT_SETTINGS.L5_MAX_OUTPUT_TOKENS}",
                "",
            ]
            if max(thoughts) >= DEFAULT_SETTINGS.L5_MAX_OUTPUT_TOKENS:
                lines += ["**WARNING: max thinking tokens met or exceeded the cap — "
                          "raise `L5_MAX_OUTPUT_TOKENS`.**", ""]
            else:
                headroom = DEFAULT_SETTINGS.L5_MAX_OUTPUT_TOKENS - max(thoughts)
                lines += [f"Cap held: {headroom} tokens of headroom above the worst "
                          "observed thinking cost.", ""]
        else:
            lines += ["*No thinking-token data recorded (all rows pre-date the fix "
                      "or were short-circuited).*", ""]
        if n_truncated:
            lines += [f"**{n_truncated} TRUNCATED_OUTPUT row(s) — output was cut off "
                      "mid-JSON. These are truncations, not model verdicts.**", ""]

    # --- Q8: Recommendation ---
    lines += ["## 8. Recommendation", ""]
    if not all_rows:
        lines += ["*Pending data.*", ""]
    else:
        # Assess based on S1/S2 and E1/X1 separation
        rec_lines = []
        if s1_scores and s2_scores:
            gap_s = s1_mean - s2_mean
            if gap_s < 0.1:
                rec_lines.append("S1/S2 gap is near-zero — the polarity feature is not separating the core minimal pair. "
                                 "Replace the weighted score with a polarity-only rule, or redesign the QA prompt.")
            elif gap_s < 0.3:
                rec_lines.append("S1/S2 gap is modest. Keep current weights but investigate whether "
                                 "answer_relevance adds signal beyond polarity.")
            else:
                rec_lines.append("S1/S2 separation is strong. Current QA weights appear functional.")

        if e1_scores and x1_scores:
            gap_r = e1_mean - x1_mean
            if gap_r < 0.1:
                rec_lines.append("E1/X1 gap is near-zero — L5 does not distinguish a genuine joke from a "
                                 "non-joke answer to the same question. This is the critical failure mode. "
                                 "The answer_relevance and causal features need redesign.")
            elif gap_r < 0.3:
                rec_lines.append("E1/X1 gap is moderate. L5 partially discriminates joke vs non-joke answers. "
                                 "Consider upweighting answer_relevance.")
            else:
                rec_lines.append("E1/X1 separation is strong. Relevance features are working.")

        if unstable:
            rec_lines.append(f"Unstable items ({[i.split(':')[0] for i in unstable]}) suggest temperature=0 "
                             "is insufficient for determinism; consider majority-vote over 3 calls.")

        if not rec_lines:
            rec_lines.append("Insufficient data for a recommendation.")

        for r in rec_lines:
            lines += [r, ""]

        lines += [
            "**RECOMMEND ONLY — no weights, thresholds, or prompts have been changed in this report.**",
            "",
        ]

    _OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--resume", action="store_true", default=True,
                       help="Skip already-completed pairs (default)")
    group.add_argument("--fresh", action="store_true", default=False,
                       help="Delete JSONL and start from scratch")
    parser.add_argument("--probe", action="store_true",
                        help="Make one test call and exit")
    args = parser.parse_args()

    if args.probe:
        probe()
        return

    run(fresh=args.fresh)


if __name__ == "__main__":
    main()
