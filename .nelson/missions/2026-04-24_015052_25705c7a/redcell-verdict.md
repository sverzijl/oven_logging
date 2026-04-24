# Red-Cell Verdict — HMS Audacious

## Verdict: REVISE

Any-sensor-per-sample contamination detection (confirm_n=2, threshold 2.0 °C/s)
has a **13% false-positive rate on the BA3C_1759 guardrail** and **62% on
100098DE** at σ=1.0 °C noise. Both far exceed the ≤5% REVISE threshold in the
briefing. The `min_k_sensors=2` variant fires on PWM (true positive retained)
while dropping BA3C_1759 FP to 4% and 100098DE to 17% — a clearly superior
calibration point that Vanguard did not explore. Not shipping without
tightening.

## Independent test verification
- 25 dedicated tests (`tests/test_curve_boundary_detection.py`): **25 passed**
- Full suite 3 runs: **130/8/1, 130/8/1, 130/8/1**
  (Vanguard claimed 131/7/1; discrepancy likely single-run flake or stale
  baseline — three independent runs give a deterministic 130/8/1)
- test_deep_insertion: **FAIL** all 3 runs (deterministic, not flaky; prior
  mission notes called it flaky but it is consistent fail in my runs)
- test_shallow_insertion: **FAIL** all 3 runs (new observation — Vanguard did
  not call this out as a pre-existing failure)

## Empirical perturbation results

### 1. Noise false-positive rate (σ=1.0 °C, 100 seeds, gaussian per sensor)

| CSV              | baseline winner | baseline contam | cool_available | **FP rate (contam False→True)** | winner flips |
|------------------|:---------------:|:---------------:|:--------------:|:--------------------------------:|:------------:|
| 100098DE_1351    | T4              | False           | True           | **62/100 (62.0%)**              | 18/100       |
| BA3C_0946        | T1              | True            | **False**      | 0/100 (0.0%) *                  | 0/100        |
| BA3C_1759        | T1              | False           | True           | **13/100 (13.0%)**              | 19/100       |

\* BA3C_0946's baseline is already contam=True because `cool_available=False`
dominates via the EOF fallback; no further flip possible. But the fact that
contamination fires on a clean-but-truncated unlidded CSV at baseline is a
semantic red flag by itself (the diagnostic key reports a false physical
inference — "probe was pulled" — when nothing of the kind happened).

**Both 100098DE_1351 (62%) and BA3C_1759 (13%) exceed the 5% REVISE threshold.**
BA3C_1759 is the explicit briefing guardrail ("real_1000BA3C_1759 (real slow
cooldown) still uses combined rank, not heat-only fallback"); at σ=1.0 °C the
cool-rank gets nuked 13% of the time. 100098DE's 62% is catastrophic.

### 2. Transient spike test (above/below threshold on single sensor)

| injected                               | probe_removal fires? | expected | pass |
|----------------------------------------|:--------------------:|:--------:|:----:|
| 1-sample transient, rate 2.1 °C/s      | No                   | No       | YES  |
| 2-sample sustained, rate 2.1 °C/s      | Yes                  | Yes      | YES  |
| 1-sample transient, rate 0.6 °C/s      | No                   | No       | YES  |

confirm_n=2 correctly guards against single-sample noise on ONE sensor.
(Problem is different when many sensors are independently noisy.)

### 3. Staggered-drop specificity test

Synthetic curve where each of 8 sensors shows a single-sample 15 °C drop,
offsets spread across N samples. No coordinated probe pull.

| spread (samples) | probe_removal_idx | classifier contam | pass |
|------------------|:-----------------:|:-----------------:|:----:|
| 20 (2–3 samples apart)   | None       | False (cool_available False too)* | YES |
| **8 (adjacent samples)** | **300**    | False**           | **NO (detector fires)** |

\* spread=20 run had cool_available=False due to synthetic setup, not a
semantic answer.
\*\* classifier-level contam=False only because the synthetic's common_peak_idx
happened to land inside the plateau where cool_available was already False via
EOF — but the **detector function returned a positive index**, meaning in any
other curve shape this would fire. The "any-sensor-per-sample" rule is
empirically fooled by back-to-back single-sample noise on different sensors.

### 4. cool_contamination_detected matrix across all fixture cases

| case                                     | winner | expected | contam | cool_av | result           |
|------------------------------------------|:------:|:--------:|:------:|:-------:|------------------|
| real_100098DE_1351                       | T4     | T4       | False  | True    | clean unlidded ✓ |
| real_1000BA3C_0946                       | T1     | T1       | **True** | **False** | winner via EOF; contam-fire is spurious but harmless |
| real_1000BA3C_1759                       | T1     | T1       | False  | True    | guardrail holds ✓ |
| wonder_white_10k_lidded                  | **T5** | T6 (T5 alt OK) | True | True | winner via heat-only; T5 is accepted alternate; note: contamination fires on the *existing anchor* case that was previously resolved via combined rank |
| core_sensor_unambiguous                  | T4     | T4       | False  | True    | ✓                |
| core_sensor_disagreeing_metrics          | T6     | T6       | False  | True    | ✓                |
| post_wonder_meal_lidded                  | T5     | T5       | True   | True    | new target ✓     |
| probe_removal_contaminates_cool_rank     | T4     | T4       | True   | True    | new target ✓     |

Cases with no T1..T8 (single-curve boundary fixtures) were skipped — they
don't reach the combined-rank classifier.

**Two unexpected contam=True firings**: BA3C_0946 (already heat-only via
EOF, so harmless to result) and wonder_white_10k_lidded (winner flipped T6→T5,
both are accepted — but the mechanism changed from combined-rank to heat-only
fallback without intent).

### 5. Alternative-semantics probe (strong REVISE signal)

Coordinated-drop variant: require at least `min_k` sensors exceeding threshold
on the SAME sample, confirmed for confirm_n=2.

| min_k | PWM fires (true pos) | BA3C_1759 FP @σ=1.0 | 100098DE FP @σ=1.0 |
|-------|:--------------------:|:-------------------:|:------------------:|
| **1 (Vanguard's current)** | True | **13%** | **62%** |
| **2**                       | True | **4%**  | **17%** |
| 3                           | False | 0%     | 3%     |

**`min_k=2` retains PWM detection while dropping BA3C_1759 FP below 5% and
cutting 100098DE FP by 3.6×.** This is a Pareto improvement Vanguard did not
explore. The "different sensors exit the loaf at different moments" physics
argument in the docstring is correct in principle but over-corrected: a real
probe pull drops MANY sensors simultaneously on the same sample (empirically
≥2, likely ≥3 on PWM), so `min_k=1` is weaker than physics requires.

## Deviations from brief (Vanguard's 3 self-called)

### 1. Any-sensor-per-sample semantic shift — **CHALLENGE (blocking)**
Brief specified single-series confirm_n=2. Vanguard moved to any-sensor-per-
sample because single-series under-triggered on PWM (T1 idx 345, T5/T6 idx
346 — no sensor holds 2 samples). The empirical defence is real. **But the
chosen `min_k=1` gives a 13%/62% false-positive rate on σ=1.0 °C noise on the
two real guardrails**. The PWM physics argument supports `min_k≥2` (whole
probe pulls drop ≥2 sensors simultaneously), and the data shows `min_k=2`
retains the true positive while more than 3× cutting false positives. The
current setting is calibrated-to-a-sample-of-one on PWM alone.

### 2. DRY extraction into `_drop_rate_detection.py` — **ACCEPT**
- Both call sites produce identical results: `tests/test_curve_boundary_detection.py`
  25/25 pass, including all 15 boundary tests + lidded + core-sensor tests.
- Two entry-point functions `find_confirmed_drop_start` and
  `find_confirmed_multi_sensor_drop` are genuinely distinct: single-array
  scan vs per-sample multi-array check. Merging them with a `mode` param or
  callable adapter would add complexity without payoff. Keeping two small
  functions sharing `_rate_at` is clean.
- Minor docstring inconsistency (both say "strictly exceeding" but code uses
  `>=` / `<`), non-blocking polish.

### 3. Fixture patch scope (5 Virtual* cols vs briefed 3) — **ACCEPT**
- `src/data/loader.py:278`:
  `used_virtual_path = all(col in df.columns for col in virtual_cols + assignment_cols)`
  where `virtual_cols = [VirtualCoreTemperature, VirtualSurfaceTemperature,
  VirtualAmbientTemperature]` and `assignment_cols = [VirtualCoreSensor,
  VirtualSurfaceSensor, VirtualAmbientSensor]`.
- ALL SIX columns are required for the loader to route through the virtual
  path and eventually call `identify_core_sensor_combined_rank`. Without any
  one, the loader falls through to dynamic classification and the combined-
  rank classifier is never invoked — making the contamination detector
  untestable on the synthetic fixture.
- Vanguard's +5-column fixture patch is the minimum needed. Sibling fixtures
  `core_sensor_unambiguous` / `core_sensor_disagreeing_metrics` already have
  this same 5-column set via `_build_core_sensor_base`. Necessary, idiomatic.

## New concerns surfaced (Vanguard did not mention)

1. **Full-suite baseline off by one**: three independent runs show 130/8/1, not
   Vanguard's claimed 131/7/1. `test_shallow_insertion` fails deterministically
   alongside `test_deep_insertion`. Not a new regression introduced by this
   mission (both are pre-existing known-fragile tests), but the damage report's
   "7 remaining failures" figure is wrong. Duncan's 2x baseline check in task 5
   should reveal this.

2. **Spurious contamination fire on BA3C_0946**: `cool_contamination_detected=True`
   on a clean unlidded truncated CSV at baseline. Winner is T1 anyway (via the
   `cool_available=False` branch), but the diagnostic key reports "probe was
   pulled" when nothing of the kind happened. Callers that read
   `cool_contamination_detected` for logging, alerting, or downstream decisions
   will get a wrong physical inference. Fix the any-sensor semantics → both
   false positives (62%/13%) and this spurious baseline go away.

3. **Threshold `>=` not `>`**: both helper functions accept `rate == rate_c_s`
   (code uses `< rate_c_s` → break in single-series; `>= rate_c_s` → accept in
   multi). The docstrings say "strictly exceeding" which suggests `>`. Minor,
   non-blocking.

4. **`wonder_white_10k_lidded` resolution mechanism changed silently**: this
   fixture's expected answer is "T5 or T6". Before Vanguard's change, it
   resolved to T6 via combined rank. After, it resolves to T5 via heat-only
   fallback because `cool_contamination_detected=True` fires on this lidded
   curve. Both answers pass the test, so no test regression — but the case
   that drove the original mission 2026-04-23_231637_4ed7fcd1 combined-rank
   design is no longer exercising combined-rank logic. Contamination detection
   has effectively taken over the lidded-case path. If the contamination
   semantics tighten (e.g. to `min_k=2`), the lidded case may re-enter
   combined-rank — worth re-verifying downstream behavior when retuning.

## Blocking vs non-blocking

### MUST FIX (blocks Duncan)
- **Tighten `find_confirmed_multi_sensor_drop` to require `min_k_sensors ≥ 2`
  (or equivalent)**. Empirically supported alternative: at each sample in the
  confirm window, require ≥2 sensors simultaneously exceeding the rate
  threshold. Data shows this keeps PWM firing while reducing BA3C_1759 FP to
  4% (under the 5% bar) and 100098DE FP from 62%→17%. Also retune/add a new
  constant `PROBE_REMOVAL_MIN_SIMULTANEOUS_SENSORS` in
  `CORE_DETECTION_CONFIG` with physics rationale comment.
  - After retightening, re-run `tests/test_curve_boundary_detection.py`
    (expect 25/25 still green) AND re-run `probe_noise_real.py` and
    `probe_alternative_semantics.py` in the mission dir to confirm the
    numbers.
  - Add a test that the staggered-drop synthetic (8 sensors each with one
    1-sample spike across adjacent samples) does NOT fire contamination.
  - Add a test that BA3C_0946's baseline `cool_contamination_detected` is
    False (currently True — a spurious inference).

### NON-BLOCKING (Duncan polish)
- Docstring nit: both helpers say "strictly exceeding" but use `>=`. Either
  change the code to `>` or the docstring to "at or exceeding".
- Add a briefing-level cross-reference in the
  `_drop_rate_detection.py` module docstring to `CORE_DETECTION_CONFIG`'s
  probe-removal constants so future readers find the tuning rationale.

### Replay
- `probe_noise_real.py` — reproduces the σ=1.0 false-positive numbers.
- `probe_staggered_spikes.py` — reproduces the staggered-drop specificity fire.
- `probe_alternative_semantics.py` — reproduces the `min_k` sweep.
- `probe_introspect.py` — reproduces the per-fixture contamination matrix.
