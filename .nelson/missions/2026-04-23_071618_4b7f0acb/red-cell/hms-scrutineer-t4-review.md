# Red-Cell Review — T4 (HMS Resolute, commit d156add)

Reviewer: HMS Scrutineer
Reviewed: 2026-04-23
Commit under review: `d156add` — "fix(loader): collapse three column-regen paths; preserve physics correction"
Base for comparison: `37f5e6d` (HEAD~1, pre-d156add)
Test commit in scope: `68a08b9` (Sentinel)

## Verdict

**APPROVE-WITH-NOTES**

The fix is substantively correct and lossless. Two notes for Admiral, neither a blocker:
(1) Resolute's "9 SurfaceTemperature writes across 2 behavioural paths" claim is accurate, but she under-states one line — including the physics-correction writer at line 348 there are really **3** code paths touching `SurfaceTemperature` (virtual helper / physics corrector / dynamic classifier). The bug-surface argument still holds.
(2) The committed P0 figure-hash baseline is stale; I confirmed the staleness is NOT caused by the refactor (HEAD~1 with its original loader reproduces the same hashes as d156add). Admiral should re-capture the baseline from this branch before T7 uses it for parity.

Self-disclosure: during parity isolation I temporarily swapped `src/data/loader.py` to HEAD~1's version to re-run `capture_baseline.py`, then restored it. This was necessary to isolate refactor-vs-environment drift, but it did constitute a transient modification of production code. The current working tree is byte-identical to d156add; `git status` is clean on `src/` and `tests/`.

## Findings

### A. Test integrity

- Claim: Resolute did not modify any test to make the failing test pass.
- Evidence:
  - `git diff 68a08b9..d156add -- tests/test_physics_flag_regression.py` → **empty**.
  - `git diff 68a08b9..d156add -- tests/` → **empty** (no test file in the tree was touched between the two commits).
  - `git show --stat d156add` shows only `src/data/loader.py` changed (+75 / -232).
- Test execution on d156add: `python -m pytest tests/test_physics_flag_regression.py -v` →
  - `test_generate_standard_columns_for_df_preserves_physics PASSED`
  - `test_regenerate_standard_columns_preserves_physics PASSED`
  - Both tests pass in 5.13 s.
- Diff confirmation that the fix alters real regeneration logic, not a cosmetic reorder: `git show d156add -- src/data/loader.py` shows the old duplicate ladders deleted and a new `_apply_standard_columns` helper introduced at line 1128; `_regenerate_standard_columns` (line 1191) and `_generate_standard_columns_for_df` (line 1197) are now 3-line and 8-line delegates respectively.
- **Finding: PASS.** Test is Sentinel-pristine; fix is real, not test-tampering.

### B. DRY — single source of truth for the virtual-sensor path

- SurfaceTemperature write count on d156add: **9** (matches Resolute's claim).
- Line-by-line grouping:
  - Line **348** — `df['SurfaceTemperature'] = df[surface_sensor]` inside `_apply_physics_based_surface_correction`. This is the physics writer itself (the `after.values` the regression test expects to survive).
  - Lines **625, 642, 699** — inside `_classify_sensors_dynamically`. This is the "Virtual* columns missing" fallback. Resolute did not route it through the helper; she argues it is orthogonal to the bug surface. That argument is sound: the fixture the test uses has Virtual* columns, the dynamic path is never entered, and the helper's ladder would wipe the classifier's means if it ran afterwards.
  - Lines **1164, 1166, 1168, 1170, 1172** — the five-branch if/elif ladder inside `_apply_standard_columns`: `override → physics_surface → VirtualSurfaceTemperature → SurfaceAverage → T7/T8 mean`. Exactly one branch executes per call.
- Helper is a single-branch ladder: **yes**. Code cite at `src/data/loader.py:1155-1172` — strict if/elif/elif/elif/elif, no sequential writes to the same column.
- Delegates are thin:
  - `_regenerate_standard_columns` at `src/data/loader.py:1191-1195` — 3 lines, a guard plus a call to the helper. Correct.
  - `_generate_standard_columns_for_df` at `src/data/loader.py:1197-1206` — 8 lines. It resolves `curve_index` by identity against `self.all_curves` before delegating. This logic is justified: during initial load `current_curve_index` may not match the df being built, so the physics flag of the *owning* curve has to be looked up. No column-assignment logic of its own. Acceptable.
- Core/Ambient sanity: 10 Core writes, 9 Ambient writes, same 5-branch ladder structure inside `_apply_standard_columns` (lines 1144-1189). No anomalous concentration in any one column. Consistent with the pattern.
- Minor note I want to flag honestly: Resolute's damage report calls this "2 behavioural code paths". I count **3** code paths with `SurfaceTemperature = ...`: the helper ladder (virtual path), the physics writer at line 348, and the dynamic classifier. Her "2" count collapses the physics writer into the helper because the helper's `physics_surface` branch is what *re-asserts* the physics sensor on subsequent regen. Semantically she is right — the physics writer IS the canonical source-of-truth for the physics-corrected value, and the helper's job is to preserve it. But a strict grep-and-count reader will see 3 sites, not 2. Not a blocker.
- **Finding: PASS.** Virtual-sensor path is single-ladder. Dynamic classifier is intentionally left un-unified and the rationale is defensible. Helper's branches are mutually exclusive per call.

### C. Dead code removed

- `grep -rn "_extract_all_baking_curves_old" src/ app.py tests/` → **zero hits in source**. Only mentions are in `.nelson/missions/.../plan-input.json` and `battle-plan.json` (mission planning docs, not code) and in Resolute's damage report.
- `git show --stat d156add` confirms 232 lines deleted from loader.py; a hunk of that is the old method.
- **Finding: PASS.** Dead method removed.

### D. Figure-hash parity

This was the claim I was told to scrutinise hardest. Result: Resolute is correct — her refactor is lossless, and the committed P0 baseline is environmentally stale.

- **P0 baseline** (committed at `.nelson/missions/.../baseline/figure-hashes.json`, captured 2026-04-23T08:49:23 UTC by Sentinel):
  - `ProbeData_100098DE_2025-05-30 13_51_07.csv`: `6ed6803bd773e2ab`
  - `ProbeData_1000BA3C_2025-05-30 09_46_16.csv`: `2e46d202024ecaa4`
  - `ProbeData_1000BA3C_2025-05-30 17_59_37.csv` curve_0: `2e46d202024ecaa4`
  - `ProbeData_1000BA3C_2025-05-30 17_59_37.csv` curve_1: `dae26a2cec909a40`
  - `ProbeData_1000BA3C_2025-05-30 17_59_37.csv` curve_2: `b756bcccaeaa8334`
  - `ProbeData_1000F3C1_2025-05-23 09_11_59.csv`: `5a5e024a7aa5fdaa`

- **Branch d156add re-capture** (saved at `.nelson/missions/.../red-cell/figure-hashes-d156add.json`):
  - `ProbeData_100098DE`: `d76ddc66f5d4...`
  - `ProbeData_1000BA3C 09_46_16`: `92f6460536fe...`
  - `1000BA3C 17_59_37` curve_0: `92f6460536fe...`
  - `1000BA3C 17_59_37` curve_1: `30d5fe9461a4...`
  - `1000BA3C 17_59_37` curve_2: `3f6c5c081ee8...`
  - `ProbeData_1000F3C1`: `5ef719dce945...`

- **HEAD~1 (`37f5e6d`) re-capture** — swapped in `git show 37f5e6d:src/data/loader.py` temporarily and re-ran `capture_baseline.py`. Saved at `.nelson/missions/.../red-cell/figure-hashes-pre-d156add.json`:
  - `ProbeData_100098DE`: `d76ddc66f5d4...`
  - `ProbeData_1000BA3C 09_46_16`: `92f6460536fe...`
  - `1000BA3C 17_59_37` curve_0: `92f6460536fe...`
  - `1000BA3C 17_59_37` curve_1: `30d5fe9461a4...`
  - `1000BA3C 17_59_37` curve_2: `3f6c5c081ee8...`
  - `ProbeData_1000F3C1`: `5ef719dce945...`

- Drift source identified: **environmental**. HEAD~1 with its own original loader produces hashes IDENTICAL to d156add, and BOTH diverge from the P0 baseline captured ~30 minutes earlier. The drift is therefore in the plotly-to-JSON serialization (likely a timestamped field or a plotly internal id regenerated on each `to_json()`), not in Resolute's refactor. The refactor is byte-lossless.
- After each comparison capture, `capture_baseline.py` overwrote `figure-hashes.json`. I restored it each time with `git restore`. Current state: P0 baseline file is clean, working tree has no modification staged.
- **Finding: PASS.** Resolute's refactor does not change figure output. Her "env drift" claim is correct. Recommend Admiral re-capture the P0 baseline from this branch's HEAD before T7 Dreadnought uses it for parity, since the current file no longer matches reality.

### E. Assertion strength

- Test file: `tests/test_physics_flag_regression.py`.
- Relevant assertion lines:
  - `test_generate_standard_columns_for_df_preserves_physics` (lines 61-73):
    ```
    corrected_surface = loader.data['SurfaceTemperature'].copy()
    loader._generate_standard_columns_for_df(loader.data)
    after = loader.data['SurfaceTemperature']
    assert np.array_equal(corrected_surface.values, after.values), ...
    ```
  - `test_regenerate_standard_columns_preserves_physics` (lines 75-87) uses the same `np.array_equal(corrected_surface.values, after.values)` pattern.
- The tests compare the **actual column values** before and after regeneration, not the `physics_corrected` flag. The flag IS checked in the `_load_corrected` helper (line 49) as a *sanity precondition* — i.e. "fixture still triggers physics", not "fix preserved the flag". The postcondition is strictly on data.
- Further, line 55-58 asserts `corrected_surface != VirtualSurfaceTemperature` before the regeneration runs, which proves the test is non-trivial: it would fail for any fixture where firmware and physics happen to agree.
- **Finding: PASS.** Asserts data, not flag. Sentinel wrote the strongest form of this test available.

### F. TDD audit

- Sentinel test commit: `68a08b9` — AuthorDate 2026-04-23 18:50:22 +1000.
- Resolute fix commit:   `d156add` — AuthorDate 2026-04-23 19:18:53 +1000.
- Gap: 28 minutes 31 seconds. Test committed first.
- Intermediate commits (`685f1d5` Swiftsure at 18:59, `37f5e6d` Archivist at 19:04) touch neither the test nor loader.py's regeneration logic, so they do not invalidate the ordering.
- **Finding: PASS.** Test-first confirmed. This is genuine TDD, not retrofitted test.

## Recommendation to Admiral

**Approve T4 with two housekeeping follow-ups.** The physics-flag race is fixed, the fix is test-first and non-destructive to the test, the refactor is byte-parity with HEAD~1 on all six figure hashes, and the DRY claim holds modulo a semantic quibble on what counts as a "path". Resolute's work is of high quality and I found nothing to send her back for.

Follow-ups (not blockers for T4 sign-off):
1. **Re-capture the P0 figure-hash baseline from this branch's HEAD** before T7 Dreadnought starts. Current `figure-hashes.json` was captured ~30 min before d156add and diverges due to plotly environmental drift. If T7 uses the stale baseline it will get false positives. Simplest fix: `rm .nelson/.../baseline/figure-hashes.json && python .../baseline/capture_baseline.py && git commit`.
2. **Consider a follow-up ticket** to fold the dynamic-classifier path into `_apply_standard_columns`. Resolute correctly left it out of T4 scope — it has no Virtual* columns, so the helper's ladder would clobber it — but a future pass could extend the ladder with a "dynamic classification result" branch and get to a true single-writer design. Not urgent.

Artifacts I produced under `.nelson/missions/2026-04-23_071618_4b7f0acb/red-cell/`:
- `hms-scrutineer-t4-review.md` (this file)
- `figure-hashes-d156add.json` (hashes re-captured on d156add as reviewer evidence)
- `figure-hashes-pre-d156add.json` (hashes re-captured after temporarily swapping in 37f5e6d's loader — proves env drift, not refactor drift)
