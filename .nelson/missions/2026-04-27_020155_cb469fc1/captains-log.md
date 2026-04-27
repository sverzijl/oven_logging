# Captain's Log — M4 DRY Sweep

**Admiral:** HMS Britannia (Opus)
**Mission ID:** 2026-04-27_020155_cb469fc1
**Branch:** refactor/temperature-profile-canonical-roles
**Outcome:** **ACHIEVED**

## Mission summary
- **Planned:** Migrate hardcoded `['T1'..'T8']` literals to `SENSOR_LIST` import across sidebar.py, plots.py, loader.py, curve_comparison.py, sensor_naming.py, curve_boundary_detector.py.
- **Achieved:** Spey commit `16e9d56`. 11 canonical-8 sites migrated across 5 files. `_SENSOR_COLUMNS` deleted. Astute GO across 8 checks.
- **Metric:** pytest 376-377 passed / 7-8 failed / 1 skipped (was 373/8/1; +3 new migration tests + flapper).

## Delivered artefacts
- 11 canonical-8 sites migrated to `from config.constants import SENSOR_LIST` + `list(SENSOR_LIST)` (or direct `SENSOR_LIST` for tuple usage).
- `src/data/curve_boundary_detector.py` — `_SENSOR_COLUMNS` deleted (Option A); 2 internal references updated.
- `tests/test_sensor_list_migration.py` — 3 regex-based regression guard tests (forbidden patterns, SENSOR_LIST imports, `_SENSOR_COLUMNS` absence).
- `sensor_naming.py:74,107` partial-fallback lists (4-element and 3-element) intentionally preserved — they're not canonical T1..T8.

## Key decisions
- **Option A on `_SENSOR_COLUMNS`** — delete and replace, not re-export. Two references, no scope balloon.
- **Partial-fallback preservation** — 3- and 4-element lists in `sensor_naming.py` are deliberate sparse defaults, not the canonical 8. Migration would change behaviour.
- **`list(SENSOR_LIST)` vs `SENSOR_LIST`** — Streamlit's selectbox accepts both; the migration uses `list(SENSOR_LIST)` where the API expects a list (selectbox options, multiselect options) and direct `SENSOR_LIST` where iteration is enough.

## Validation evidence
- **Independent grep audit (Astute §1):** zero canonical-8 standalone forms outside allow-list (`config/constants.py`, `tests/test_sensor_list_migration.py`).
- **Selectbox preservation (Astute §3):** `options=list(SENSOR_LIST)` and `index=list(SENSOR_LIST).index(current_core/surface)` both verified — structurally identical to pre-migration.
- **Loader behaviour (Astute §5):** real CSVs load cleanly with identical per-curve sensor assignments to M3 baseline. `SENSOR_LIST` order confirmed equal to `[f'T{i}' for i in range(1,9)]`.
- **Pytest delta:** stable +3 across runs (modulo the pre-existing flapper). All 35 prior-flotilla tests 100% green — no breakage.
- **app.py audit:** clean. No hardcoded T1..T8 forms in the entry point.

## Open risks (for M5)
1. **`loader.py:1244` mixed-column list** — Astute caught a multi-line list that escaped Spey's single-line regex. It includes T1..T8 mixed with Virtual* columns; arguably a less-pure canonical site. M5 should decide whether to hot-fix or defer.
2. **Partial-range lists** — pre-existing technical debt across several src/ files (T1–T4, T5–T8 sub-groups for core/surface average computations). Out of this flotilla's scope.
3. **`test_deep_insertion` flapper** — order-dependent failure that oscillates pass/fail. M5 finale should decide whether to fix or document and defer.

## Follow-ups
- **M5 next:** flotilla finale — comprehensive E2E + cross-mission perturbation re-runs + final no-regression guardrail.

## Mentioned in Despatches
- **HMS Spey** — clean methodical sweep across 7 owned files; correct judgement on partial-fallback preservation; commit message documented decisions.
- **HMS Astute** — independent grep audit caught Spey's claimed pytest count off by 1 (377 → 376) AND the loader:1244 multi-line site Spey's regex missed. Empirical loader smoke-test added confidence beyond structural checks.

## Reusable patterns
- **Adopt:** Regex-over-source regression guard test catches reintroduction of forbidden patterns. Effective for sweeping migrations.
- **Adopt:** Read every grep hit before migrating — the "mixed-column" case (T1..T8 + Virtual*) is correctly NOT in scope but you only know that by reading.
- **Avoid:** Single-line regex misses multi-line literals. M5 should run a more exhaustive pattern check.

## Mission stats
- Captains: 2 (HMS Spey, HMS Astute)
- Crew per ship: 0
- Standing-order violations: 0
- Pytest delta: +3 passes (4 with flapper)
- Commit: 16e9d56
- Files touched: 7
