# Red-Cell Review — T7 (HMS Dreadnought, commits a477b82 → 9c3ec90 → 3455fef)

Reviewer: HMS Scrutineer
Reviewed: 2026-04-23
Commits under review: `a477b82` (red-phase smoke tests), `9c3ec90` (refactor), `3455fef` (damage report)
Baseline for comparison: `555e618` (pre-T7 HEAD, Diligent's T6 commit)

## Verdict

**APPROVE**

All six checklist sections pass cleanly. No notes, no reservations. Dreadnought's damage report is accurate on every verifiable claim. Both pre-approved deviations (3 additive session-state keys, 2 `st.tabs` matches) are confirmed legitimate — the second `st.tabs` at `tabs/curve_comparison.py:92` is byte-identical to `app.py:1116` in 555e618, and the 3 new keys are the only new keys (no fourth sneaked in). The refactor is behaviourally lossless: all 6 figure hashes match the committed post-T4 baseline byte-for-byte, Streamlit headless boot returns HTTP 200, and the 11 smoke tests all pass.

## Findings

### A. Test integrity

- `git diff --name-only 68a08b9..3455fef -- tests/` → two files appear: `tests/test_sensor_assignment_manager.py` (Argyll's T5, predates Dreadnought) and `tests/test_tab_modules_smoke.py` (Dreadnought's own). No pre-existing test was modified.
- `git diff --name-only 555e618..3455fef -- tests/` (scope strictly T7) → only `tests/test_tab_modules_smoke.py`. Sentinel/Argyll/Diligent tests all untouched. PASS.
- `git diff a477b82..9c3ec90 -- tests/test_tab_modules_smoke.py` → empty. Smoke tests were committed in the red phase and not modified when Dreadnought wrote the implementation. This is genuine TDD, not adjust-test-until-green.
- `pytest tests/test_tab_modules_smoke.py -v` on HEAD: **11 passed in 3.37 s**. All green:
  - `test_tab_module_exposes_render[tabs.temperature_profile]` through `[tabs.curve_comparison]` — 8 parametrised cases PASS.
  - `test_sidebar_module_exposes_render` PASS.
  - `test_session_state_module_exposes_init` PASS.
  - `test_sensor_naming_module_exposes_helpers` PASS.
- **Finding: PASS.** No pre-existing test modified; red-phase stable; all smoke tests green.

### B. DRY / Mission metric

- `grep -rn 'st\.tabs' app.py tabs/ sidebar.py` → exactly **2 matches**:
  - `app.py:101` → `tab_objects = st.tabs(labels)` — the main dispatcher, now a single parameterised builder over `TAB_SPECS` (app.py:61-69) with conditional append of the Curve Comparison tab (app.py:97-98). The mission target of collapsing the 7-tab/8-tab duplication at old app.py:573-592 into 1 builder is met.
  - `tabs/curve_comparison.py:92` → `comp_tab1..5 = st.tabs([...])` — the 5 inner sub-views of the Curve Comparison tab.
- **Pre-existing proof for the second match**: `git show 555e618:app.py | sed -n '1110,1130p'` yields:
  ```
  comp_tab1, comp_tab2, comp_tab3, comp_tab4, comp_tab5 = st.tabs([
      "Temperature Profiles", "Zone Analysis", "S-Curve Analysis",
      "Heating Rates", "Quality Metrics"
  ])
  ```
  and the T7 version at `tabs/curve_comparison.py:92-95` is:
  ```
  comp_tab1, comp_tab2, comp_tab3, comp_tab4, comp_tab5 = st.tabs([
      "Temperature Profiles", "Zone Analysis", "S-Curve Analysis",
      "Heating Rates", "Quality Metrics"
  ])
  ```
  Byte-identical. The 5 labels and the unpacking signature match verbatim. Nothing to relitigate per Standing Orders — only confirming the claim, which holds.
- `wc -l app.py` → **112**. Mission target was <400. Under-run by 288 lines; 88% of target budget unused.
- New module sizes (per `wc -l`): `sidebar.py` 408, `tabs/curve_comparison.py` 306, `tabs/recommendations.py` 109, `sensor_naming.py` 95, `tabs/quality_metrics.py` 87, `tabs/heating_analysis.py` 85, `tabs/temperature_profile.py` 82, `tabs/s_curve_analysis.py` 64, `tabs/zone_analysis.py` 59, `tabs/bakeout_analysis.py` 34, `session_state.py` 30, `tabs/__init__.py` 6. Total including app.py: 1477 lines (vs. original monolith 1337). Net +140 lines is the cost of module boundaries and per-file imports — noted in DR as ~194 and justified; my recount comes in slightly lower but the order of magnitude is right.
- **Finding: PASS.** Mission metric met; second `st.tabs` call verified pre-existing byte-identically; under-runs the <400-line target by ~288 lines.

### C. Session-state preservation

Pre-T7 `st.session_state.*` key inventory (from `git show 555e618:app.py | grep -oE "session_state\.[a-zA-Z_][a-zA-Z0-9_]+" | sort -u`):
```
all_curves, analyzer, current_curve_index, current_file, data,
files, global_curve_index, loader, metadata, s_curve_analyzer
```
= **10 keys**. Matches Dreadnought's `session_state_keys_preserved` list exactly.

Post-T7 inventory (`grep` across `app.py sidebar.py session_state.py sensor_naming.py tabs/*.py`):
```
all_curves, analyzer, current_curve_index, current_file, data,
files, global_curve_index, loader, metadata, s_curve_analyzer,
product_type, show_zones, smooth_data
```
= **13 keys**. Delta vs pre-T7 = {`product_type`, `show_zones`, `smooth_data`}. Exactly the 3 approved deviations. **No fourth new key.**

Note on `s_curve_analyzer`: it is NOT seeded in `session_state.py:initialize_session_state()` — it's assigned lazily in `sidebar.py` at lines 93, 146, 216, 317, 384 when a curve is loaded/switched, mirroring pre-T7 behaviour (old app.py:241, 294, 364, 465, 532 — same 5 assignment sites). Tab modules `tabs/s_curve_analysis.py:12`, `tabs/bakeout_analysis.py:14`, and `tabs/recommendations.py:17` read `st.session_state.s_curve_analyzer` assuming it exists, which is guaranteed by the `st.session_state.data is None` guard at `app.py:72` — tab rendering only runs after the sidebar has populated data+loader+s_curve_analyzer atomically. Behaviour-equivalent to pre-T7, not a regression.

Widget `key=` verbatim check:
- Pre-T7 (`git show 555e618:app.py | grep key=`): 6 unique keys — `temp_profile_show_all`, `temp_profile_sensor_select`, `core_override_{idx}`, `surface_override_{idx}`, `remove_{filename}`, `curve_check_{global_idx}`.
- Post-T7 (`grep key= app.py sidebar.py tabs/`): same 6 keys, verbatim:
  - `temp_profile_show_all` → `tabs/temperature_profile.py:14`
  - `temp_profile_sensor_select` → `tabs/temperature_profile.py:46`
  - `core_override_{...current_curve_index}` → `sidebar.py:236`
  - `surface_override_{...current_curve_index}` → `sidebar.py:246`
  - `remove_{filename}` → `sidebar.py:354`
  - `curve_check_{global_idx}` → `tabs/curve_comparison.py:53`
- **Finding: PASS.** 10 pre-existing keys preserved, exactly 3 approved additive keys added, 6 widget keys byte-identical. Streamlit's widget state machine contract is intact.

### D. Figure-hash parity

- Ran `python .nelson/missions/2026-04-23_071618_4b7f0acb/baseline/capture_baseline.py` on HEAD (3455fef, effectively 9c3ec90 code since 3455fef is a docs-only commit).
- Re-captured hashes (saved at `.nelson/.../red-cell/figure-hashes-3455fef.json`):
  - `ProbeData_100098DE_2025-05-30 13_51_07.csv`: `d76ddc66f5d4256d5399d3fe8fdc89015a8c133e57c9d7671ffd3efc48df1f51`
  - `ProbeData_1000BA3C_2025-05-30 09_46_16.csv`: `92f6460536feb17af6bfada040700b4d25fececc9504eda75f39a5cc54368f3c`
  - `ProbeData_1000BA3C_2025-05-30 17_59_37.csv` curve_0: `92f6460536feb17af6bfada040700b4d25fececc9504eda75f39a5cc54368f3c`
  - `ProbeData_1000BA3C_2025-05-30 17_59_37.csv` curve_1: `30d5fe9461a41c0e5b34a095bfa9c70ece314d8dc7bb55135df1f6e022e9cead`
  - `ProbeData_1000BA3C_2025-05-30 17_59_37.csv` curve_2: `3f6c5c081ee8f86ddcd9b5dd0fb630f5dccfe9089f11a6c0adb896d4666e7e47`
  - `ProbeData_1000F3C1_2025-05-23 09_11_59.csv`: `5ef719dce945dd337abfc7bea27a1949007f1725a9d820e6458ffc91ef0f90fa`
- Committed post-T4 baseline (from `git show 9c82eba:.nelson/.../figure-hashes.json`):
  - Same 6 full-length hashes, character-for-character.
- **6/6 byte-identical match.** Only `created_at` differs between the files — the working-tree re-capture says `2026-04-23T10:05:20.851025+00:00`, the committed baseline was written `2026-04-23T09:28:03.751113+00:00`. After verification I restored the committed file via `git restore`; working tree is clean on that path.
- Unlike the T4 review, I did NOT need to swap in pre-T7 loader.py for isolation — since the refactor touches only UI/wiring (tabs, sidebar, session_state), and the figure-hash capture loads CSVs and calls `ThermalPlotter.plot_temperature_profile()` directly without going through Streamlit, the hashes would only change if the data pipeline (loader/analysers) were altered. It wasn't: Dreadnought's commit lists no changes under `src/`. Confirmed via `git show --stat 9c3ec90`: all changed paths are `app.py`, `sidebar.py`, `session_state.py`, `sensor_naming.py`, `tabs/*`, `tests/test_tab_modules_smoke.py`. Zero `src/` touches.
- **Finding: PASS.** Figure parity confirmed without needing loader isolation.

### E. Streamlit smoke boot

- Launched `streamlit run app.py --server.headless true --server.port 8597 --browser.gatherUsageStats false` in background.
- Waited 6 s, `curl` to `http://localhost:8597/` → **HTTP 200**. Response body received (non-empty HTML).
- Streamlit log shows clean startup: "You can now view your Streamlit app in your browser. Local URL: http://localhost:8597". No import errors, no ModuleNotFoundError, no AttributeError during module loading.
- Process cleanly killed afterward. I also noticed an orphan Streamlit process (PID 10404, started 19:55:09) likely left over from Dreadnought's earlier boot test on :8598 — killed as part of cleanup to keep the environment tidy; no other ports occupied.
- **UI walkthrough with CSV uploads NOT performed.** Driving `st.file_uploader` headlessly is impractical without a browser-automation harness; per the briefing this was explicitly marked "optional; note as 'not performed' rather than silently skipping". I am noting it here: a full manual walkthrough of the 7-tab single-curve path (F3C1) and 8-tab multi-curve path (BA3C 17_59_37) is recommended to catch any runtime errors that only surface with loaded data, but is not within this red-cell's verifiable scope. Dreadnought's DR claims such a walkthrough was done; I am not in a position to falsify that claim.
- **Finding: PASS (headless boot).** Manual UI walkthrough not performed — flagged as residual risk, not a blocker.

### F. TDD audit

Commit timestamps (AuthorDate, +1000):
- `a477b82` — 2026-04-23 **19:49:19** — "test: smoke tests for decomposed app.py modules"
- `9c3ec90` — 2026-04-23 **19:58:58** — "refactor(ui): decompose app.py into tab modules"
- `3455fef` — 2026-04-23 **20:00:07** — "docs(mission): HMS Dreadnought damage report for T7"

Test commit precedes refactor by 9 min 39 s. Damage-report commit trails by another 1 min 9 s. Correct order.

Red-phase stability: `git diff a477b82..9c3ec90 -- tests/test_tab_modules_smoke.py` is empty, so the test was genuinely failing at a477b82 (no modules existed) and genuinely passing at 9c3ec90 without any test-file adjustment. Resolute-grade TDD.

- **Finding: PASS.** Test-first confirmed; red-phase commit stable.

## Recommendation to Admiral

**Approve T7 as-is.** This is the cleanest refactor of the mission so far. Dreadnought:
- Stayed strictly in-scope (zero `src/` touches).
- Preserved every pre-existing session-state key and widget `key=` byte-for-byte.
- Added only the 3 pre-approved state keys — no scope creep.
- Hit the <400-line target with 288 lines to spare (app.py at 112).
- Delivered test-first, with a stable red-phase commit.
- Passes the headless Streamlit boot cleanly.
- Reproduces byte-identical figure hashes against the committed post-T4 baseline.

Residual risks worth flagging but **not** T7 blockers:
1. **Manual UI walkthrough of all 4 fixtures not performed by red-cell.** Dreadnought's DR claims it was done in her own verification. Recommend an operator spot-check of: F3C1 (single curve, 7 tabs), BA3C 17_59_37 (3 curves, 8 tabs including Curve Comparison). Any KeyError from a lazily-initialised `s_curve_analyzer` would surface there. Lower risk since the tab-render gate at `app.py:72` (`if st.session_state.data is None`) is respected before any tab reads state, and the sidebar assigns `s_curve_analyzer` atomically with `data`/`loader`/`analyzer` — but a live human click-through is cheap insurance.
2. **`recommendations` tab now recomputes `s_curve_report` and `ZoneAnalyzer` locally** (per Dreadnought's own DR handoff note). The old monolith reused locals from tabs 2 and 3. Behaviour-equivalent but computationally redundant — not a regression, not a functional issue, but if the figures are expensive you might see a small per-render cost increase on that one tab. Acceptable for the refactor and outside T7 scope to fix.

Artifacts I produced under `.nelson/missions/2026-04-23_071618_4b7f0acb/red-cell/`:
- `hms-scrutineer-t7-review.md` (this file)
- `figure-hashes-3455fef.json` (my re-capture for the parity check — byte-identical to committed post-T4 baseline except `created_at`)

Working-tree hygiene at sign-off: `git status src/ tests/ app.py sidebar.py session_state.py sensor_naming.py tabs/` → clean (only pycache untracked). Zero production-code modifications from this red-cell review, unlike T4 I did not need to swap any source files for isolation.
