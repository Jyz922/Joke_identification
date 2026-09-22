# HANDOFF — DoubleTake
Last updated: 2026-09-21 by daren-l5 gemini-backend session

---

## Current state (VERIFIED)

All items below were confirmed by commands run in this session.

| Check | Command | Result |
|---|---|---|
| Offline test suite | `py -3.11 -m pytest -q` | **110 passed, 10 skipped** — live tests skip (no GEMINI_API_KEY) |
| Offline only | `py -3.11 -m pytest -q -m "not live"` | **110 passed, 10 deselected** |
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
| L5 | **done** | yes (offline: 110 passed; live: 10 tests, skip without key) | Gemini backend (default); Anthropic backend switchable via L5_BACKEND; live tests skip when GEMINI_API_KEY unset |
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

Live L5 calibration run: set `GEMINI_API_KEY` and run `py -3.11 scripts/run_l5_calibration.py` to fill in `docs/L5_CALIBRATION.md`.

After that: proceed to L2 (WordNet + SemCor + Kuperman AoA retriever) per the agreed build order.

---

## Team workflow

This file has one owner: **Daren**. Other contributors do not edit HANDOFF.md; they note status in their PR description.

---

## Session log

*(append-only — never rewrite old entries)*

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
