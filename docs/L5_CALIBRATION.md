# L5 Calibration Report

> **Status: NOT YET RUN — requires `ANTHROPIC_API_KEY`.**
>
> To generate this report, set your API key and run:
> ```
> py -3.11 scripts/run_l5_calibration.py
> ```
> The script runs 5 passes over all 6 fixture items and overwrites this file
> with the actual calibration table.

---

## What this report will contain

Once generated, this document reports:

- Per-item: expected status, observed status across 5 runs, score range (min/mean/max), stability flag
- Score variance across runs (a proxy for model non-determinism; Claude 4.7-and-later models reject non-default temperature/top_p/top_k with a 400 error, so run-to-run variance is measured rather than suppressed)
- Whether each fixture's `expected_l5_status` was confirmed, rejected, or unstable

## Fixture summary

| ID | Genre | Ambiguous term | Expected status | Notes |
|---|---|---|---|---|
| S1 | QA_RIDDLE | guts | RESOLUTION_PASS | Strong polarity flip (organs vs courage) |
| S2 | QA_RIDDLE | horns | RESOLUTION_PASS | Strong polarity flip (animal vs vehicle) |
| E1 | DEFINITIONAL_ONELINER | autobiography | RESOLUTION_PASS | Same-span anchor (resegmentation) — Decision 2 test case |
| A1 | DEFINITIONAL_ONELINER | explain | RESOLUTION_FAIL | Deliberately weak split (`ex + plain`) — low contrast expected |
| D1 | DIALOGUE_MISUNDERSTANDING | pull yourself together | RESOLUTION_PASS | Clear speaker misunderstanding |
| X1 | DECLARATIVE | bank | INSUFFICIENT_CONTEXT | Anchoring FAIL (ONE_SENSE_ONLY) — L5 never calls LLM |

## Decision 2 validation

E1 (`autobiography`) is the critical test for ARCHITECTURE.md Decision 2.  Both sense anchors quote the same token (`autobiography`), which is correct for a resegmentation item.  A calibration run that finds E1 = RESOLUTION_PASS validates that the definitional prompt does not penalise same-span anchors when `anchor_relation == resegmentation`.

## Note on non-determinism

Claude 4.7-and-later models reject non-default temperature/top_p/top_k with a 400 error, so run-to-run variance is measured rather than suppressed.  Five runs are recorded to measure this variance.  A stable item shows the same `resolution_status` in all 5 runs; an unstable item warrants prompt review.
