# DoubleTake — Architecture

## 1. L0-pre / L0-post split

### The problem with a monolithic L0

The README describes L0 as a single "scope declaration" stage that runs first and produces labels such as `OUT_OF_SCOPE_HOMOPHONE`, `HOMOGRAPH`, and `COMPOUND_SPLIT`.  These labels require knowing whether the text contains a homophone, a homograph, or neither — evidence that is only produced by L2 (sense retrieval), L3 (candidate ranking), and L4 (sense anchoring).  A single L0 running before those layers cannot make those determinations without duplicating or pre-empting their logic.

### The solution: two responsibilities, two functions

**L0-pre** — runs first in the pipeline:
- Validates and normalises the raw input text (unicode NFC, whitespace collapse).
- Rejects inputs that are empty, too short, too long, or whose non-ASCII ratio exceeds the configured threshold (a proxy for non-English text or encoding garbage).
- Makes **no judgement** about the text's content, vocabulary, or lexical mechanism.
- Lives in `src/doubletake/l0_scope.py` as `preprocess_input(text, settings) -> str`.

**L0-post** — runs last in the pipeline (after L8):
- A **pure function**: `assign_scope_label(evidence: LayerEvidence) -> ScopeLabel`.
- Maps the `LayerEvidence` accumulated by L2–L4 to exactly one `ScopeLabel`.
- Deterministic, zero I/O, fully unit-testable in isolation.
- Lives in the same file as `assign_scope_label`.

This split keeps each piece fully testable, avoids tangled dependencies, and makes the data flow explicit: the scope verdict is a *summary* of what the analysis found, not a gate that precedes it.

---

## 2. L0-post decision table

The decision table is evaluated top-to-bottom; the first matching row wins.

| Priority | Condition | ScopeLabel |
|---|---|---|
| 1 | `is_homophone AND NOT has_homograph` | `OUT_OF_SCOPE_HOMOPHONE` |
| 2 | `has_homograph` | `HOMOGRAPH` |
| 3 | `has_compound_split` | `COMPOUND_SPLIT` |
| 4 | `is_nonlexical_joke` | `OUT_OF_SCOPE_NONLEXICAL_JOKE` |
| 5 | *(none of the above)* | `NO_SCOPE_MECHANISM` |

**Row 1 guard** — `NOT has_homograph`: a word such as *lead* (metal / to guide) is simultaneously a heterographic homophone and a homograph.  The guard ensures genuine homographs are not incorrectly excluded.

**Row 2 before Row 3** — homographic ambiguity is the primary mechanism; compound splits are a secondary variant.  If both are flagged (unlikely but possible), `HOMOGRAPH` takes precedence.

**Row 4 after positive matches** — a confirmed lexical mechanism takes precedence over a nonlexical flag.

**Row 5 as safe default** — incomplete evidence (all fields `False`, which is the initial state before L2–L4 run) yields `NO_SCOPE_MECHANISM` rather than an error.

---

## 3. Layer-registry contract

Layers are registered as named callables:

```python
register_layer("L1", run_l1)
```

Each callable must satisfy:

```
(record: AnalysisRecord, settings: Settings) -> AnalysisRecord
```

The runner calls layers in registration order.  For each item:
- If a layer succeeds it appends a `LayerTrace(status="OK", ...)` and returns the updated record.
- If a layer raises any exception the runner catches it, appends a `LayerTrace(status="ERROR", reason=...)`, and continues to the next layer.  A failed layer never crashes the run.

Currently registered layers (in order): `L0-pre`, `L0-post`.

To add a new layer, implement the function in `layers.py` (or wherever appropriate) and call `register_layer` at module load time in `runner.py`.  No other changes are required.

---

## 4. Deliberate deviations from README

### Deviation 1 — target-age familiarity removed from L3 candidate scoring

**README says:** *"A useful candidate score combines … target-age familiarity …"*

**Implementation:** target-age familiarity is excluded from `L3_TOP_K` candidate ranking.  The same scoring formula is applied regardless of the target ages supplied with the item.

**Reason:** including age-of-acquisition data in the candidate score would make the ranked candidate list age-dependent.  The same text could therefore surface a *different* pun word when evaluated for age 6 versus age 12, making the detection result inconsistent across a single item.  Per-age sensitivity belongs in L7 (comprehension assessment), which receives the already-selected candidates from L3 and evaluates their accessibility for each target age independently.

The deviation is recorded in `config.py` as an inline comment adjacent to `L3_TOP_K`.

---

## 5. L5 schema: discriminated union (Decision 1)

### Rejected option: flat model

A single `L5Result` with all possible subscore fields marked `Optional` was rejected.  The flat model leaves approximately two-thirds of its fields as `None` on any given item (a QA item has no definitional subscores; a definitional item has no QA subscores).  This makes it impossible to answer the question "was this field checked and found absent, or was it simply never evaluated?"  Downstream layers and calibration code cannot distinguish the two states from the model alone; they would require out-of-band knowledge of which branch ran.

### Chosen option: discriminated union

`L5Result` is `Annotated[Union[L5QAResult, L5DefinitionalResult, L5DialogueResult], Field(discriminator="genre")]`.

Each branch carries exactly the fields relevant to that genre:

| Branch | `genre` discriminant | Subscore keys |
|---|---|---|
| `L5QAResult` | `QA_RIDDLE` | `polarity_or_direction`, `answer_relevance`, `causal`, `agent`, `tense_aspect` |
| `L5DefinitionalResult` | `DEFINITIONAL_ONELINER` | `setup_invites_literal`, `punchline_exploits_split`, `contrast_strength` |
| `L5DialogueResult` | `DIALOGUE_MISUNDERSTANDING`, `DECLARATIVE` | `misunderstanding_plausible`, `contrast_clear`, `speaker_intention_clear` |

Every field in the instantiated branch is present and non-null.  Absent fields are structurally impossible: `extra="forbid"` blocks extra keys, and no branch defines the other branches' fields.  The discriminant `genre` is the same `Genre` enum used by L1, so no new primitive is introduced.

**Cost of the rejected option:** any code that reads `resolution_score` or a subscore must first test for `None`, and a bug that sets the wrong branch's field to `None` is silent at the model level.

---

## 6. L5 definitional branch: same-span anchor acceptance (Decision 2)

### Anchor-quote definition

`sense_a_anchor_quote` and `sense_b_anchor_quote` in `L4Result` are **context spans** — exact substrings of the item text that activate each sense of the ambiguous term, not the ambiguous term itself.

- **Correct:** for *"Why do cows wear bells? Because their horns don't work,"* the animal-horn sense is anchored by `"cows"` (establishing livestock context) and the vehicle-horn sense by `"don't work"` (establishing device-failure context).
- **Wrong:** using `"horns"` for both — that is the ambiguous term, not a context span.

When both senses of a resegmentation (compound-split) item anchor to the same surface token — the compound word itself — `sense_a_anchor_quote == sense_b_anchor_quote` is correct and expected.  Every other case of identical anchor quotes indicates that L4 returned the ambiguous term in both fields instead of identifying distinct context spans.  L5 detects this and short-circuits to `INSUFFICIENT_CONTEXT` with a `WARNING` log rather than making an LLM call with ambiguous anchor evidence.

### The problem

For compound-split jokes (e.g. *Autobiography: when your car starts telling you about its life*), both senses anchor to the same surface token — the compound word itself.  L4 therefore sets `sense_a_anchor_quote == sense_b_anchor_quote`.  A naïve L5 implementation that rejects same-span anchors as "unresolved" would fail every compound-split item.

### The rule

The `L5DefinitionalResult` branch accepts same-span anchors **when and only when** `L4Result.anchor_relation == AnchorRelation.RESEGMENTATION`.  The prompts for `l5_definitional.md` are written with this in mind: they ask the LLM to evaluate the semantic contrast between the two readings of the compound word, not whether the quotes appear at different offsets.

### Why not change L4?

L4 correctly reports `sense_a_anchor_quote == sense_b_anchor_quote` for resegmentation items — this is an accurate description of the anchor structure.  Modifying L4 to produce a synthetic distinction would falsify the anchoring record.  The right fix is in L5, which must interpret same-span anchors differently depending on `anchor_relation`.

---

---

## 7. L5 backend choice (Decision 3)

### Why Gemini, not Anthropic, is the default

`L5_BACKEND = "gemini"` and `L5_MODEL_GEMINI = "gemini-3.6-flash"` in `Settings`.

**Schema-constrained JSON output.** Gemini's `response_schema` parameter (via `GenerateContentConfig`) enforces the exact JSON structure at the API level.  The LLM cannot omit a subscore field or add unexpected keys; the API returns an error instead.  The Anthropic path relies on prompt engineering and post-hoc field validation with a retry loop — schema enforcement eliminates an entire class of retry-needed failures.

**Temperature=0 is supported.** `GenerateContentConfig(temperature=0.0)` is accepted.  Anthropic claude-4.7+ models reject non-default temperature/top_p/top_k with a 400 error, so the Anthropic path must absorb run-to-run score variance as a measurement cost.  Temperature=0 makes Gemini runs deterministic for the same input, which matters for calibration stability.

**Smoke-test polarity on S1/S2 (Decision 3 validation).** S1 ("Why don't skeletons fight? Because they have no guts.") should score `polarity_or_direction ≈ 1.0` (question premise and punchline align as expected). S2 ("Why do skeletons fight? Because they have no guts.") should score `polarity_or_direction ≈ 0.0` (punchline contradicts premise).  A passing model gives S1 ≥ 0.6 (RESOLUTION_PASS) and S2 < 0.6 (RESOLUTION_FAIL).  These are items `S1`/`S2` in `tests/fixtures/l5_anchors.jsonl`.

**Cost.** Gemini 2.5 Flash / 3.6 Flash is significantly cheaper per token than Claude Sonnet for the same structured-output task.

**Data-use warning.** Free-tier Gemini API requests may be used to improve Google's models.  For production or sensitive content, use a paid tier (`x-goog-user-project` billing, which opts out of training use).  This is a runtime concern, not a code concern; no change to `l5_resolution.py` is needed.

### Switching backends

Change `L5_BACKEND = "anthropic"` in `Settings` (or override in tests).  The `_complete_json` dispatcher routes to `_call_llm` (Anthropic) or `_call_gemini` (Gemini).  All offline tests mock both `client.messages.create` and `client.models.generate_content` so they pass regardless of which backend is active.

---

### Deviation 2 — L5_RESOLUTION_THRESHOLDS added, per genre (not named in README)

**README says:** *the weighted resolution score formula, but no pass/fail threshold.*

**Implementation:** `L5_RESOLUTION_THRESHOLDS` in `Settings` maps each genre to the minimum weighted score required for a `RESOLUTION_PASS` verdict:

| Genre | Threshold | Basis |
|---|---|---|
| QA_RIDDLE | 0.46 | 5-run calibration: X1 (negative) max 0.417, E1 (positive) min 0.507. Set from per-run ranges, not means — verdicts are per run. |
| DEFINITIONAL_ONELINER | 0.60 | Positives only (A1 0.935; P2 0.865–0.930, relabelled PASS 2026-09-24). No validated negative. |
| DIALOGUE_MISUNDERSTANDING | 0.60 | Positives only (D1, P3). No validated negative. |
| DECLARATIVE | 0.60 | **UNVALIDATED** — no declarative item has been scored live. Placeholder until declarative jokes/non-jokes from the annotated corpus are calibrated. |

No QA threshold separates S1 (positive, 0.58–0.68) from S2 (negative, 0.59–0.86). That inversion comes from how the L4 fixtures label the senses, not from the cut-off.

**Reason:** without a named threshold, every implementation would embed the cut-off as a magic number inside L5 logic, making it invisible and non-tunable.  Per-genre because each branch has a different subscore set, so scores land on different scales (QA 0.27–0.86 vs definitional/dialogue 0.86–0.94 in calibration).

---

## 8. L2 lexical data sources (Decision 4)

**Sources, all deterministic, cached under `data/` (gitignored):**

- **WordNet 3.0** via nltk. It downloads to `data/nltk_data/` the first time it is used. Each sense carries synset id, gloss, POS, `lexname()`.
- **SemCor tag counts** via WordNet `Lemma.count()`. That is WordNet's cntlist, the per-sense tag frequency from the SemCor semantic concordance. The raw SemCor corpus is not downloaded because nothing needs it.
- **Age of acquisition:** Kuperman, V., Stadthagen-Gonzalez, H., & Brysbaert, M. (2012). *Age-of-acquisition ratings for 30,000 English words.* Behavior Research Methods, 44(4), 978–990. Fetched by `scripts/fetch_aoa.py` (sha256-pinned) from the Ghent CRR `AoA_51715_words.zip` (Internet Archive capture, 2022-12-07; the original crr.ugent.be URL is 404). Only the `AoA_Kup` column is used (31,105 rated surface forms). **Not committed** to the repo: every clone runs the fetch script once.

**AoA join fallback chain** (`l2_senses.aoa_lookup`): exact → lowercase → lemmatized → miss. Every `SenseEntry` records which stage matched in `aoa_match`, so a miss reaches L7 as an explicit miss rather than a silent gap. Run `py -3.11 -m doubletake.l2_senses` for the stage-by-stage coverage report.

**Compound splits** (`l2_senses.compound_splits`): two-way splits where both halves are exact WordNet lemma names (autobiography → auto + biography). The part-senses are emitted with `source="wordnet_split:<a>+<b>"`, which lets L3 reach the resegmentation case.
