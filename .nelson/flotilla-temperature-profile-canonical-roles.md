# Flotilla — refactor/temperature-profile-canonical-roles

**Branch:** `refactor/temperature-profile-canonical-roles` (cut from `main` 2026-04-27, after merge `50c620c`)
**Origin:** Hood sign-off from review mission `2026-04-26_231226_f8a0d05d`
**Pattern:** sequential flotilla, one nelson mission per captain, plus Astute red-cell mini-fleet between substantive captains, plus HMS Achilles meta-fleet finale.

## Confirmed defects to close

- **B1 — Heatmap role-blindness** (Medium). `src/visualization/plots.py:211-238` ignores overrides; tab call at `tabs/temperature_profile.py:81` passes no roles.
- **B2 — Index drift** (Low-Medium, latent). `tabs/temperature_profile.py:19` vs `:53` use different index sources.

## Code smells / DRY groups to close

S1, S2 (Patterns A/B), S3 (heatmap empty-input), S4 (`st.session_state` coupling), S6 (double-fetch), S7 (duplicate role-iteration in plots.py:107-113), DRY-A (13+ hardcoded `['T1'..'T8']`), DRY-B (three-place role-iteration loop).

## Mission map

| Mission | Captain | Mission scope | Files touched | Tests added (target) | Stations |
|---|---|---|---|---|---|
| **M1** | HMS Iron Duke | Foundation: introduce `SENSOR_LIST` in `config/constants.py` and new module `src/ui/sensor_role_helpers.py` with `build_sensor_role_map()`, `build_sensor_label_map()`. Failing tests first. No call sites migrated yet. | `config/constants.py`, `src/ui/sensor_role_helpers.py` (new), `tests/test_sensor_role_helpers.py` (new) | ≥8 unit tests for helpers (override-respecting, multi-curve, empty-input, fallback labels) | Station 1, red-cell HMS Astute |
| **M2** | HMS Diamond | Fix B1: extend `plot_temperature_gradient_heatmap()` signature to accept `sensor_roles` (and optional `sensors`), make y-axis labels role-aware, add empty-input guard for S3. Migrate the call site at `tabs/temperature_profile.py:81`. Failing test first. | `src/visualization/plots.py`, `tabs/temperature_profile.py` (one-line call), `tests/test_heatmap_role_aware.py` (new) | ≥4 tests (override applied / no override / empty data / partial sensors) | Station 1, red-cell HMS Astute |
| **M3** | HMS Vanguard | Fix B2 + collapse S1/S2/S6: in `tabs/temperature_profile.py`, hoist a single `assignments = loader.get_sensor_assignments_with_overrides(curve_index)` call, replace Pattern A/B with `build_sensor_label_map`/`build_sensor_role_map`, fix `:53` to pass explicit index. Optional: factor `render(state)` injection signature for S4. | `tabs/temperature_profile.py`, `tests/test_temperature_profile_render.py` (new) | ≥4 tests (multi-curve role consistency, perturbed-index regression for B2, AppTest smoke) | Station 1, red-cell HMS Astute |
| **M4** | HMS Sweep (HMS Spey) | DRY migration: replace `['T1'..'T8']` literals with `SENSOR_LIST` import at `sidebar.py:239,240,249,250`; `src/visualization/plots.py:91,214`; `src/data/loader.py:865,1404`; `src/analysis/curve_comparison.py:31`; `sensor_naming.py:74,107`; `src/data/curve_boundary_detector.py:36 _SENSOR_COLUMNS` (consolidate). | sidebar.py, plots.py, loader.py, curve_comparison.py, sensor_naming.py, curve_boundary_detector.py | ≥3 regression tests + grep guardrail (no remaining hardcoded T1..T8 lists outside SENSOR_LIST) | Station 1, red-cell HMS Astute |
| **M5** | HMS Achilles (finale, meta-fleet) | Cross-mission validation: full pytest run, re-run Astute's three perturbation scenarios (a/b/c) from review mission, add E2E test that exercises the whole tab via Streamlit AppTest, no-regression guardrail vs `main` pytest baseline. | `tests/test_temperature_profile_e2e.py` (new), `tests/test_flotilla_finale_regression.py` (new, mirrors the past flotilla finale pattern) | ≥6 E2E tests + regression baseline | Station 1, red-cell HMS Astute |

## Inter-mission red-cell mini-fleets

After M1, M2, M3, M4 complete and commit, run a small Astute red-cell mini-mission that:
1. Runs `pytest tests/` and confirms the new tests pass and no existing-passing tests fail.
2. Re-runs the perturbation scenario relevant to that mission's scope.
3. Reports go / hold to the admiral. Hold = open damage report, do not advance to next mission until resolved.

These are micro-missions (one captain, ~15min each) — they do not get a full nelson SKILL invocation; they are lightweight verification gates.

## Standing orders for every captain in this flotilla

- TDD non-negotiable: failing test first, watch it fail, then implement to pass.
- DRY non-negotiable: every duplicate found in scope is eliminated in the same mission. No partial migrations.
- Branch hygiene: each mission ends with a single commit on `refactor/temperature-profile-canonical-roles`. No force-push, no rebase.
- Out of scope: keyless widgets in zone_analysis/heating_analysis, TransformationManager integration, loader.py.backup, full app.py split, root-level historical scripts, fixing the 8 pre-existing pytest failures.
- Pre-existing pytest baseline at flotilla start: 8 fail / 338 pass / 1 skip. New tests must pass; the 8 failing tests must remain ignored (out of scope).

## Stand-down criteria for the flotilla

All five missions land their commits, M5's pytest run shows the original 338 still passing plus all new tests passing, and Astute confirms B1 and B2 closed empirically. At that point the branch is ready for merge to `main`.
