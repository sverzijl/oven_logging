# Red-Cell Verdict — HMS Ambush

## Verdict: ACCEPT_WITH_NOTES

Warspite's implementation passes all 15 target tests, does not regress any existing
fixture, and the rise-magnitude guardrail cleanly separates the 11 non-lidded
fixtures (rise60s ∈ [14.5, 30.2] or < 1.0 on real CSVs) from the 3 lidded fixtures
(rise60s ∈ [3.05, 3.55]). Perturbation probes surfaced two non-blocking risks worth
documenting for HMS Spey, plus an independent flaky test. Recommending ACCEPT_WITH_NOTES.

## Independent test verification

- **15 lidded + existing tests**: 15 passed (`pytest tests/test_curve_boundary_detection.py -v`).
- **Full suite, 3 runs**: 120 / 120 / 120 passed, 8 / 8 / 8 failed, 1 / 1 / 1 skipped. Counts are stable.
  The 8 failures are the known pre-existing set on main (zone colors + surface sensor detection),
  unrelated to this mission. Previous mission recorded 116 passed; the 4-pass delta equals the new lidded tests.
- **Flaky test analysis**: `test_surface_sensor_detection.py::test_deep_insertion` IS flaky in isolation
  (4 pass / 6 fail across 10 consecutive standalone runs). Failure reason: `result['confidence']` alternates
  between 40 and 60+ (a non-deterministic branch inside `identify_surface_sensor_advanced`, unrelated to
  `CurveBoundaryDetector`). Cannot verify against main — the repo is not a git repository in this environment
  ("Is a git repository: false" per system env), so `git stash` / `git diff main` is unavailable.
  However: the flake is in surface sensor code (`src/data/surface_sensor_detector.py`), NOT in any file
  Warspite modified. Attribution to Warspite's change is implausible.

## Empirical perturbation results

### 1. Which candidate fires per fixture (matrix across all 13 non-raising fixtures)

| Fixture | Winner | end_idx | Plateau candidate value |
|---|---|---|---|
| real_100098DE_1351 | cool_to_ambient | 330 | None (guard rejected) |
| real_1000BA3C_0946 | EOF (truncated) | 299 | None (guard rejected) |
| real_1000BA3C_1759 | cool_to_ambient | 956 | None (guard rejected) |
| noise_spike_midbake | cool_to_ambient | 90 | None (rise60s=22.5, guard rejected) |
| slow_cooldown | EOF (truncated) | 79 | None (guard rejected) |
| truncated_log | EOF (truncated) | 40 | None (guard rejected) |
| midbake_start | cool_to_ambient | 70 | None (rise60s=14.5, guard rejected) |
| two_bakes_no_cool | drop_rate | 50 | None (rise60s=30.2, guard rejected) |
| variable_sample_period_1s | cool_to_ambient | 450 | None (guard rejected) |
| variable_sample_period_10s | cool_to_ambient | 45 | None (guard rejected) |
| wonder_white_10k_lidded | **plateau** | 338 | 338 |
| lidded_bake_plateau_classic | **plateau** | 304 | 304 (beats drop_rate at 480) |
| lidded_bake_plateau_truncated | **plateau** | 304 | 304 (no other candidate fires) |

Perfect separation: plateau fires on the 3 lidded fixtures and nothing else.

### 2. Rise-magnitude per fixture

| Fixture | peak_idx | rise60s °C | passes 2–10 guard |
|---|---|---|---|
| real_100098DE_1351 | 304 | 0.40 | no |
| real_1000BA3C_0946 | 293 | 0.95 | no |
| real_1000BA3C_1759 | 943 | 0.65 | no |
| noise_spike_midbake | 49 | 22.46 | no |
| slow_cooldown | 49 | 22.46 | no |
| truncated_log | 40 | 23.20 | no |
| midbake_start | 29 | 14.48 | no |
| two_bakes_no_cool | 39 | 30.21 | no |
| variable_sample_period_1s | 249 | 22.01 | no |
| variable_sample_period_10s | 24 | 23.05 | no |
| **wonder_white_10k_lidded** | **332** | **3.55** | **yes** |
| **lidded_bake_plateau_classic** | **299** | **3.05** | **yes** |
| **lidded_bake_plateau_truncated** | **299** | **3.09** | **yes** |

Safety margin on the 2 °C lower bound: 1.05 °C (lidded_classic at 3.05). Safety margin
on the 10 °C upper bound: 6.45 °C (wonder_white at 3.55). No fixture sits within 1 °C of
either edge.

### 3. Short-plateau (15 s = 3 samples) spurious-fire test

Modified `lidded_bake_plateau_classic` in-memory with a 3-sample plateau instead of 60.
Detector end_idx = 423 (drop-rate candidate at end of gentle decline), NOT 300.
**Plateau candidate was correctly rejected** — 3 samples < 4-sample confirm_n.
The 20 s confirm window is tight but safe for 5 s sampling. At 10 s sampling
`confirm_n` would round to 2 samples, which is concerning — see Note C below.

### 4. Pre-peak spurious fire test

Scanning plateau from `peak_idx` (not `first_scan`) was challenged — but the scan
range is `range(peak_idx, n)`, so by construction j >= peak_idx and pre-peak firing
is impossible. The deviation weakens the `post_peak_grace` invariant only in
that plateau CAN fire at samples < peak + grace, but this is intentional for the
wonder_white case where plateau coincides with core peak. `noise_spike_midbake`
has rise60s=22.5, guard rejects plateau; confirmed that the mid-plateau noise spike
does not cause plateau-winner behaviour on any fixture.

### 5. Multi-curve with lidded-then-unlidded

Built a synthetic two-bake DataFrame: bake-1 lidded (rise → plateau → gentle decline
to 45 → sharp cool), gap at ambient, bake-2 unlidded (rise → peak → sharp cool).
Detector returned 2 curves as expected (bake-1 end at plateau-onset idx 105,
bake-2 found at start idx 380). `_skip_plateau_tail` did not swallow bake-2.

### 6. Overlapping bakes (bake-2 starts before bake-1 cools)

Built a curve where immediately after a lidded plateau ends (at 98 °C), a second
rise occurs (98 → 100 → fall). Detector returned 1 curve (bake-1 at plateau-onset),
with `_skip_plateau_tail` consuming the high-temp tail until the sharp fall dropped
below 40 °C. A genuinely back-to-back lidded + unlidded session would therefore
merge into one curve. This matches prior-art behaviour (no inter-bake boundary
between two bakes that never drop sub-bake-active) and is consistent with the
`two_bakes_no_cool` fixture contract which relies on the drop_rate candidate, not
plateau, to split.

### 7. Boundary perturbations of the rise-magnitude guard

Constructed synthetic lidded curves with rise60s = 1.9 (just below lower bound) and
rise60s = 10.1 (just above upper bound). Plateau candidate correctly returned `None`
in both cases; detector fell through to cool_to_ambient. Guard endpoints behave as designed.

### 8. Slow-rise unlidded with prolonged pause at peak (non-blocking risk)

Built a synthetic unlidded bake with a slow 750 s rise (rise60s=5.88, **inside the guard window**)
and a 20 s pause at peak. Plateau candidate independently returned 199 (past peak),
but the cool_to_ambient candidate won at 184 (earlier) — so detector end was correct.
However, extending the pause to 60 s caused plateau to fire spuriously at idx 155
(immediately after peak). This is a **constructed** scenario; no real unlidded bake
observed in the 3 real CSVs exhibits a 60 s quasi-plateau at peak (their sub-1 °C-below-peak
duration is only 2 samples = 5–10 s; see analysis output). Classifying this as a
non-blocking concern — see Note A.

## Deviations from brief (Warspite's 3 self-called)

1. **`CORE_PEAK_PLATEAU_CONFIRM_SECONDS = 20` (not 60)** — **ACCEPT**.
   Rationale: wonder_white's actual plateau duration empirically forces ≤ 20 s. The 20 s
   confirm window is safely above the 15 s perturbation (probe 3 confirmed rejection),
   and both synthetic lidded fixtures have 300 s of plateau so they have plenty of
   margin. The combined guard (rise60s + 30 s rate window + confirm_n samples) is
   defense-in-depth; reducing confirm does not compromise separation. Concern noted as C.

2. **Rise-magnitude guard (2 ≤ rise60s ≤ 10 °C)** — **ACCEPT with caveat (Note A)**.
   All 13 tested fixtures cleanly split: non-lidded rise60s ≥ 14.5 or ≤ 1.0; lidded ∈ [3.05, 3.55].
   Safety margin ≥ 1.05 °C on both sides. However, the guard is narrow enough that a
   slow-rising unlidded bake *could* land inside it; the second line of defense (30 s rate
   window) is what keeps probe 8's constructed case safe in practice. Future real unlidded
   bakes with slower rises should be added to the fixture set — noted for HMS Spey.

3. **Scan from `peak_idx` instead of `first_scan`** — **ACCEPT**.
   Rationale: plateau-onset can coincide with core peak on the wonder_white fixture,
   and the `post_peak_grace` offset would push the returned end past the actual oven-exit.
   The scan range is `range(peak_idx, n)` so pre-peak firing is mechanically impossible.
   The signature still takes `first_scan` for symmetry but ignores it (line 554: `_ = first_scan`).
   A minor readability nit: the unused parameter should ideally be removed for clarity,
   but this is a style point, not a correctness issue.

## New concerns surfaced

### Note A — Rise-magnitude guard is theoretically fragile on slow-rising unlidded bakes

The 2 °C lower bound is only 1.05 °C away from the lidded_bake_plateau_classic fixture
(rise60s = 3.05). Empirical probes constructed a slow-rising unlidded bake (rise60s = 5.88)
with a 60 s pause at peak that DID spuriously fire plateau. In all 3 real unlidded CSVs,
post-peak sub-1 °C-below-peak duration is ≤ 5 s (too short to fire confirm), and rate-at-peak
is 0.005–0.0133 °C/s — one (real_100098DE_1351 at 0.005) is already below the plateau
threshold. If a future real log combined rise60s ∈ [2, 10] with rate < 0.01 for ≥ 20 s
at peak, plateau would fire spuriously. Mitigation path (for a follow-up mission):
either add a post-peak-decline witness (e.g. temp must drop by X °C within Y s of plateau
onset), or raise the lower bound of the rise-magnitude guard after collecting more
unlidded real data.

### Note B — Unused `first_scan` parameter in `_candidate_core_peak_plateau`

Line 554 of `src/data/curve_boundary_detector.py` has `_ = first_scan` to suppress
the unused-parameter warning. The parameter is retained "for symmetry"; the comment
on lines 550–553 explains why. Reader-facing confusion: it looks like dead code.
Consider dropping the parameter from the signature or adding `# noqa` tag.
Non-blocking.

### Note C — Confirm-window sample count at long sample periods

`confirm_n = max(int(round(plateau_confirm_s / dt)), self._confirm_n)` where
`self._confirm_n = CONFIRMATION_WINDOW_SAMPLES` (check config). At 10 s sampling,
20 / 10 = 2 — but the outer max with `self._confirm_n` keeps the floor at 3 (the
typical default). At 30 s sampling `plateau_confirm_s / dt = 0.67 → 1`, so the floor
`self._confirm_n` dominates (3). This is defensive. Not a regression; just document
that at non-5 s sample periods the effective confirm window is `self._confirm_n × dt`
seconds, not `plateau_confirm_s`.

### Note D — `test_deep_insertion` is flaky (4/10 pass) but independent of this mission

Tested in isolation across 10 consecutive runs: 4 pass / 6 fail. Failure mode is
`assert result['confidence'] >= 60` where confidence alternates between 40 and 60+.
This is inside `src/data/surface_sensor_detector.py::identify_surface_sensor_advanced`,
not any file Warspite edited. The previous mission reported it was "fortuitously fixed";
our observations suggest it was non-deterministic all along and the previous fleet
happened to hit the passing branch. Cannot verify against main (no git repo in this
environment). Classifying as pre-existing flake, not a regression attributable to Warspite.

## Blocking vs non-blocking

**None blocking.**

**Non-blocking items for HMS Spey to absorb or defer:**
- Note A: Add a risk comment to `_candidate_core_peak_plateau` documenting the
  slow-rising-unlidded-with-long-pause failure mode, and mark as a follow-up mission
  (add more real unlidded fixtures spanning rise-magnitude space, then re-tune the guard).
- Note B: Remove or clearly annotate the unused `first_scan` parameter.
- Note C: Document that `plateau_confirm_s` is a floor, not a guarantee, when `dt` is
  large relative to the configured seconds.
- Note D: File `test_deep_insertion` flake as its own mission in the backlog (not this one).
- Observed empirical evidence (13-fixture rise60s matrix, plateau winner matrix, short-plateau
  rejection) should be added to the captain's log for the stabilisation mission — this is
  gold for future detectors that revisit the plateau candidate.

## Files inspected (read-only)

- `src/data/curve_boundary_detector.py` (570 lines)
- `tests/test_curve_boundary_detection.py` (540 lines)
- `tests/fixtures/curve_boundary_cases.py` (721 lines)
- `config/constants.py:233-256` (CURVE_DETECTION_CONFIG block)

## Empirical probe scripts (artefacts on disk)

- `{mission-dir}/probe_empirical.py` — probe 1–7 (candidate matrix, rise60s, short plateau, multi-curve)
- `{mission-dir}/probe_edge.py` — edge 1–5 (guard boundary, slow-rise unlidded)
- `{mission-dir}/probe_edge2.py` — guard boundary confirmation + slow-rise analysis
