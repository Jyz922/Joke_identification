# HANDOFF — DoubleTake
Last updated: 2026-09-21T17:30:00Z by audit session (no prior HANDOFF.md existed)

---

## Current state (VERIFIED)

All items below were confirmed by commands run in this session.

| Check | Command | Result |
|---|---|---|
| Offline test suite | `py -3.11 -m pytest -q` | **5 failed, 102 passed** — all failures are live tests (TypeError: no API key, not skipped) |
| Live tests only | `py -3.11 -m pytest -q -m live` | **5 failed, 1 passed, 101 deselected** — X1 passes (no LLM call needed); S1–D1 fail with TypeError |
| Coverage (offline) | `py -3.11 -m pytest --cov=doubletake --cov-branch -q -k "not live"` | 76% total — layers.py 0%, runner.py 0% |
| API key | `py -3.11 -c "import os; print(bool(os.environ.get(...)))"` | **NOT SET** |
| L5_CALIBRATION.md | read file | **EXISTS but PLACEHOLDER** — no real run data |
| Runner CLI | `py -3.11 -m doubletake.runner --blind tests/fixtures/sample_blind.jsonl` | **Valid JSONL** — 3 items, 3 trace entries each (L0-pre OK, L5 ERROR, L0-post OK) |
| NotImplementedError stubs | read layers.py | 7 stubs: run_l1, run_l2, run_l3, run_l4, run_l6, run_l7, run_l8 |
| Git state | `git status; git log --oneline -15` | On main, up-to-date with origin; **all source untracked** — only 2 commits (README uploads) |
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
| L5 | **done** | yes (offline: 18+6=24 tests; live: 6 tests) | Offline 89% cov; live tests FAIL (no skip) without API key |
| L6 | **stub** | none | `run_l6` raises NotImplementedError |
| L7 | **stub** | none | `run_l7` raises NotImplementedError |
| L8 | **stub** | none | `run_l8` raises NotImplementedError |

---

## Open issues

### From Step 2 (a–h)

**a. Model string** — CONFIRMED
- `src/doubletake/l5_resolution.py:23` → `_MODEL = "claude-sonnet-4-6"`
- Current identifiers: claude-opus-5, claude-sonnet-5, claude-haiku-4-5-20251001, claude-fable-5-1
- `claude-sonnet-4-6` is not in that list
- Severity: **should-fix** — calibration data should use the model that will be deployed

**b. Temperature comment** — CONFIRMED WRONG
- `docs/L5_CALIBRATION.md:39` states: *"SDK version 1.7.0 removes `temperature` from `messages.create()`"*
- Correct reason: Claude 4.7-and-later models reject non-default temperature/top_p/top_k with a **400 error**; the SDK parameter was not removed
- Severity: **should-fix** — misleads future maintainers about why temperature is absent

**c. test_enums.py** — CONFIRMED HARDCODED (tautological)
- `tests/test_enums.py:37–90` — all 42 status strings are hardcoded in `_README_STATUS_STRINGS`
- The test verifies that the hardcoded strings appear in enums.py, NOT that README.md matches enums.py
- README drift will not be caught
- Severity: **nice-to-have** to fix (tests pass; no false negatives from enum side; only gap is README drift detection)

**d. L5 retry / pydantic validation logging** — NOT FOUND
- There is no pydantic validation of the LLM JSON response. Missing fields default silently to `0.0` via `float(parsed.get(k, 0.0))` in `l5_resolution.py:180–181`
- The retry (attempt 2) triggers only on `json.JSONDecodeError, ValueError, IndexError`
- If the LLM returns valid JSON with wrong/missing field names, no warning is emitted and the score is silently 0.0
- Severity: **should-fix** — silent 0.0 fallback makes schema failures and genuine RESOLUTION_FAIL indistinguishable

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

**i. Live tests don't skip when API key is absent** — CONFIRMED (BLOCKER for CI)
- `tests/test_l5.py:395–413` — `@pytest.mark.live` is only a label; no `pytest.skipif` or conftest skip
- Without API key: 5 tests FAIL with `TypeError: Could not resolve authentication method` instead of being skipped
- `py -3.11 -m pytest -q` reports 5 failures in a clean environment with no key
- Severity: **blocker** — breaks CI and misleads "are tests passing?" check

**j. runner.py and layers.py have 0% coverage**
- No integration test exercises the runner's `run()` function or the registered pipeline
- Runner exception handling (`runner.py:170–180`) is completely untested
- Severity: **should-fix**

**k. No source code committed to git**
- `git status` shows ALL source files as untracked
- Only 2 commits exist: both are README-only uploads from before the codebase was written
- Severity: **should-fix** — no version history, no ability to diff, revert, or bisect

**l. pytest-cov not in test dependencies**
- `pyproject.toml` `[project.optional-dependencies].test` only lists `pytest>=7`
- `pytest-cov` must be installed manually; not documented anywhere
- Severity: **nice-to-have**

**m. Bare string comparison in _l0_post_layer**
- `runner.py:99` — `record.l4_result.anchoring_status == "PASS"` instead of `AnchoringStatus.PASS`
- Works because `AnchoringStatus` is `StrEnum`, but inconsistent with the rest of the codebase
- Severity: **nice-to-have**

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

Fix issue (i) first — live tests must skip, not fail, when `ANTHROPIC_API_KEY` is absent. This is the only thing that makes `py -3.11 -m pytest -q` report failures in a clean environment.

```
# Add to tests/conftest.py (new file):
import os, pytest
def pytest_collection_modifyitems(config, items):
    if not os.getenv("ANTHROPIC_API_KEY"):
        skip = pytest.mark.skip(reason="ANTHROPIC_API_KEY not set")
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(skip)
```

After that: set `ANTHROPIC_API_KEY` and run `py -3.11 scripts/run_l5_calibration.py` to fill in `docs/L5_CALIBRATION.md`.

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
