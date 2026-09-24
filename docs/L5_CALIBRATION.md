# L5 Calibration Report

Generated: 2026-09-24 20:52 UTC  
Backend: `gemini`  
Primary model: `gemini-3.6-flash`  
Fallback chain: `['gemini-3.8-flash']`  
Target runs: 5  
Threshold: 0.6  

## 1. Full result table

| ID | Genre | Expected | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Stable |
|---|---|---|---|---|---|---|---|---|
| S1 | QA RIDDLE | RESOLUTION_PASS | OK PASS 0.677 | OK PASS 0.632 | OK PASS 0.625 | !! FAIL 0.580 | OK PASS 0.657 | No |
| S2 | QA RIDDLE | RESOLUTION_FAIL | !! PASS 0.775 | OK FAIL 0.590 | !! PASS 0.797 | OK FAIL 0.590 | !! PASS 0.863 | No |
| E1 | QA RIDDLE | RESOLUTION_PASS | !! FAIL 0.507 | !! FAIL 0.510 | !! FAIL 0.515 | !! FAIL 0.555 | !! FAIL 0.512 | Yes |
| X1 | QA RIDDLE | RESOLUTION_FAIL | OK FAIL 0.320 | OK FAIL 0.417 | OK FAIL 0.400 | OK FAIL 0.370 | OK FAIL 0.270 | Yes |
| A1 | DEFINITIONAL ONELINER | RESOLUTION_PASS | OK PASS 0.935 | OK PASS 0.935 | OK PASS 0.935 | OK PASS 0.935 | OK PASS 0.935 | Yes |
| D1 | DIALOGUE MISUNDERSTANDING | RESOLUTION_PASS | OK PASS 0.927 | OK PASS 0.920 | OK PASS 0.907 | OK PASS 0.858 | OK PASS 0.868 | Yes |
| P1 | QA RIDDLE | RESOLUTION_PASS | !! FAIL 0.595 | OK PASS 0.603 | !! FAIL 0.593 | !! FAIL 0.588 | !! FAIL 0.547 | No |
| P2 | DEFINITIONAL ONELINER | RESOLUTION_FAIL | !! PASS 0.865 | !! PASS 0.900 | !! PASS 0.915 | !! PASS 0.930 | !! PASS 0.880 | Yes |
| P3 | DIALOGUE MISUNDERSTANDING | RESOLUTION_PASS | OK PASS 0.917 | OK PASS 0.897 | OK PASS 0.897 | OK PASS 0.897 | OK PASS 0.917 | Yes |
| N1 | DECLARATIVE | INSUFFICIENT_CONTEXT | OK INSU None | OK INSU None | OK INSU None | OK INSU None | OK INSU None | Yes |

## Per-item subscores

### S1 — Why don't skeletons fight? Because they have no guts.

- **Genre:** QA_RIDDLE
- **Expected:** `RESOLUTION_PASS`
- **Ambiguous term:** `guts`

| Run | Verdict | Score | polarity_or_direction | answer_relevance | causal | agent | tense_aspect | Model | Retries |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `RESOLUTION_PASS` | 0.6775 | 0.30 | 1.00 | 0.95 | 1.00 | 1.00 | gemini-3.6-flash | 0 |
| 2 | `RESOLUTION_PASS` | 0.6325 | 0.20 | 1.00 | 0.95 | 1.00 | 1.00 | gemini-3.6-flash | 0 |
| 3 | `RESOLUTION_PASS` | 0.6250 | 0.20 | 1.00 | 0.90 | 1.00 | 1.00 | gemini-3.6-flash | 0 |
| 4 | `RESOLUTION_FAIL` | 0.5800 | 0.10 | 1.00 | 0.90 | 1.00 | 1.00 | gemini-3.6-flash | 0 |
| 5 | `RESOLUTION_PASS` | 0.6575 | 0.30 | 0.95 | 0.90 | 1.00 | 1.00 | gemini-3.6-flash | 0 |

### S2 — Why do skeletons fight? Because they have no guts.

- **Genre:** QA_RIDDLE
- **Expected:** `RESOLUTION_FAIL`
- **Ambiguous term:** `guts`

| Run | Verdict | Score | polarity_or_direction | answer_relevance | causal | agent | tense_aspect | Model | Retries |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `RESOLUTION_PASS` | 0.7750 | 0.75 | 0.85 | 0.50 | 1.00 | 1.00 | gemini-3.6-flash | 0 |
| 2 | `RESOLUTION_FAIL` | 0.5900 | 0.30 | 0.80 | 0.70 | 1.00 | 1.00 | gemini-3.6-flash | 0 |
| 3 | `RESOLUTION_PASS` | 0.7975 | 0.70 | 0.85 | 0.80 | 1.00 | 1.00 | gemini-3.6-flash | 0 |
| 4 | `RESOLUTION_FAIL` | 0.5900 | 0.40 | 0.80 | 0.40 | 1.00 | 1.00 | gemini-3.6-flash | 0 |
| 5 | `RESOLUTION_PASS` | 0.8625 | 0.80 | 0.90 | 0.85 | 1.00 | 1.00 | gemini-3.6-flash | 0 |

### E1 — Why do elephants have a trunk? Because they don't have pockets to put 

- **Genre:** QA_RIDDLE
- **Expected:** `RESOLUTION_PASS`
- **Ambiguous term:** `trunk`

| Run | Verdict | Score | polarity_or_direction | answer_relevance | causal | agent | tense_aspect | Model | Retries |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `RESOLUTION_FAIL` | 0.5075 | 0.10 | 0.85 | 0.70 | 0.95 | 1.00 | gemini-3.6-flash | 0 |
| 2 | `RESOLUTION_FAIL` | 0.5100 | 0.10 | 0.85 | 0.75 | 0.90 | 1.00 | gemini-3.6-flash | 0 |
| 3 | `RESOLUTION_FAIL` | 0.5150 | 0.10 | 0.85 | 0.75 | 0.95 | 1.00 | gemini-3.6-flash | 0 |
| 4 | `RESOLUTION_FAIL` | 0.5550 | 0.10 | 0.95 | 0.85 | 0.95 | 1.00 | gemini-3.6-flash | 0 |
| 5 | `RESOLUTION_FAIL` | 0.5125 | 0.10 | 0.85 | 0.75 | 0.95 | 0.95 | gemini-3.6-flash | 0 |

### X1 — Why do elephants have a trunk? Because the car's trunk was already ful

- **Genre:** QA_RIDDLE
- **Expected:** `RESOLUTION_FAIL`
- **Ambiguous term:** `trunk`

| Run | Verdict | Score | polarity_or_direction | answer_relevance | causal | agent | tense_aspect | Model | Retries |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `RESOLUTION_FAIL` | 0.3200 | 0.00 | 0.70 | 0.50 | 0.30 | 0.80 | gemini-3.6-flash | 0 |
| 2 | `RESOLUTION_FAIL` | 0.4175 | 0.10 | 0.80 | 0.60 | 0.40 | 0.85 | gemini-3.6-flash | 0 |
| 3 | `RESOLUTION_FAIL` | 0.4000 | 0.10 | 0.70 | 0.60 | 0.50 | 0.80 | gemini-3.6-flash | 0 |
| 4 | `RESOLUTION_FAIL` | 0.3700 | 0.10 | 0.70 | 0.40 | 0.50 | 0.80 | gemini-3.6-flash | 0 |
| 5 | `RESOLUTION_FAIL` | 0.2700 | 0.00 | 0.60 | 0.40 | 0.20 | 0.80 | gemini-3.6-flash | 0 |

### A1 — Autobiography: when your car starts telling you about its life.

- **Genre:** DEFINITIONAL_ONELINER
- **Expected:** `RESOLUTION_PASS`
- **Ambiguous term:** `autobiography`

| Run | Verdict | Score | setup_invites_literal | punchline_exploits_split | contrast_strength | Model | Retries |
|---|---|---|---|---|---|---|---|
| 1 | `RESOLUTION_PASS` | 0.9350 | 0.95 | 0.95 | 0.90 | gemini-3.6-flash | 0 |
| 2 | `RESOLUTION_PASS` | 0.9350 | 0.95 | 0.95 | 0.90 | gemini-3.6-flash | 0 |
| 3 | `RESOLUTION_PASS` | 0.9350 | 0.95 | 0.95 | 0.90 | gemini-3.6-flash | 0 |
| 4 | `RESOLUTION_PASS` | 0.9350 | 0.95 | 0.95 | 0.90 | gemini-3.6-flash | 0 |
| 5 | `RESOLUTION_PASS` | 0.9350 | 0.95 | 0.95 | 0.90 | gemini-3.6-flash | 0 |

### D1 — Danny: You look awful, Gerry. What's wrong? Gerry: I've got a bad case

- **Genre:** DIALOGUE_MISUNDERSTANDING
- **Expected:** `RESOLUTION_PASS`
- **Ambiguous term:** `shingles`

| Run | Verdict | Score | misunderstanding_plausible | contrast_clear | speaker_intention_clear | Model | Retries |
|---|---|---|---|---|---|---|---|
| 1 | `RESOLUTION_PASS` | 0.9275 | 0.85 | 1.00 | 0.95 | gemini-3.6-flash | 0 |
| 2 | `RESOLUTION_PASS` | 0.9200 | 0.80 | 1.00 | 1.00 | gemini-3.6-flash | 0 |
| 3 | `RESOLUTION_PASS` | 0.9075 | 0.80 | 1.00 | 0.95 | gemini-3.6-flash | 0 |
| 4 | `RESOLUTION_PASS` | 0.8575 | 0.75 | 0.95 | 0.90 | gemini-3.6-flash | 0 |
| 5 | `RESOLUTION_PASS` | 0.8675 | 0.70 | 1.00 | 0.95 | gemini-3.6-flash | 0 |

### P1 — Why do cows wear bells? Because their horns don't work.

- **Genre:** QA_RIDDLE
- **Expected:** `RESOLUTION_PASS`
- **Ambiguous term:** `horns`

| Run | Verdict | Score | polarity_or_direction | answer_relevance | causal | agent | tense_aspect | Model | Retries |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `RESOLUTION_FAIL` | 0.5950 | 0.20 | 0.95 | 0.85 | 0.90 | 1.00 | gemini-3.6-flash | 0 |
| 2 | `RESOLUTION_PASS` | 0.6025 | 0.20 | 0.95 | 0.90 | 0.90 | 1.00 | gemini-3.6-flash | 0 |
| 3 | `RESOLUTION_FAIL` | 0.5925 | 0.20 | 0.95 | 0.85 | 0.90 | 0.95 | gemini-3.6-flash | 0 |
| 4 | `RESOLUTION_FAIL` | 0.5875 | 0.20 | 0.90 | 0.85 | 0.95 | 1.00 | gemini-3.6-flash | 0 |
| 5 | `RESOLUTION_FAIL` | 0.5475 | 0.10 | 0.95 | 0.85 | 0.90 | 0.95 | gemini-3.6-flash | 0 |

### P2 — Explain: to make the plain exit.

- **Genre:** DEFINITIONAL_ONELINER
- **Expected:** `RESOLUTION_FAIL`
- **Ambiguous term:** `explain`

| Run | Verdict | Score | setup_invites_literal | punchline_exploits_split | contrast_strength | Model | Retries |
|---|---|---|---|---|---|---|---|
| 1 | `RESOLUTION_PASS` | 0.8650 | 0.85 | 0.85 | 0.90 | gemini-3.6-flash | 0 |
| 2 | `RESOLUTION_PASS` | 0.9000 | 0.85 | 0.90 | 0.95 | gemini-3.6-flash | 0 |
| 3 | `RESOLUTION_PASS` | 0.9150 | 0.90 | 0.90 | 0.95 | gemini-3.6-flash | 0 |
| 4 | `RESOLUTION_PASS` | 0.9300 | 0.95 | 0.90 | 0.95 | gemini-3.6-flash | 0 |
| 5 | `RESOLUTION_PASS` | 0.8800 | 0.90 | 0.85 | 0.90 | gemini-3.6-flash | 0 |

### P3 — Patient: Doctor, I keep thinking I'm a pair of curtains. Doctor: Pull 

- **Genre:** DIALOGUE_MISUNDERSTANDING
- **Expected:** `RESOLUTION_PASS`
- **Ambiguous term:** `pull yourself together`

| Run | Verdict | Score | misunderstanding_plausible | contrast_clear | speaker_intention_clear | Model | Retries |
|---|---|---|---|---|---|---|---|
| 1 | `RESOLUTION_PASS` | 0.9175 | 0.90 | 0.95 | 0.90 | gemini-3.6-flash | 0 |
| 2 | `RESOLUTION_PASS` | 0.8975 | 0.85 | 0.95 | 0.90 | gemini-3.6-flash | 0 |
| 3 | `RESOLUTION_PASS` | 0.8975 | 0.85 | 0.95 | 0.90 | gemini-3.6-flash | 0 |
| 4 | `RESOLUTION_PASS` | 0.8975 | 0.85 | 0.95 | 0.90 | gemini-3.6-flash | 0 |
| 5 | `RESOLUTION_PASS` | 0.9175 | 0.90 | 0.95 | 0.90 | gemini-3.6-flash | 0 |

### N1 — The bank was steep.

- **Genre:** DECLARATIVE
- **Expected:** `INSUFFICIENT_CONTEXT`
- **Ambiguous term:** `bank`

| Run | Verdict | Score | Model |
|---|---|---|---|
| 1 | `INSUFFICIENT_CONTEXT` | None |  |
| 2 | `INSUFFICIENT_CONTEXT` | None |  |
| 3 | `INSUFFICIENT_CONTEXT` | None |  |
| 4 | `INSUFFICIENT_CONTEXT` | None |  |
| 5 | `INSUFFICIENT_CONTEXT` | None |  |

## 2. polarity_or_direction: binary or graded?

Observed `polarity_or_direction` values across 25 QA/applicable calls:
- Near-binary (< 0.1 or > 0.9): **2** (8%)
- Graded (0.1–0.9): **23**

Min: 0.000, Max: 0.800, Mean: 0.230

**Verdict: GRADED** — some values fall between 0.1 and 0.9.

## 3. Does polarity alone determine the verdict?

With weight `polarity_or_direction = 0.45` and threshold `0.6`:

- If `polarity = 0.0`: maximum score from other four features = 0.55 < 0.60 → **always FAIL** regardless of others.
- If `polarity = 1.0`: score ≥ 0.45. Needs other features ≥ 0.15 for PASS at threshold 0.60.
  - Threshold ≤ 0.45 would make polarity=1 a guaranteed PASS.
  - Current threshold 0.60 is **not inert** — other features contribute 0.15 to tip a borderline case.

From the data: no case where polarity≈1.0 led to RESOLUTION_FAIL. In practice polarity dominates, but the threshold is not mathematically inert.

## 4. S1 vs S2 separation (polarity minimal pair)

- S1 (PASS expected): scores ['0.677', '0.632', '0.625', '0.580', '0.657'], mean = **0.635**
- S2 (FAIL expected): scores ['0.775', '0.590', '0.797', '0.590', '0.863'], mean = **0.723**
- Gap (S1 − S2): **-0.089**

**Warning**: gap < 0.10 — L5 is barely separating the polarity minimal pair.

## 5. E1 vs X1 separation (relevance minimal pair)

- E1 (PASS expected — trunk/pockets joke): scores ['0.507', '0.510', '0.515', '0.555', '0.512'], mean = **0.520**
- X1 (FAIL expected — trunk/grey mammals non-joke): scores ['0.320', '0.417', '0.400', '0.370', '0.270'], mean = **0.356**
- Gap (E1 − X1): **0.165**

Modest gap — L5 partially distinguishes joke from non-joke (relevance pair). This is the most informative number in the run.

## 6. Run-to-run variance

3 item(s) with unstable verdict:

- S1: ['RESOLUTION_PASS', 'RESOLUTION_PASS', 'RESOLUTION_PASS', 'RESOLUTION_FAIL', 'RESOLUTION_PASS']

- S2: ['RESOLUTION_PASS', 'RESOLUTION_FAIL', 'RESOLUTION_PASS', 'RESOLUTION_FAIL', 'RESOLUTION_PASS']

- P1: ['RESOLUTION_FAIL', 'RESOLUTION_PASS', 'RESOLUTION_FAIL', 'RESOLUTION_FAIL', 'RESOLUTION_FAIL']

Note: temperature=0 does not guarantee determinism with Gemini schema-constrained output.

## 7. Failure accounting

- Completed rows: **50** / 50
- Rows with 5xx retries: **0** (0%)
- Rows using fallback model: **0** (0%)
- INSUFFICIENT_CONTEXT total: **5**
  - By design (N1 anchoring pre-check, no LLM call): **5**
  - Schema/parse failure (LLM called but response unparseable): **0**

## 7b. Thinking tokens & truncation (proves the cap held)

- finish_reason counts: {'FinishReason.STOP': 45, '(none)': 5}

- thoughts_token_count over 45 model calls: min 545, max 2066, mean 1019
- Configured cap `L5_MAX_OUTPUT_TOKENS` = 8192

Cap held: 6126 tokens of headroom above the worst observed thinking cost.

## 8. Recommendation

S1/S2 gap is near-zero — the polarity feature is not separating the core minimal pair. Replace the weighted score with a polarity-only rule, or redesign the QA prompt.

E1/X1 gap is moderate. L5 partially discriminates joke vs non-joke answers. Consider upweighting answer_relevance.

Unstable items (['S1', 'S2', 'P1']) suggest temperature=0 is insufficient for determinism; consider majority-vote over 3 calls.

**RECOMMEND ONLY — no weights, thresholds, or prompts have been changed in this report.**
