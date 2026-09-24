# HANDOFF — DoubleTake
Last updated: 2026-09-24 by daren-l5 INSUFFICIENT_CONTEXT root-cause session

---

## Current state (VERIFIED)

All items below were confirmed by commands run in this session.

| Check | Command | Result |
|---|---|---|
| Full test suite | `py -3.11 -m pytest -q` | **130 passed, 0 failed** (120 offline + 10 live) |
| Offline only | `py -3.11 -m pytest -q -m "not live"` | **120 passed, 10 deselected** |
| Coverage (offline) | `py -3.11 -m pytest --cov=doubletake --cov-branch -q -k "not live"` | 76% total — layers.py 0%, runner.py 0% |
| API key | `py -3.11 -c "import os; print(bool(os.environ.get(...)))"` | **NOT SET** |
| L5_CALIBRATION.md | read file | **EXISTS but PLACEHOLDER** — no real run data |
| Runner CLI | `py -3.11 -m doubletake.runner --blind tests/fixtures/sample_blind.jsonl` | **Valid JSONL** — 3 items, 3 trace entries each (L0-pre OK, L5 ERROR, L0-post OK) |
| NotImplementedError stubs | read layers.py | 7 stubs: run_l1, run_l2, run_l3, run_l4, run_l6, run_l7, run_l8 |
| Git state | `git log --oneline -8` | On daren-l5; 7 commits including all fixes from this session |
| pytest-cov installed | install attempt | Was **NOT installed** — installed during this session |

### Per-module coverage (offline suite, branch mode)

| Module | Stmts | Miss | Cover |
|---|---|---|---|
| `__init__.py` | 1 | 0 | 100% |
| `config.py` | 18 | 0 | 100% |
| `corpus.py` | 68 | 4 | 91% |
| `enums.py` | 53 | 0 | 100% |
| `l0_scope.py` | 40 | 1 | 97% |
| `l5_resolution.py` | 80 | 6 | 89% |
| `layers.py` | 26 | 26 | **0%** |
| `runner.py` | 76 | 76 | **0%** |
| `schema.py` | 116 | 1 | 98% |
| **TOTAL** | **478** | **114** | **76%** |

---

## Claimed but unverified

- Prior session summaries exist only in commit messages / no formal HANDOFF.md existed. No prior claims were inherited.

---

## Layer status

| Layer | Status | Tests | Notes |
|---|---|---|---|
| L0-pre | **done** | yes (13 tests in test_l0.py) | 97% cov; `isinstance` guard not tested |
| L0-post | **done** | yes (9 tests in test_l0.py) | Wired; returns NO_SCOPE_MECHANISM until L2–L4 run |
| L1 | **stub** | none | `run_l1` raises NotImplementedError |
| L2 | **stub** | none | `run_l2` raises NotImplementedError |
| L3 | **stub** | none | `run_l3` raises NotImplementedError |
| L4 | **stub** | none | `run_l4` raises NotImplementedError |
| L5 | **done** | yes (120 offline, 10 live; all green) | Gemini backend (default); 5xx retry + model fallback chain; anchor-span short-circuit guard; QA/dialogue branches exercised live (suite green) |
| L6 | **stub** | none | `run_l6` raises NotImplementedError |
| L7 | **stub** | none | `run_l7` raises NotImplementedError |
| L8 | **stub** | none | `run_l8` raises NotImplementedError |

---

## Open issues

### From Step 2 (a–h)

**a. Model string** — PARTIALLY RESOLVED (Gemini backend session)
- `L5_BACKEND = "gemini"` and `L5_MODEL_GEMINI = "gemini-3.6-flash"` added to Settings in config.py
- `_MODEL = "claude-sonnet-4-6"` is the Anthropic fallback (used when `L5_BACKEND = "anthropic"`); this model string is **unverified** — no live Anthropic call has been made this session, so API availability, billing, and correct output format are untested
- Not blocking: `L5_BACKEND = "gemini"` is the default and the only path with a live run pending
- Decision rationale in ARCHITECTURE.md §7

**b. Temperature comment** — RESOLVED (d74e036)
- Replaced SDK-version attribution with correct explanation in docs/L5_CALIBRATION.md and scripts/run_l5_calibration.py
- Correct reason: Claude 4.7-and-later models reject non-default temperature/top_p/top_k with a 400 error

**c. test_enums.py** — CONFIRMED HARDCODED (tautological)
- `tests/test_enums.py:37–90` — all 42 status strings are hardcoded in `_README_STATUS_STRINGS`
- The test verifies that the hardcoded strings appear in enums.py, NOT that README.md matches enums.py
- README drift will not be caught
- Severity: **nice-to-have** to fix (tests pass; no false negatives from enum side; only gap is README drift detection)

**d. L5 retry / pydantic validation logging** — RESOLVED (d26f7ae)
- `_call_llm` now accepts `required_keys`; missing keys log a WARNING and raise ValueError (caught by existing retry loop)
- `resolve_l5` determines weights before the LLM call and passes `required_keys=frozenset(weights)`
- Subscores use `parsed[k]` not `parsed.get(k, 0.0)`; `resolution_score` is `Optional[float]=None` for INSUFFICIENT_CONTEXT
- 5 parametrised regression tests in `tests/test_l5_missing_subscores.py`

**e. Runner exception path test** — NOT FOUND
- `runner.py:170–180` catches any layer exception and appends `LayerTrace(status="ERROR")`
- No test registers a layer that raises and asserts the run continues with the error recorded in `trace`
- `runner.py` has 0% coverage
- Severity: **should-fix** — exception handling is entirely untested

**f. Registry signature test** — NOT FOUND
- No test asserts every stub in `layers.py` satisfies `(record: AnalysisRecord, settings: Settings) -> AnalysisRecord`
- Severity: **nice-to-have**

**g. L0-post branch coverage** — NOT 100%
- `l0_scope.py` is 97% (1 statement missed, 1 branch partial)
- The uncovered branch is `preprocess_input:109–112` — the `isinstance(text, str)` guard; no test passes a non-string
- `assign_scope_label` itself is fully covered (all 5 decision-table rows tested)
- Severity: **nice-to-have**

**h. README L3 / config.py deviation** — RESOLVED
- `config.py:6–9` documents the deviation (target-age familiarity removed from L3 scoring)
- `ARCHITECTURE.md §4 Deviation 1` documents it with rationale
- No action needed

**n. X1 fixture — RESOLVED**
- Original X1 ("...large grey mammals") was an invalid L5 fixture: punchline contained no context for the container sense of "trunk", so sense B could never be anchored — a L4 fail, not an L5 one
- Original X1 moved to `tests/fixtures/l4_anchoring.jsonl` as an L4 anchoring negative (`expected_anchoring_status: ONE_SENSE_ONLY`)
- New X1 in `l5_anchors.jsonl`: "Why do elephants have a trunk? Because the car's trunk was already full." — `sense_a_anchor="elephants"`, `sense_b_anchor="car's trunk"`, both senses distinct and in-text; punchline fails to explain the proboscis → `expected_l5_status: RESOLUTION_FAIL`
- Validation test `test_fixture_anchor_quotes_are_substrings_and_distinct` now passes; suite is 130/130 green

### Additional findings

**i. Live tests don't skip when API key is absent** — RESOLVED, UPDATED
- `tests/conftest.py` updated to check the active backend's key: `GEMINI_API_KEY` when `L5_BACKEND == "gemini"`, else `ANTHROPIC_API_KEY`
- `py -3.11 -m pytest -q` now reports **110 passed, 10 skipped** with no GEMINI_API_KEY

**j. runner.py and layers.py have 0% coverage**
- No integration test exercises the runner's `run()` function or the registered pipeline
- Runner exception handling (`runner.py:170–180`) is completely untested
- Severity: **should-fix**

**k. No source code committed to git** — CORRECTED
- Prior audit ran from the parent folder (`jokes\`), which is not a git repo — the result was misleading
- Actual state: repo exists at `jokes\Joke_identification`; all source is committed on branch `daren-l5` and pushed to origin
- 7 commits as of this session

**l. pytest-cov not in test dependencies**
- `pyproject.toml` `[project.optional-dependencies].test` only lists `pytest>=7`
- `pytest-cov` must be installed manually; not documented anywhere
- Severity: **nice-to-have**

**m. Bare string comparison in _l0_post_layer** — RESOLVED (fe433c7)
- `runner.py:99` now uses `AnchoringStatus.PASS` instead of `"PASS"`

---

## Build order (agreed)

| Step | Layer | Current status | Notes |
|---|---|---|---|
| 1 | L5 | **done** — live calibration pending | Needs API key + `py -3.11 scripts/run_l5_calibration.py` |
| 2 | L2 | **stub** — next to build | WordNet + SemCor + Kuperman AoA retriever |
| 3 | L7 | **stub** | Comprehension, per-age |
| 4 | L1 | **stub** | Surface analysis + genre routing |
| 5 | L3 | **stub** | Candidate ranking (age-free) |
| 6 | L4 | **stub** | Anchoring |
| 7 | L8 | **stub** | Appropriateness |
| 8 | L6 | **stub** — low priority | Leave as L6_SKIPPED unless time allows |
| 9 | L0-post | **done** — wired | Wire full evidence from L2–L4 into LayerEvidence last |

---

## Deliberate deviations from README

| Deviation | Reason | Documented in |
|---|---|---|
| L3 candidate scoring: target-age familiarity removed | Age-dependent scoring would make the same text surface different pun words at different ages; per-age sensitivity belongs in L7 | `config.py:6–9`, `ARCHITECTURE.md §4 Deviation 1` |
| L5_RESOLUTION_THRESHOLD = 0.60 added | README gives the weight formula but no named pass/fail cut-off; declaring it in config.py makes it tunable | `config.py:12–14`, `ARCHITECTURE.md §4 Deviation 2` |
| L0 split into L0-pre + L0-post | Monolithic L0 would need to pre-empt L2–L4 logic; split keeps each piece independently testable | `ARCHITECTURE.md §1–2` |

---

## Next action

**Run the calibration — the cap fix is applied and verified. Owner (Daren) runs it.**

Root cause (all-INSUFFICIENT_CONTEXT run) was `max_output_tokens=512`: Gemini 3.x
counts thinking tokens against it, thinking (487–969 observed) consumed the budget,
JSON truncated mid-emit and was misread as a parse failure. FIXED in commit
`d241418`:

- `L5_MAX_OUTPUT_TOKENS = 8192` (config.py). Verified live: S1 at 8192 → `STOP`,
  thoughts=914, output=62, valid JSON. Three thinking samples (487/969/914) all
  clear 8192 with ~7200 headroom.
- `ResolutionStatus.TRUNCATED_OUTPUT` added. `finish_reason==MAX_TOKENS` now returns
  it distinctly (ERROR-logged with item + thoughts count), never again masquerading
  as a model verdict. Offline test covers it.
- Calibration now records `finish_reason` + `thoughts_token_count` per row and the
  raw file persists the actual `response.text`; report has a thinking-distribution
  section to prove the cap held.

Steps:
1. `py -3.11 scripts/run_l5_calibration.py --probe` — confirm API available.
2. `py -3.11 scripts/run_l5_calibration.py --fresh` — the existing
   `runs/l5_calibration.jsonl` holds 45 stale all-INSUFFICIENT rows from the buggy
   run; use `--fresh` (not `--resume`) so they don't poison the report. **API-gated:
   needs explicit approval per HANDOFF live-call rule.**
3. Review `docs/L5_CALIBRATION.md` — note that the currently-uncommitted version of
   this file is the STALE buggy report (all INSUFFICIENT); the fresh run overwrites it.

The AFC warning printed by the SDK is a RED HERRING: `function_calls=None`,
`automatic_function_calling_history=[]`. Not related to the failure.

After calibration data is collected: proceed to L2 (WordNet + SemCor + Kuperman AoA
retriever) per the agreed build order.

---

## Team workflow

This file has one owner: **Daren**. Other contributors do not edit HANDOFF.md; they note status in their PR description.

---

## Session log

*(append-only — never rewrite old entries)*

### 2026-09-24 — Cap fix + truncation surfacing (daren-l5), commit d241418

Follows the root-cause session below. Applied the production fix and made truncation
a first-class outcome.

- `config.py`: `L5_MAX_OUTPUT_TOKENS = 8192` (was hardcoded 512 in
  `_call_gemini_single`). Rationale in-code: thinking is charged against the cap and
  varies 2x; 8192 clears the worst observed (969) with wide margin. Chose raise-the-cap
  over `ThinkingConfig` deliberately — thinking is likely what separates the polarity
  minimal pair; not cutting it to save tokens we don't pay for.
- `enums.py`: added `ResolutionStatus.TRUNCATED_OUTPUT`. (test_enums.py unaffected — it
  only checks README strings ⊆ enum values; no consumer branches on the status, only
  layers.py interpolates it into a trace string.)
- `l5_resolution.py`:
  - `_call_gemini_single` now takes `max_output_tokens`; detects
    `finish_reason==MAX_TOKENS` right after the call and returns `truncated=True`
    WITHOUT a parse retry (retrying just truncates again).
  - Introduced `_L5Call` NamedTuple (parsed, model_used, fallback_used, retries,
    truncated, thoughts_tokens) as the chain/dispatcher return, replacing the growing
    tuple. `_call_gemini_with_chain`/`_complete_json` return it; truncation short-circuits
    the fallback chain (switching models won't fix a cap hit).
  - `resolve_l5`: on `truncated`, logs ERROR (item_id + thoughts_token_count + model +
    cap) and returns `_empty_result(status=TRUNCATED_OUTPUT)`. Renamed
    `_make_insufficient` → `_empty_result(status=...)` (default INSUFFICIENT_CONTEXT).
  - Diagnostics sink now also carries `thoughts_tokens`.
- `scripts/run_l5_calibration.py`: JSONL row + raw file record `finish_reason` and
  `thoughts_token_count`; raw file persists verbatim `response.text` (fix from prior
  entry). Added report section "7b. Thinking tokens & truncation" (finish_reason counts,
  thoughts min/max/mean, cap-headroom / MAX_TOKENS warning).
- `tests/test_l5.py`: `test_max_tokens_yields_truncated_not_insufficient` — mocked
  MAX_TOKENS response → TRUNCATED_OUTPUT (not INSUFFICIENT), score None, exactly one
  `generate_content` call (no parse retry).
- `scripts/debug_one_call.py`: default cap now reads `L5_MAX_OUTPUT_TOKENS` so it mirrors
  production.

**Verified this session:** `py -3.11 -m pytest -q -m "not live"` → **121 passed, 10
deselected**. One live S1 call at cap 8192 → `finish_reason=STOP`, thoughts=914,
output=62, valid JSON, would score → RESOLUTION_PASS.

**NOT done (owner's call, API-gated):** the calibration run itself. Existing
`runs/l5_calibration.jsonl` has 45 stale all-INSUFFICIENT rows — use `--fresh`.
`docs/L5_CALIBRATION.md` is uncommitted and holds the stale buggy report; left as-is,
the fresh run overwrites it.

### 2026-09-24 — INSUFFICIENT_CONTEXT root-cause session (daren-l5)

**Root cause of the all-45-INSUFFICIENT_CONTEXT calibration run — FOUND and VERIFIED (2 live S1 calls):**

- `max_output_tokens=512` in `_call_gemini_single`'s `GenerateContentConfig` is too
  small. Gemini 3.x counts internal **thinking tokens** against that cap. Thinking
  consumed the budget → `finish_reason=MAX_TOKENS` → `response.text` truncated mid-JSON
  (`'{\n  "polarity_or'`, 16 chars) → `JSONDecodeError` → both parse attempts fail →
  INSUFFICIENT_CONTEXT.
- Verified via new `scripts/debug_one_call.py` (reproduces the exact production config,
  dumps the untouched response):
  - cap 512:  `MAX_TOKENS`, thoughts=487, candidates=7, text=16 chars → fails.
  - cap 2048: `STOP`, full valid JSON, parses, score 0.67 → RESOLUTION_PASS (expected).
  - thinking tokens varied 487 → 969 between two identical temp-0 calls — cost is
    variable; cap must clear the worst case.

**Corrected `retries` semantics (this misreading cost the prior session):**

- `retries` counts **only 5xx backoff sleeps** (`_call_gemini_single` line ~297). It is
  NOT incremented by the JSON-parse / missing-field retry (the inner `parse_attempt`
  loop). Therefore `retries=0` does NOT mean "the missing-subscore retry never ran" —
  that retry DID run (both attempts) and both failed on truncated JSON. The prior
  handoff's inference from `retries=0` was wrong.
- The parse-failure path to INSUFFICIENT_CONTEXT: `_call_gemini_single` returns
  `(None, 0, None)` → `_call_gemini_with_chain` returns `(None, model, False, 0)` (skips
  fallback, correct) → `resolve_l5` calls `_make_insufficient(..., retries=0)`.

**Offline fix applied — raw-response logger (was writing garbage):**

- The old `runs/raw/*.json` files contained `result.subscores` (i.e. `{}` for every
  INSUFFICIENT_CONTEXT) — NOT the model's response. 45 paid calls produced zero usable
  evidence of what Gemini returned.
- Fix: added optional `diagnostics: dict` sink threaded through `resolve_l5` →
  `_complete_json` → `_call_gemini_with_chain` → `_call_gemini_single`. The Gemini path
  fills it with verbatim `raw_text` and `finish_reason`. Deliberately NOT added to the
  frozen `L5Result` (would bloat every serialized blind-run record). All new params
  default `None` → backward-compatible.
- `run_l5_calibration.py`: raw file now persists `{raw_text, finish_reason, subscores}`;
  JSONL row now includes `finish_reason`.
- `scripts/debug_one_call.py` added (one-call diagnostic; prints finish_reason,
  usage_metadata incl. thoughts_token_count, len(text), verbatim text, parts,
  function_calls).

**NOT done (awaiting decision):** the production `max_output_tokens` cap fix itself.
One variable at a time — raise cap vs. set `thinking_budget` is an open choice. See
Next action.

**Verified this session:** `py -3.11 -m pytest -q -m "not live"` → **120 passed, 10
deselected**. Two live S1 debug calls (cap 512 fails, cap 2048 passes).

**Unrelated:** upgraded Claude Code CLI 2.1.170 → 2.1.282 (npm global; winget does not
manage this install).

### 2026-09-21 — Audit session
- First session to produce HANDOFF.md; no prior handoff existed
- Ran all 8 verification commands; installed pytest-cov (was missing)
- Baseline: 102 offline tests pass; 5 live tests fail (no API key, no skip)
- Coverage: 76% total; layers.py and runner.py at 0%
- Found 13 open issues (a–m); issue (h) resolved; issue (i) is the only blocker
- Source code not committed to git (all untracked)
- No code changed this session (audit-only)

### 2026-09-21 — Fix session (daren-l5)
- Resolved d (d26f7ae): silent 0.0 subscore defaults removed; missing fields now retry then INSUFFICIENT_CONTEXT; 5 new regression tests
- Resolved i (393c6b5): conftest.py added; live tests skip without API key; `py -3.11 -m pytest -q` now 106 passed, 6 skipped
- Resolved b (d74e036): temperature explanation corrected in docs/L5_CALIBRATION.md and scripts/run_l5_calibration.py
- Resolved m (fe433c7): bare "PASS" string replaced with AnchoringStatus.PASS in runner.py
- Skipped a: model choice pending re-decision; marked "superseded, pending"
- Corrected item k: prior audit was run from wrong directory (parent jokes\); repo and commits exist on daren-l5
- Suite state: 106 passed, 6 skipped (no API key)

### 2026-09-21 — Gemini backend session (daren-l5)
- Task 1 (a771b0e): fixtures restored — tests/fixtures/l5_anchors.jsonl replaced with 10 spec items (S1/S2 skeleton minimal pair, E1/X1 elephant/trunk minimal pair, A1 autobiography, D1 shingles, P1 cows/horns, P2 explain-fail, P3 curtains, N1 bank/INSUFFICIENT_CONTEXT); suite 110 passed, 10 skipped
- Task 2 ("l5: add gemini backend"): Gemini backend wired end-to-end
  - config.py: L5_BACKEND="gemini", L5_MODEL_GEMINI="gemini-3.6-flash"
  - pyproject.toml: google-genai>=2.0 added; google-genai 2.24.0 installed
  - l5_resolution.py: pydantic response models (_QALLMResponse, _DefinitionalLLMResponse, _DialogueLLMResponse); _is_spend_cap_error, _extract_retry_delay, _gemini_generate (429+retryDelay handling), _call_gemini (schema-constrained, temperature=0), _complete_json dispatcher; resolve_l5 signature unchanged (client: Any = None)
  - tests/conftest.py: skip logic checks GEMINI_API_KEY vs ANTHROPIC_API_KEY based on active backend
  - tests/test_l5.py: _mock_client mocks both client.messages.create and client.models.generate_content; test_insufficient_context_when_anchoring_not_pass asserts both not_called
  - tests/test_l5_missing_subscores.py: _client_always_omitting mocks both interfaces; call_count assertion is backend-aware
  - scripts/run_l5_calibration.py: backend+model in report header, time.sleep(0.5) between calls, None score handling throughout, notes updated for new fixture IDs
  - ARCHITECTURE.md §7: Decision 3 — Gemini backend rationale (schema constraints, temperature=0, cost, data-use warning, S1/S2 smoke test)
  - Partially resolved issue a: L5_BACKEND + L5_MODEL_GEMINI in Settings; Anthropic model string (claude-sonnet-4-6) unverified — not blocking while L5_BACKEND="gemini"
  - L5_BACKEND typed as Literal["gemini", "anthropic"]; dispatcher raises ValueError on unknown backend; one test confirms invalid value rejected at config load
- Suite state: 110 passed, 10 deselected (live tests skip without GEMINI_API_KEY)
- Live calibration NOT run — requires GEMINI_API_KEY

### 2026-09-23 — X1 replacement session (daren-l5)

**X1 replaced and original moved to L4 fixture set (issue n resolved):**

- Previous session's proposed X1 replacements were all positives (container sense used to answer the question = E1 restated). A relevance negative needs both senses anchored AND a punchline that fails to resolve.
- D1 text corrected to match spec (Danny asks why Gerry is glum; Gerry has shingles; the doctor prescribed aluminum siding). Previous text ("Wood or aluminum siding? No, it's a skin rash!") had wrong structure. Anchors unchanged: `"bad case of shingles"` / `"Aluminum siding"`.
- New X1: `"Why do elephants have a trunk? Because the car's trunk was already full."` — `sense_a_anchor="elephants"`, `sense_b_anchor="car's trunk"`. Both senses present with distinct spans; punchline (car's storage trunk was full) explains nothing about a proboscis → RESOLUTION_FAIL. This is a genuine L5 negative, not an E1 restatement.
- Original X1 (`"...large grey mammals"`) saved to `tests/fixtures/l4_anchoring.jsonl` as L4 anchoring negative (`expected_anchoring_status: ONE_SENSE_ONLY`). Valid test of the wrong layer — not deleted.

**Suite state (VERIFIED this session, both runs):** `py -3.11 -m pytest -q` → **130 passed, 0 failed** (120 offline + 10 live), exit 0.

### 2026-09-23 — Anchor-span fix session (daren-l5)

**Root cause identified:** All 8 non-resegmentation PASS-status fixtures had `sense_a_anchor_quote == sense_b_anchor_quote` (the ambiguous term itself in both fields) instead of distinct context spans. Per ARCHITECTURE.md Decision 2, identical anchor spans are only legal for `resegmentation`. The previous live-test "passes" for A1 and P2 were the only two fixtures that didn't trigger this structural bug; L5's QA and dialogue branches have NEVER been exercised against a live model.

**Changes this session:**

- `ARCHITECTURE.md`: Added "Anchor-quote definition" subsection to Decision 2, clarifying that anchor quotes are context spans activating each sense, not the ambiguous term itself.
- `src/doubletake/schema.py`: Added docstring to `L4Result` explaining the context-span requirement and the resegmentation exception.
- `tests/fixtures/l5_anchors.jsonl`: Fixed context spans for S1, S2, E1, D1, P1, P3. D1 text also updated to include the required context phrases. A1, P2, N1 unchanged. X1 unchanged (awaiting owner approval on replacement — see issue n).
- `src/doubletake/l5_resolution.py`: Added `WARNING` log to the existing `anchoring_status != PASS` short-circuit; added new short-circuit guard for identical anchor spans where `anchor_relation != RESEGMENTATION`, with `WARNING` log naming the item and reason.
- `tests/test_l5.py`: Updated `_qa_l4()`, `_dialogue_l4()`, `_qa_record_for_routing()` to use distinct anchor spans; updated `test_fixture_item_offline` to handle the new short-circuit case; added `test_fixture_anchor_quotes_are_substrings_and_distinct` validation test (offline, no LLM, fails intentionally for X1).
- `tests/test_l5_missing_subscores.py`: Updated `_qa_record()` to use distinct anchor spans.

**Suite state (VERIFIED this session):** 119 passed, **1 failed** (`test_fixture_anchor_quotes_are_substrings_and_distinct` on X1 — intentional), 10 deselected.

### 2026-09-22 — Resilience + calibration session (daren-l5)

**Task 1 DONE ("l5: retry 5xx and model fallback chain"):**
- `config.py`: added `L5_MODEL_GEMINI_CHAIN: list[str] = ["gemini-3.8-flash"]`
- `schema.py`: added `model_used: str = ""`, `fallback_used: bool = False`, `retries: int = 0` to all three L5 result types (L5QAResult, L5DefinitionalResult, L5DialogueResult)
- `l5_resolution.py`:
  - Imports `ServerError as _GeminiServerError` (critical: SDK raises ServerError for 5xx, ClientError for 4xx — separate classes)
  - `_call_gemini_single`: up to 5 attempts per model, exponential backoff 2/4/8/16s between attempts, catches `_GeminiServerError` only
  - `_call_gemini_with_chain`: tries primary then each fallback in chain after 5xx exhaustion; parse failure does not trigger fallback
  - `_complete_json` and `resolve_l5` updated to propagate `model_used`, `fallback_used`, `retries`
  - `_gemini_generate` updated: `if delay:` (positive only) for retry; 0s retryDelay now raises RuntimeError immediately (daily-quota RPD case)
  - `_make_insufficient` updated to accept and forward tracking fields
- `tests/test_l5.py`: 9 new offline tests (5xx 2-call retry, 5-503 fallback, all-exhausted raises, RPD fails fast); `time.sleep` patched in all 5xx/quota tests; `time.sleep(L5_CALL_PAUSE_SECONDS)` added after each live call

**Task 1 bug found and fixed (same commit):**
- Original code caught `_GeminiClientError` for 5xx retries — wrong; SDK raises `ServerError` (sibling of `ClientError`, not a subclass)
- Discovered from live test: `google.genai.errors.ServerError: 503 UNAVAILABLE` propagated without triggering retry
- Fix: added `ServerError` import, changed `except _GeminiClientError` to `except _GeminiServerError` in `_call_gemini_single`
- RPD issue also fixed: 429 with `retryDelay=0s` now raises RuntimeError immediately instead of retrying

**Task 2 DONE ("calibration: resumable runner"):**
- `scripts/run_l5_calibration.py`: full rewrite — JSONL append-per-row, skip-completed, `--resume`/`--fresh`/`--probe` flags, per-row `wall_clock_ms`, `raw_response_path`
- `docs/L5_CALIBRATION.md`: regenerated as NO-DATA placeholder with prominent status header
- Fixed two Unicode encoding bugs (Windows cp1252): `✓`/`✗` → `OK`/`!!`, em-dash in probe print removed

**Task 3 NOT DONE — calibration blocked:**
- Gemini free-tier RPD quota (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit 20/day for `gemini-3.6-flash`) exhausted by live pytest runs
- Calibration attempt made ~19 API calls — all 429; 0 useful rows written (N1 row in JSONL is INSUFFICIENT_CONTEXT with no LLM call)
- Q2, Q4, Q5, Q6, Q7 from calibration spec cannot be answered — no score data
- Resume: `py -3.11 scripts/run_l5_calibration.py --probe` then `--resume` after midnight Pacific quota reset
- Suite state: 119 passed, 10 deselected
