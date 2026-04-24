# Captain's Log — HMS Spartan (M6 of flotilla `refactor/expected-bake-time`)

**Mission ID:** `2026-04-24_153328_f274752b`
**Branch:** `refactor/expected-bake-time`
**Risk tier:** MEDIUM (Action Station 2 — Streamlit widget-key bleed is the primary hazard; precedent mission `2026-04-24_102020_af6532e1` fixed the same class of bug in the temperature_profile tab)
**Mode:** single-session

## Sailing Orders

| | |
|---|---|
| Outcome | Per-curve "Expected bake time (min)" `st.number_input` widgets in the sidebar Analysis Settings block; widget keys scoped by filename + curve_number (1-indexed); on-change call `loader.set_expected_durations(...)` + `st.rerun()`; empty → None. |
| Metric | 3+ widget smoke tests pass; no regression in existing sidebar tests; sidebar imports cleanly; loader `set_expected_durations` invoked only on change (no infinite rerun). |
| Deadline | This session. |

## Decisions & Rationale

1. **Extract pure helpers into `src/ui/expected_duration_widgets.py` BEFORE touching `sidebar.py`.** Streamlit integration is painful to unit test (requires running the runtime). By extracting the three conversion / lookup / assembly primitives — `minutes_to_seconds`, `session_key_for_curve`, `build_hint_list_from_session` — into a pure module, the MEDIUM-risk hazards (unit confusion, key collisions, empty-value handling) get 11 tests before Streamlit sees a single widget. This also matches the pattern established by M2 (`src/data/sigmoid_refinement.py` as pure primitive, wrappers elsewhere).

2. **Widget keys baked from `(filename, curve_number)`, NOT `current_curve_index`.** The temperature_profile tab fix from mission `2026-04-24_102020_af6532e1` anchored the convention; M6 reuses it. Concrete hazard: user has 3 curves, enters 25 min for curve 2, switches view to curve 3, the widget default reads `current_curve_index=2` and pre-fills the curve-3 box with the curve-2 hint. Using `curve_number` as part of the key makes the hint stable regardless of which curve is currently selected.

3. **Empty / 0.0 / None minutes all treated as "no hint".** `st.number_input(min_value=0.0, value=None)` can return `None` or `0.0` depending on widget state; both map to "no hint". `build_hint_list_from_session` collapses an all-empty result to the overall `None` so the loader forwards `None` to the detector and the byte-identical no-hint path fires. This is the regression-free guarantee.

4. **Change-detection before `set_expected_durations`.** Streamlit reruns on every widget change. If M6 naively called `loader.set_expected_durations` every rerun, every view change would trigger a fresh detection pass — wasteful, and in the worst case infinite (because `st.rerun()` triggers another rerun). Guard: `if loader.expected_durations_s != hint_list: ...`. Only re-runs when the hint list actually changed.

5. **Sidebar integration inside `st.expander`, collapsed by default.** The hint is optional. Placing it in an expanded section would draw the user's eye to a feature they may not need; collapsing it keeps the sidebar visually uncluttered while still advertising the capability via the "⏱️ Expected bake time (optional)" header. Caption inside explains the two-pass UX.

6. **Pre-fill each widget with the detector's native duration.** First upload → detection runs with no hint → widgets pre-fill with detected durations. User who is happy with detection can leave everything alone; user who wants to override sees the "as detected" value and can adjust. This makes the feature additive — the baseline is "show me what you found", not "demand I enter a value".

7. **No separate test for the full Streamlit integration.** Unit-testing the sidebar directly requires `streamlit.testing.v1` infrastructure which isn't in the project today and would be a disproportionate investment for M6's surface. Alternatives: (a) smoke import to verify syntax (done), (b) manual browser smoke via `streamlit run app.py` (noted in validation plan, belongs to M7 finale along with the red-cell 36-run battery).

## Artifacts

| File | Change | Size |
|---|---|---|
| `src/ui/__init__.py` | **NEW** — package marker | 0 lines |
| `src/ui/expected_duration_widgets.py` | **NEW** — 4 pure helpers | 91 lines |
| `sidebar.py` | Import helpers; call `_render_expected_duration_hints()` after Product Type; new helper function at module bottom | +~70 lines |
| `tests/test_sidebar_expected_duration.py` | **NEW** — 11 tests across 3 classes | 136 lines |

## Validation Evidence

**Red bar:** `ModuleNotFoundError: No module named 'src.ui.expected_duration_widgets'`.

**Green bar:**
```
pytest tests/test_sidebar_expected_duration.py
============================= 11 passed in 0.04s ==============================
```

**Smoke import:**
```
python -c "import sidebar; ..."
sidebar import OK
_render_expected_duration_hints defined: True
helpers importable from src.ui
  example key: expected_bake_minutes__foo.csv__c2
  minutes 25 -> seconds: 1500.0
```

**Full-suite:** `8 failed, 214 passed, 1 skipped` — failures match pre-existing baseline (memory follow-up `(j)`). +11 net passing tests vs. post-M5.

**Manual browser smoke:** DEFERRED to M7 finale, where the full 36-run red-cell battery runs end-to-end via Streamlit on the 3 primary real CSVs.

## Open Risks / Follow-ups

- **Browser smoke pending M7.** No M6 test currently verifies that a user clicking the expander, typing "25" into the bake-1 input, and pressing Enter triggers a re-detection and visible window adjustment. That full-loop test belongs in M7's empirical finale alongside the noise battery.
- **`duration` field on the curve dict is in MINUTES** (detector line 124: `curve_data["TimeMinutes"]`, used for `duration` max). Widget pre-fill uses this directly, which happens to be correct — but a future detector change that switches `duration` to seconds would silently break the pre-fill. Mitigation: M7 adds a cross-check that pre-fill matches `duration × 60 == end_time - start_time` within one sample.
- **`st.rerun()` on hint change.** Streamlit's rerun model re-executes the sidebar; the change-detection guard (`loader.expected_durations_s != hint_list`) prevents the infinite-loop hazard. If a future refactor moves hint state to a different object, the equality check needs to follow.

## Mentioned in Despatches

- The helper module `src/ui/expected_duration_widgets.py` is the first module under `src/ui/` — previously all UI lived at the repo root. Establishes the convention that UI pure-logic helpers (not widgets themselves) belong under `src/ui/`. Future follow-ups: the sensor override helpers currently inlined in `sidebar.py` lines 226–322 would also benefit from this treatment; noted for the post-flotilla cleanup mission.

## Reusable Patterns

- **Pure helpers + thin Streamlit wrapper.** Unit-testing Streamlit is painful. Extract everything non-widget (key construction, unit conversion, list assembly, equality checks) into a pure module; let the sidebar function be a minimal glue layer that calls widgets and invokes the helpers.
- **Change-detection equality guard against Streamlit infinite reruns.** Any `st.rerun()` path that fires "on change" needs `if current_state != new_state` to avoid firing every frame.
- **Session key format: `<prefix>__<filename>__<curve_number>`** — double-underscore separators are unambiguous and filename collisions are contained.

## Next Up

M7 HMS Victory — flotilla finale. MEDIUM risk (no new code but may surface regressions bouncing work back to M3/M4). Will run:
- The 36-run red-cell battery (σ ∈ {0.15, 0.5, 1.0} × 3 real CSVs × 4 hint modes)
- Browser smoke on real CSVs
- Memory update: append completion items to `project_refactoring_plan.md`
- Final captain's log summarising the whole flotilla

Entry criteria for M7: met.
