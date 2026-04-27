# Captain's Log — M1 Foundation

**Admiral:** HMS Britannia (Opus)
**Mission ID:** 2026-04-27_001526_acde7444
**Branch:** refactor/temperature-profile-canonical-roles
**Duration:** 39 minutes — outcome **ACHIEVED**

## Mission summary
- **Planned:** Introduce canonical SENSOR_LIST + new src/ui/sensor_role_helpers.py module with two pure helpers; TDD failing-first; no call-site migrations.
- **Achieved:** Iron Duke landed commit `5524a0b` with 16 new tests (golden test pins M3 contract). Astute verified GO with corrections.
- **Metric:** pytest 354 passed / 8 failed / 1 skipped (was 338/8/1 → +16 passes; one prior flake re-fired).

## Delivered artefacts
- `config/constants.py` — `SENSOR_LIST = ('T1'..'T8')` appended.
- `src/ui/sensor_role_helpers.py` — `build_sensor_role_map(loader, curve_index=None)` and `build_sensor_label_map(loader, curve_index=None, *, role_format="({role})")`. No Streamlit dependency.
- `tests/test_sensor_role_helpers.py` — 16 tests across 3 classes; golden parametrized test against inline-loop replicas.

## Key decisions
- **Iron Duke implements directly (0 crew).** Atomic single-deliverable mission with embedded TDD; skeleton-crew anti-pattern would apply if a single PWO duplicated the captain's work. Confirmed correct call by hull telemetry (no captain reported context strain).
- **Astute as red-cell with HOLD authority.** Per project standing order, red-cell empirically verifies — don't trust captain self-reports. Immediately paid off when Iron Duke claimed 355 pytest passes; Astute observed 354 and explained why (`test_deep_insertion` is an order-dependent flake, not fixed by M1).

## Validation evidence
- Iron Duke: 16 tests RED first (ImportError on missing module), then GREEN after implementation. Documented in return summary.
- Astute: independent pytest run confirmed 354/8/1; helper-vs-inline parity proven by spot-check across 4 scenarios; override re-run produced expected per-curve role differences (curve 0 surface=T6, curve 1 surface=T7).
- `git diff main..HEAD --stat` confirmed only the three owned files changed outside `.nelson/`.

## Open risks (carried to downstream missions)
1. **Override storage format.** Briefing said `{'surface_sensor': 'T2'}`; actual format is `{'surface': 'T2'}` (without `_sensor` suffix). Public API is `loader.set_sensor_override(curve_idx, 'surface', sensor)`. M3 must use the public API, not direct `_sensor_overrides` dict mutation.
2. **Geometric ambient recalculation.** Surface override triggers a recalc that wipes pre-existing internal-sensor assignments (Astute observation in §5). M3 must audit this when replacing the inline loops — the helpers correctly reflect post-recalc state, but if M3 wires up overrides incorrectly the visible behaviour can change.
3. **`test_deep_insertion` flake.** Unresolved — order-dependent state pollution with `test_shallow_insertion`. Out of scope for this flotilla; flagged for the pre-existing-failures cleanup mission.
4. **Helper returns full 8-key dict.** Includes explicit `'unknown'` for unassigned sensors. Downstream code must not assume partial dict (Pattern B inline loop returned partial; helper does not).

## Follow-ups
- **M2** can begin: extend `plot_temperature_gradient_heatmap` signature, fix B1, migrate the heatmap call site at `tabs/temperature_profile.py:81`.
- **M3** must use `loader.set_sensor_override(...)` public API and account for the geometric ambient recalc when refactoring Pattern A/B sites.
- **M4** sweep can adopt `SENSOR_LIST` import safely.
- **M5 finale** should add a regression test for the order-dependent flake if possible (separate from this flotilla's scope).

## Mentioned in Despatches
- **HMS Iron Duke** — clean atomic commit, golden test (h) using parametrized inline-loop replicas was the right design call (turns the M3 contract from prose into executable proof).
- **HMS Astute** — empirical re-run caught the off-by-one pytest claim and the override-format briefing error; both would have cost M3 time. Standing-order discipline upheld.

## Reusable patterns
- **Adopt:** Golden test against inline-loop replicas. Future helper-extraction missions should mirror this — replace prose claim of equivalence with an executable parametrized test.
- **Adopt:** Always have red-cell re-run pytest themselves; never trust captain self-reports on count deltas.
- **Avoid:** Briefing errors on storage formats. The admiral wrote `_sensor_overrides[curve_index] = {'surface_sensor': 'T2'}` from memory; should have read `loader.py:850-857` first to confirm the actual format. Cost: Astute spent extra time discovering and correcting.

## Mission stats
- Captains: 2 (HMS Iron Duke, HMS Astute)
- Crew per ship: 0
- Standing-order violations: 0
- Pytest delta: +16 passes
- Commit: 5524a0b
