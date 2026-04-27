# HMS Hood — Captain 3 Sign-off
**Date:** 2026-04-27  
**Mission:** 2026-04-26_231226_f8a0d05d  
**Action Station:** 0 (Patrol — read-only adjudication)

---

## 1. Confirmed defects

> **B1 — Medium — Heatmap y-axis labels ignore role overrides; plot and heatmap contradict each other on same curve** — Vanguard ref: §1/B1; Astute ref: §(b); Recommendation: add optional `sensor_roles` param to `plot_temperature_gradient_heatmap`.

> **B2 — Low-Medium (latent) — Line 53 uses `loader.current_curve_index` while line 19 uses `st.session_state.current_curve_index`; divergence yields mismatched multiselect labels and plot colouring** — Vanguard ref: §1/B2; Astute ref: §(a); Recommendation: pass explicit index at line 53 and hoist both calls to a single assignment.

Both defects carry concrete file:line citations (`plots.py:211-238`, `temperature_profile.py:19` vs `:53`), empirical verdicts PASS/CONDITIONAL PASS, and user-observable symptoms. Both confirmed.

---

## 2. Demoted to smell

None. Vanguard raised exactly two bugs. B2 stays as a confirmed defect despite its narrow trigger window: the two-index dual-call architecture is a standing invitation for any future caller (URL param reader, keyboard shortcut, test harness) to re-fire the bug. "Narrow trigger window" is not a structural guarantee — it is a coincidence of the current sidebar execution order. Latent fragility of this kind has bitten this codebase before (see CLAUDE.md "Known Fragile Areas"). B2 remains a bug; demotion rejected.

---

## 3. Code smells & DRY findings — accepted as-is

- **S1** — Pattern A label-building loop (`temperature_profile.py:22-38`) — accept; collapses with S2 into canonical helper.
- **S2** — Pattern B role-building loop (`temperature_profile.py:52-67`) — accept; collapses with S1.
- **S3** — Silent empty heatmap on missing T* columns (`plots.py:217-221`) — accept; add guard before `np.array()`.
- **S4** — Seven `st.session_state` reads in `render()` block unit testing — accept; `render(state)` injection fixes.
- **S5** — Color-only role distinction; line-style partially mitigates — accept as low-priority; defer to accessibility pass.
- **S6** — Redundant double-fetch of assignments (lines 19 and 53) — accept; resolved by B2 fix + hoisting.
- **S7** — Duplicate role-iteration logic between tab and `plots.py:107-113` — accept; resolved by canonical helper.
- **DRY Group A** — `['T1'..'T8']` hardcoded at 13+ sites; `SENSOR_LIST` belongs in `config/constants.py` — accept.
- **DRY Group B** — Pattern A/B four-way role loop repeated three times across `temperature_profile.py` and `curve_comparison.py` — accept; `build_sensor_role_map` / `build_sensor_label_map` in `src/ui/sensor_role_helpers.py` is the right abstraction.

No flags. All smell and DRY findings are well-evidenced and internally consistent.

---

## 4. Refactor scope estimate

- **Estimated LOC delta:** ~150 LOC across ~8 files: +70 new `src/ui/sensor_role_helpers.py` with helpers and tests, +10 `config/constants.py` (`SENSOR_LIST`), -26 Pattern A/B deleted from `temperature_profile.py`, +20 heatmap signature + guard (`plots.py`), -20 hardcoded `['T1'..'T8']` literals across 5 files replaced with `SENSOR_LIST`, +60 new failing-first unit tests, +16 `render(state)` injection wiring.
- **Captain count:** 4 + optional Red-cell (Hood adopts Vanguard §5 exactly — scope is well-scoped per captain, no overlap, correct sequencing).
- **Captain 1:** `SENSOR_LIST` in `config/constants.py`; new `src/ui/sensor_role_helpers.py` with `build_sensor_role_map` / `build_sensor_label_map`; failing tests first; no callers migrated.
- **Captain 2:** `plot_temperature_gradient_heatmap` signature + role-aware y-axis + S3 guard; call site at `temperature_profile.py:81` updated; resolves B1; failing tests first.
- **Captain 3:** `tabs/temperature_profile.py` — delete Patterns A/B, hoist assignments call, fix line-53 explicit index, `render(state)` injection; resolves B2 and S4; failing tests first.
- **Captain 4:** Site-by-site `SENSOR_LIST` sweep (`sidebar.py:239-250`, `plots.py:91`, `loader.py:865,1404`, `curve_comparison.py:31`); regression tests first.
- **Optional Red-cell:** Re-run Astute scenarios (a), (b), (c) after each captain lands to confirm closure.

---

## 5. Recommended branch name

`refactor/temperature-profile-canonical-roles`

---

## 6. Go/no-go

**Go.** Both confirmed bugs have concrete file:line citations and empirical verification; the DRY debt is well-mapped with a clear migration path; captain scope is tightly bounded with no cross-captain ambiguity. Launch the follow-up flotilla now.
