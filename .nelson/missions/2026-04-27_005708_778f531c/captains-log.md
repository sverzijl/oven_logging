# Captain's Log — M2 Heatmap Fix

**Admiral:** HMS Britannia (Opus)
**Mission ID:** 2026-04-27_005708_778f531c
**Branch:** refactor/temperature-profile-canonical-roles
**Outcome:** **ACHIEVED**

## Mission summary
- **Planned:** Fix B1 (heatmap role-blindness) and S3 (empty-input fragility); migrate heatmap call site to use `build_sensor_role_map` from M1.
- **Achieved:** Diamond commit `e72c164` adds `sensor_roles` parameter + ValueError empty-input guard. Astute verified GO across all 7 checks.
- **Metric:** pytest 359 passed / 8 failed / 1 skipped (was 354/8/1; +5 new).

## Delivered artefacts
- `src/visualization/plots.py:211-238` — `plot_temperature_gradient_heatmap()` now accepts optional `sensor_roles` and `sensors` parameters; raises `ValueError("No sensor columns in data; expected at least one of T1..T8.")` on empty input.
- `tabs/temperature_profile.py` — heatmap call site (lines 80-87 area) now passes `sensor_roles=build_sensor_role_map(loader, current_curve_index)`. Pattern A (lines 22-38) and Pattern B (lines 52-68) preserved untouched.
- `tests/test_heatmap_role_aware.py` — 5 TDD tests (override applied, no override, empty input, partial sensors, source-regex for call site).

## Key decisions
- **ValueError on empty input.** Diamond chose explicit exception over silent empty figure. Rationale: an empty DataFrame reaching this function is a programming error, not a user-facing edge case. ValueError surfaces it immediately and is trivially testable.
- **Heatmap call site adopts M1 helper now, not in M3.** Project DRY standing order requires eliminating duplication in the same mission that touches it. The alternative (introducing a third inline role-iteration loop in M2 then collapsing it in M3) violates DRY.
- **Pattern A/B explicitly preserved.** M2 has hard guardrail not to touch those loops. Astute confirmed via diff: lines 22-38 and 52-68 unchanged.

## Validation evidence
- **B1 closure (Astute §1):** override scenarios produce role-suffixed labels (e.g., `'Core 2 (Surface)'`). The M0 invariant baseline `['Core 1','Core 2','Core 3','Core 4','Middle 1','Middle 2','Near Surface','Surface']` is now responsive to overrides.
- **Backwards compat (Astute §2):** with no roles, y-axis matches M0 baseline byte-exact.
- **Empty-input (Astute §3):** `ValueError: No sensor columns in data; expected at least one of T1..T8.` raised exactly.
- **End-to-end (Astute §4):** override on a non-core sensor reaches the heatmap via `build_sensor_role_map`. Diamond's surprise (surface override no-ops if target is core) is real but not a regression — same behaviour pre-fix; M3 must work around it.
- **Pytest delta (Astute §5):** 354 → 359, exactly +5. No new failures.
- **Pattern A/B preservation (Astute §7):** diff confirms lines 22-38 and 52-68 untouched.

## Open risks (carried to M3+)
1. **B2 still open.** Heatmap path is now clean; line-plot path still has the index-drift surface (line 19 vs line 53). M3 must close this.
2. **Surface→core override no-op.** When override target is already classified as core, surface override silently does nothing because core priority dominates in `get_sensor_assignments_with_overrides()`. M3 should add a UX note or validation when wiring up the sidebar override flow — though the existing sidebar likely already accounts for this.
3. **Geometric ambient recalc.** Already flagged in M1; surface override to T1 also collapses `internal_sensors` to `[]`. M3 must not be surprised when role maps shift on overrides.
4. **Test fixture fragility.** `test_heatmap_role_aware.py` and the M1 tests load real CSVs at repo root. If those files move, tests break. Out of scope for this flotilla; flag for M5 finale.

## Follow-ups
- **M3 next:** close B2, collapse Pattern A/B with `build_sensor_label_map` and `build_sensor_role_map`, hoist the double-fetch of assignments into a single call, optionally add `render(state)` injection signature for S4.

## Mentioned in Despatches
- **HMS Diamond** — clean atomic commit; ValueError contract decision was correct (Astute spot-checked it). Caught the core-priority surprise via test fixture iteration and documented it.
- **HMS Astute** — empirical re-run with two override scenarios proved the M0 invariant is broken. Independent pytest count confirmed +5. Surfaced three non-blocking downstream concerns.

## Reusable patterns
- **Adopt:** Migrate the call site to the M1 helper in the same mission that fixes the function — don't defer DRY.
- **Adopt:** Source-regex test (`test_heatmap_call_site_uses_helper`) prevents accidental regression where someone re-introduces a raw call without the role map.
- **Avoid:** Test fixture relied on a specific real CSV; if the M5 finale doesn't add fixtures or graceful skip, this becomes flaky on environments without the CSVs.

## Mission stats
- Captains: 2 (HMS Diamond, HMS Astute)
- Crew per ship: 0
- Standing-order violations: 0
- Pytest delta: +5 passes
- Commit: e72c164
