# L5 Calibration Report

> **STATUS: NO DATA.**
> Run aborted — Gemini free-tier daily quota (RPD, `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit 20) exhausted.
> Zero of 50 item-runs completed. This file is a placeholder; all figures below are INCOMPLETE.
> Next action: `py -3.11 scripts/run_l5_calibration.py --probe` after daily quota resets (midnight Pacific), then `--resume`.

Generated: 2026-09-22 18:26 UTC  
Backend: `gemini`  
Primary model: `gemini-3.6-flash`  
Fallback chain: `['gemini-3.8-flash']`  
Target runs: 5  
Threshold: 0.6  

## 1. Full result table

| ID | Genre | Expected | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Stable |
|---|---|---|---|---|---|---|---|---|
| S1 | QA RIDDLE | RESOLUTION_PASS | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE |
| S2 | QA RIDDLE | RESOLUTION_FAIL | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE |
| E1 | QA RIDDLE | RESOLUTION_PASS | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE |
| X1 | QA RIDDLE | RESOLUTION_FAIL | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE |
| A1 | DEFINITIONAL ONELINER | RESOLUTION_PASS | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE |
| D1 | DIALOGUE MISUNDERSTANDING | RESOLUTION_PASS | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE |
| P1 | QA RIDDLE | RESOLUTION_PASS | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE |
| P2 | DEFINITIONAL ONELINER | RESOLUTION_FAIL | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE |
| P3 | DIALOGUE MISUNDERSTANDING | RESOLUTION_PASS | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE |
| N1 | DECLARATIVE | INSUFFICIENT_CONTEXT | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE | INCOMPLETE |

## Per-item subscores

### S1 — Why don't skeletons fight? Because they have no guts.

- **Genre:** QA_RIDDLE
- **Expected:** `RESOLUTION_PASS`
- **Ambiguous term:** `guts`

*No data yet.*

### S2 — Why do skeletons fight? Because they have no guts.

- **Genre:** QA_RIDDLE
- **Expected:** `RESOLUTION_FAIL`
- **Ambiguous term:** `guts`

*No data yet.*

### E1 — Why do elephants have a trunk? Because they don't have pockets to put 

- **Genre:** QA_RIDDLE
- **Expected:** `RESOLUTION_PASS`
- **Ambiguous term:** `trunk`

*No data yet.*

### X1 — Why do elephants have a trunk? Because they are large grey mammals.

- **Genre:** QA_RIDDLE
- **Expected:** `RESOLUTION_FAIL`
- **Ambiguous term:** `trunk`

*No data yet.*

### A1 — Autobiography: when your car starts telling you about its life.

- **Genre:** DEFINITIONAL_ONELINER
- **Expected:** `RESOLUTION_PASS`
- **Ambiguous term:** `autobiography`

*No data yet.*

### D1 — Gerry: I've got shingles. Danny: Where are they? Gerry: Outside on the

- **Genre:** DIALOGUE_MISUNDERSTANDING
- **Expected:** `RESOLUTION_PASS`
- **Ambiguous term:** `shingles`

*No data yet.*

### P1 — Why do cows wear bells? Because their horns don't work.

- **Genre:** QA_RIDDLE
- **Expected:** `RESOLUTION_PASS`
- **Ambiguous term:** `horns`

*No data yet.*

### P2 — Explain: to make the plain exit.

- **Genre:** DEFINITIONAL_ONELINER
- **Expected:** `RESOLUTION_FAIL`
- **Ambiguous term:** `explain`

*No data yet.*

### P3 — Patient: Doctor, I keep thinking I'm a pair of curtains. Doctor: Pull 

- **Genre:** DIALOGUE_MISUNDERSTANDING
- **Expected:** `RESOLUTION_PASS`
- **Ambiguous term:** `pull yourself together`

*No data yet.*

### N1 — The bank was steep.

- **Genre:** DECLARATIVE
- **Expected:** `INSUFFICIENT_CONTEXT`
- **Ambiguous term:** `bank`

*No data yet.*

## 2. polarity_or_direction: binary or graded?

*No data yet.*

## 3. Does polarity alone determine the verdict?

With weight `polarity_or_direction = 0.45` and threshold `0.6`:

- If `polarity = 0.0`: maximum score from other four features = 0.55 < 0.60 → **always FAIL** regardless of others.
- If `polarity = 1.0`: score ≥ 0.45. Needs other features ≥ 0.15 for PASS at threshold 0.60.
  - Threshold ≤ 0.45 would make polarity=1 a guaranteed PASS.
  - Current threshold 0.60 is **not inert** — other features contribute 0.15 to tip a borderline case.

*No data yet.*

## 4. S1 vs S2 separation (polarity minimal pair)

*No data yet.*

## 5. E1 vs X1 separation (relevance minimal pair)

*No data yet — E1/X1 has never been tested; this is the most informative number in the run.*

## 6. Run-to-run variance

*Not enough data to assess variance.*

## 7. Failure accounting

*No data yet.*

## 8. Recommendation

*Pending data.*
