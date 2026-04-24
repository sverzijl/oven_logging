# Red-Cell Verdict — HMS Artful

## Verdict: ACCEPT_WITH_NOTES

The classifier is physically sound, the gate is well-calibrated against
realistic-noise perturbations of the real CSVs, and all 21 dedicated
tests pass stably. Several of Iron Duke's self-called deviations hold up
under scrutiny. Two findings warrant polish by HMS Lancaster (neither
blocks the mission's core contract — the override fires correctly,
writes to `curve_sensor_assignments['core']`, and propagates to
`loader.get_core_sensor()`). Details below.

## Independent test verification

- **21 dedicated tests**: 21 / 21 PASS.
- **Full suite 3 runs**:
  - Run 1: 126 passed / 8 failed / 1 skipped (80.75s)
  - Run 2: 126 passed / 8 failed / 1 skipped (74.71s)
  - Run 3: 126 passed / 8 failed / 1 skipped (73.26s)
- **Flaky test analysis**: **No flaky tests detected.** Failures are
  STABLE across all 3 runs — identical 8 failures each time:
  - `test_curve_comparison_integration.py::test_zone_color_consistency`
  - `test_internal_sensor_filtering.py::test_realistic_baking_profile`
  - `test_surface_sensor_detection.py::test_shallow_insertion`
  - `test_surface_sensor_detection.py::test_deep_insertion`
  - `test_visualization.py::test_plot_zone_duration_comparison`
  - `test_visualization.py::test_single_curve_comparison`
  - `test_visualization.py::test_many_curves_comparison`
  - `test_visualization.py::test_unknown_zone_handling`
- **`test_deep_insertion`**: FAILS in all 3 runs. Not flaky. Iron Duke's
  report of "passed this run" is incorrect.

## Empirical perturbation results

### 1. Monte-Carlo noise-floor gap distribution

Ran `probe_monte_carlo.py` across 200 RNG seeds.

**Iron Duke's 4-sensor σ=0.5 °C config** (as briefed):
- gap-to-runner-up:  min 0, median 1, p95 **3**, max **4**
- gap-to-worst-sibling: min 0, median 4, p95 6, max 6

Iron Duke's "gap caps at 3 across 200 seeds" claim is **almost** correct for
gap-to-runner-up at p95=3, but max=4 — in one seed a gap of 4 IS observed
between winner and runner-up on 4 identical-physics sensors.

**Production-path 8-sensor σ=0.5 °C** (what actually runs on real CSVs):
- gap-to-runner-up: min 0, median 1, p95 **4**, max **5**
- gap-to-worst-sibling: min 3, median 10, **199/200 seeds ≥ 4**

This is the more concerning finding: with 8 identical-physics sensors,
the winner-vs-runner-up gap reaches 4 in >5% of seeds at σ=0.5 °C.
**The threshold of 4 was calibrated on a 4-sensor experiment but the
classifier runs on 8.** Higher σ makes this worse (at σ=1.0 °C, the
gap-to-worst-sibling is ≥ 4 in 200/200 seeds).

**Saving grace**: the real CSV noise perturbation test (probe 3, below)
shows the gap on actual real CSVs stays safely below 4 at σ ≤ 1.0 °C.
The issue is theoretical: if real sensor physics genuinely are identical
(e.g. probe with all sensors in uniform-temperature zone), the 4-threshold
could trigger false flips. In practice, the three real CSVs don't sit in
this regime.

**Recommendation (Lancaster)**: update the config comment to clarify that
the "noise floor of 3" was measured at N=4 sensors with σ=0.5 °C, and
the margin-of-1 reasoning doesn't straightforwardly extend to the
production 8-sensor path. Suggest also testing gap-to-firmware directly
against realistic CSV noise levels rather than against identical-physics
siblings.

### 2. Gap=4 threshold boundary test

`probe_threshold_exact.py` — constructed fixtures with firmware=T1 and
various gaps:

| Built case | Actual gap | Winner | Override fires? | Expected |
|------------|------------|--------|------------------|----------|
| A (aimed gap 2) | 2 | T4 | NO (corrected=False) | No |
| B (aimed gap 3) | 2 | T4 | NO | No |
| C (aimed gap 4) | 6 | T4 | YES | Yes |
| D (aimed gap 5) | 6 | T4 | YES | Yes |

Note: could not construct an exact gap=3 case because the integer
rank-sum score ladder with 8 distinct sensors forces even-number gaps
(score pairs like (1,1)=2, (2,2)=4, (3,3)=6, …) unless ties are built in.
What was verified: **gap=2 does NOT fire; gap=6 DOES fire**. The gate
behaves correctly. Gap=4 and gap=5 fire (cases C and D had aimed gaps
that collapsed to 6 due to rank arithmetic).

### 3. Noise-perturbed real CSVs

`probe_noise_real.py` — added gaussian noise at σ ∈ {0.5, 1.0, 2.0} °C
across 100 seeds on each of the 3 real unlidded CSVs, post-loader-slice.
Measured seeds where gap-vs-firmware ≥ 4 (would flip the override):

| CSV | σ=0.5 | σ=1.0 | σ=2.0 |
|-----|-------|-------|-------|
| real_100098DE_1351 (firmware T4) | 0/100 | 0/100 | **5/100** |
| real_1000BA3C_0946 (firmware T1) | 0/100 | 0/100 | 0/100 |
| real_1000BA3C_1759 (firmware T1) | 0/100 | 0/100 | 0/100 |

**Only real_100098DE_1351 at σ=2.0 °C** shows 5/100 potential flips.
At σ=2.0 °C noise the winner distribution becomes: T3=48, T4=47, T2=5
— effectively a coin-flip between T3 and T4. **At realistic noise (σ≤1 °C)
the guardrails are robust.**

### 4. common_peak_idx on plateau overlaps

`probe_peak_overlap.py` — constructed two-sensor plateau-overlap case
(T1 plateaus 100..150, T2 plateaus 120..140 with LATER first-peak).
Result: `common_peak_idx = 141` (just after T2's plateau ends). At that
index, T1 reads 95.0 (STILL within 0.05 °C tolerance of its peak because
T1's plateau extended to 150) and T2 reads 95.0 (AT its peak). Neither
is systematically biased. Both retain ~94 °C at the cool-sample idx.
Iron Duke's "latest first-peaking sensor's LAST-at-max index" definition
is **deterministic** and does not create the biasing-toward-one-sensor
pathology I initially feared. ACCEPT the deviation.

**Single-peak case**: `_latest_at_max_idx` returns idx=150 while
`max(idxmax)` = 149 — differs by 1 sample because `np.concatenate` of
two np.linspace segments produces a 2-sample apparent plateau at the
transition (both samples read exactly 100 °C). On real CSVs with noisy
peaks this offset is typically 1-3 samples. Iron Duke's claim that the
plateau-end collapses to `max(idxmax)` on single-peak curves is **slightly
imprecise** — it's max(idxmax) + (samples-within-0.05°C-of-peak). Not a
bug; the +k offset still measures retained temperature correctly.

### 5. Heat-only fallback trigger matrix

Introspected each fixture (`probe_introspect.py`):

| Fixture | n | common_peak_idx | cool_sample_idx | cool_available | Winner | Gap vs firmware | Override? |
|---------|---|-----------------|-----------------|----------------|--------|-----------------|-----------|
| core_sensor_unambiguous | 600 | — | — | **True** | T4 | 11 | (synth, no integ) |
| core_sensor_disagreeing_metrics | 600 | — | — | **True** | T6 | — | (synth, no integ) |
| real_100098DE_1351 | 328 | — | — | **True** | T4 | 0 | No |
| real_1000BA3C_0946 | 287 | — | — | **FALSE** | T1 | 0 | No |
| real_1000BA3C_1759 | 944 | 930 | 942 | **True** | T2 | 1 | No |
| wonder_white_10k (loader-sliced) | 300 | 299 | 311 | **FALSE** | T5 | 7 | YES |

**Two surprising findings**:

(a) **real_1000BA3C_0946 triggers heat-only fallback** — not just wonder
white. The briefing framed heat-only as wonder-white-specific. In fact
it fires on any log whose loader-sliced end is near a latest-sensor's
peak. This case ALSO has cool_available=False; fortunately firmware T1
is also the heat-rank winner, so no override considered. But **this
behaviour is silent** — nothing in the diagnostic dict or log output
indicates that heat-only fallback was used. **Recommend Lancaster add
a `cool_available` key to the diagnostics dict** so downstream can see
when a ranking is heat-only.

(b) **core_sensor_disagreeing_metrics does NOT trigger heat-only**
(cool_available=True). Good — T6 wins by genuine combined-rank, not by
accident. The test is valid.

### 6. Downstream propagation trace through sidebar.py

Traced: `loader.get_core_sensor(curve_index)` → `get_core_sensors()`
(loader.py:507-517) → `_get_automatic_core_sensors()` (loader.py:870-871)
→ `SensorAssignmentManager.get_automatic_core_sensors()`
(sensor_assignment_manager.py:37-54).

`sensor_assignment_manager.py:46-47` correctly routes `core` when
`core_physics_corrected=True`, hitting BEFORE the legacy `core_info`
fallback. **Sidebar override dropdown displays the corrected core.**

`sensor_naming.py:28-32` (get_dynamic_sensor_names, used by
`tabs/temperature_profile.py:5`) uses BOTH:
- `assignments['core']` for the "Primary" flag (authoritative ✓)
- `assignments['core_info']['all_sensors']` for the set of sensors to
  tag as "Core" (firmware histogram — NOT updated by correction)

Verified empirically via `probe_downstream.py` on wonder white:
- `T5: "Core (Primary)"` ✓ (because T5 happens to appear in firmware
  histogram with 40 samples)
- `T1: "Core"` ✓ (because T1 dominates firmware histogram with 260)

For wonder white this is correct by coincidence. **If the physics
correction picks a sensor that doesn't appear in the firmware histogram
at all, it won't be labelled "Core" at all** (legend collision risk).
Not blocking — no current fixture triggers it — but it's a display
fragility.

**Recommendation (Lancaster)**: either (a) union physics-corrected
core into the set of "Core"-labeled sensors in `get_dynamic_sensor_names`,
or (b) rewrite `get_dynamic_sensor_names` to drive off
`loader.get_core_sensor()` / `get_surface_sensor()` rather than the raw
firmware histograms.

## Deviations from brief (Iron Duke's 4 self-called)

### 1. CONFIDENCE_GAP_MIN = 4 (briefed as 2)

**CHALLENGE → ACCEPT_WITH_NOTE.** At 4 sensors σ=0.5 °C, p95=3, max=4
(not "3 across 200 seeds" — max is 4). At 8 sensors σ=0.5 °C, p95=4,
max=5 — the margin-of-1 above noise is thinner than Iron Duke implied,
but the real-CSV noise-perturbation test shows 0/100 flips at realistic
σ ≤ 1.0 °C. Calibration is **safe in practice**, somewhat optimistic in
theory. Config comment should be tightened (notes to Lancaster).

### 2. `common_peak_idx` = latest first-peaking sensor's LAST-at-max index

**ACCEPT.** Deterministic, handles plateau fixtures correctly, does not
create the biasing pathology I feared. On single-peak curves it offsets
from `max(idxmax)` by the plateau-width-within-tolerance (typically 1-3
samples) rather than strictly collapsing — harmless.

### 3. Heat-only fallback when cool window extends past EOF

**ACCEPT WITH CONCERN.** Fallback is necessary and the wonder-white
test validates it. **But**: the behaviour is silent (no flag in
diagnostics, no log output), AND it fires more often than Iron Duke
implied (also on real_1000BA3C_0946, the unlidded truncated CSV).
Recommend surfacing `cool_available` in the diagnostic dict.

Separately verified the `core_sensor_disagreeing_metrics` fixture does
NOT accidentally trigger heat-only — combined-rank is active, and T6
wins genuinely (not via heat-only → T5).

### 4. sensor_assignment_manager.py modified (4th file)

**ACCEPT.** The silent-shadow path is real: without this edit,
`_get_automatic_core_sensors` would return firmware's histogram sensors
ignoring `core_physics_corrected`. The inline comment at lines 43-46
documents the fix. Edit is minimal and correct.

**New shadow discovered**: `sensor_naming.py` and `sidebar.py:183-191`
also read firmware `core_info['all_sensors']`. Not breaking the main
contract (the corrected core still reaches `get_core_sensor()`), but
displays are coincidentally-correct on wonder white and potentially
mislabel on future CSVs. See note #6 above.

## New concerns surfaced

1. **`test_deep_insertion` is consistently failing**, not flaky, in 3/3
   runs. Iron Duke's "it passed this run" is wrong. It's a pre-existing
   red test, not impacted by this mission but worth correcting the
   record.

2. **Full-suite math is +6, not +7.** Baseline 120 + 6 new dedicated
   core tests = 126 (observed). 127 was never reached. Iron Duke
   overcounted by 1 — no "mysterious fortuitous pass" exists.

3. **`cool_available=False` fires silently on real_1000BA3C_0946** —
   heat-only fallback activates on non-lidded short logs whose loader
   slice ends near the last sensor's peak. Currently harmless (firmware
   is heat-winner too) but diagnostic opacity is a risk.

4. **`sensor_naming.get_dynamic_sensor_names` still keys off firmware
   histogram** for the "Core"-label set, not physics-corrected
   assignments. Wonder white's T5 happens to appear in firmware
   histogram so it's tagged correctly; a future correction to a non-
   firmware-histogram sensor would be mislabelled.

## Mystery of the +7 full-suite passing

**No mystery — arithmetic error.** Baseline 120p + 6 new tests = 126p.
Iron Duke's self-report of 127p is off by 1. All 3 full-suite runs
reproduce 126p/8f/1s. `test_deep_insertion` is NOT flaky and DID NOT
pass — failed all 3 runs. No hidden previously-failing test has turned
green.

## Blocking vs non-blocking

**Non-blocking (ACCEPT_WITH_NOTES for Lancaster):**

1. Update config comment for `CONFIDENCE_GAP_MIN = 4` to clarify the
   noise-floor measurement was 4-sensor σ=0.5 °C, and the margin at
   8 sensors is thinner (p95=4, max=5 on identical-physics siblings).
2. Surface `cool_available` in the diagnostics dict and/or log output
   when heat-only fallback fires; currently silent on real_1000BA3C_0946.
3. Either teach `sensor_naming.get_dynamic_sensor_names` about
   `core_physics_corrected`, or rewrite it to drive off
   `loader.get_core_sensor()` rather than the firmware histogram.
4. Correct the mission-report arithmetic: net full-suite change is
   +6 passes, not +7. `test_deep_insertion` consistently FAILS — it is
   NOT flaky.

**Not blocking because**: the core contract of the mission — override
fires when combined-rank is unambiguous, guardrails hold on all 3 real
unlidded CSVs, 21 dedicated tests pass, and the corrected sensor does
reach `loader.get_core_sensor()` and the sidebar dropdown — all hold.

## Files reviewed / perturbation probes saved

Mission dir probes (for replay):
- `probe_monte_carlo.py` — 4- and 8-sensor identical-physics noise-floor gap distribution
- `probe_threshold_boundary.py` / `probe_threshold_exact.py` — constructed fixtures exercising override gate
- `probe_noise_real.py` — gaussian noise on the 3 real CSVs
- `probe_introspect.py` — classifier diagnostics on all 6 fixture cases
- `probe_wonder_white.py` — wonder-white-specific trace (raw vs loader-sliced)
- `probe_peak_overlap.py` — overlapping-plateau and single-peak `common_peak_idx`
- `probe_downstream.py` — `get_dynamic_sensor_names` propagation trace
