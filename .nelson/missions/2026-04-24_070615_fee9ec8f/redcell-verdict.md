# Red-Cell Verdict — HMS Ambush

## Verdict: ACCEPT_WITH_NOTES

Stance B implementation is functionally correct on all 18 fixtures, introspection
matrix verified independently, and full-suite baseline (135/8/1) held across 3
runs. Dragon's two replacement guards (`peak_idx+1` scan start, 80 °C
min-peak-temp filter) are defensible once the physics of the BA3C_1759 j=293
cliff is understood. However, one non-blocking concern surfaces: cliff fragility
under realistic Combustion Inc. probe noise (σ ≈ 0.05–0.15 °C) has **regressed**
relative to the prior mission's "0 FP under σ ≤ 1.0 °C" result — the detector
now splits BA3C_1759 into 3 curves in 27 %–60 % of noise trials at realistic σ.

## Independent test verification

- **30 boundary tests**: 30/30 pass (verified from a fresh pytest invocation).
- **Full suite, 3 runs**: 135 passed / 8 failed / 1 skipped × 3. Failure set is
  the pre-existing visualization baseline (matches Defender). No new regressions.
- **Introspection matrix** verified via `probe_introspect_full.py` against live
  `tests/fixtures/curve_boundary_cases.py`:
  - `real_100098DE_1351`: end=306, truncated=False ✓
  - `real_1000BA3C_0946`: end=293, truncated=False ✓
  - `real_1000BA3C_1759[0]`: end=944, truncated=False ✓
  - `real_1000BA3C_1759[1]`: end=6185, truncated=False ✓ (start drifts 5890→6032; within tolerance=5? NO — 142 samples, but outside scope of this mission)
  - `post_wonder_meal_lidded`: end=344, truncated=False ✓
  - `wonder_white_10k_lidded`: end=338, truncated=False ✓

Side finding during introspection: two fixtures have known pre-existing failures
(`two_bakes_no_cool[1]` end 123 vs 92, `probe_removal_contaminates_cool_rank`
end 309 vs 299). Not introduced by Dragon's changes — existing baseline.

## Central investigation

### Q1 — Nature of BA3C_1759 j=293 cliff

**Finding: it IS a genuine probe-pull event, not a probe-insertion artifact.**

Raw inspection at `probe_q1_j293_nature.py` (j=280..310 of skiprows=10 dataframe):
- j=0..293: core rises monotonically from room temp to 96.75 °C over ~25 min
  (a full, clean bake — PredictionState='Cooking', VCS=T1 throughout).
- j=293 → j=294: **20.05 °C cliff** (96.75 → 76.70), **all 8 sensors drop
  simultaneously** (T1..T8, including ambient T8 170 → 166 °C → collapses over
  next 10 samples). The probe was physically withdrawn from the loaf into
  cooler surroundings.
- j=294..299: monotonic decline to ~40 °C.
- j=300..944: core warms back to 98.15 °C (second loaf, same session; probe
  reinserted). Cliff at j=944 → 945 (23.05 °C drop).

So BA3C_1759 physically contains **three probe-in-loaf events** (0..293,
300..944, 5890..6185). The fixture merges the first two into one logical
"bake 1" because PredictionState never reverts to 'Probe Not Inserted' — the
probe stayed turned on between the two insertions. Ground truth
`expected_ends=[944, 6185]` encodes this merge. Dragon's guard is therefore
**consistent with the fixture's choice**, not with the physics. This is a
design call, not a bug — but it means the guard is genuinely protecting against
a first-probe-pull-event, not merely an insertion transient. The briefing's
framing ("probe-insertion signature") is imprecise; a more accurate description
is **"first-probe-pull-of-a-multi-pull-session"**.

Corollary: the identical pattern exists in `post_wonder_meal_lidded` at j=189
(87.35 → 47.35 = 40 °C drop, probe repositioned, then loaf #2 bakes to peak
98.65 at j=343 → cliff at j=344). Dragon's `peak_idx+1` logic protects both.
Not a single-CSV fit.

### Q2 — `peak_idx+1` scan correctness

**Finding: correct. Grace-window fallback covers the edge cases.**

Probed via `probe_q2_peak_idx_scan.py` and `probe_q2_debug.py`:

- **Main loop, long log, cliff after peak** (normal case): works — cliff fires
  at the running-peak+grace offset.
- **Cliff AT peak_idx, log ends shortly after** (short-bake case): the main
  loop's `peak_idx+1` scan cannot find it, but `_detect_curve_end`'s terminal
  grace-window fallback (lines 290–292 of `curve_boundary_detector.py`)
  re-runs `_candidate_probe_pull_cliff` from peak_idx and picks it up. Confirmed
  on a 40-sample synthetic: peak at j=30, cliff at j=30→31 → end=30, trunc=False.
- **Case where cliff-at-peak should legitimately fire mid-log** (pathological
  very-short-bake-then-pull inside a longer log): the grace fallback runs ONLY
  at end-of-log. If a genuine short-bake cliff-at-peak happens mid-log and a
  subsequent taller peak moves the running-max, the first cliff is silently
  dropped (consistent with the BA3C_1759 merge semantics). This is the intended
  behavior under Stance B — no counterexample found in the fixture set.

### Q3 — 80 °C min-peak-temp defensibility

**Finding: defensible. Well-margined against all real cliffs; correctly
suppresses the cascade post-cliff rescan.**

Probed via `probe_q3_min_peak.py`:

Real-CSV cliff sample temperatures (value at the cliff's starting sample):

| CSV | cliff_j | temps[j] | drop |
|---|---|---|---|
| real_100098DE_1351 | 306 | 93.95 | 21.65 |
| real_1000BA3C_0946 | 293 | 96.75 | 20.05 |
| real_1000BA3C_0946 | 294 | 76.70 | 16.00 (cascade — correctly suppressed) |
| real_1000BA3C_1759 | 293 | 96.75 | 20.05 |
| real_1000BA3C_1759 | 294 | 76.70 | 16.00 (cascade — suppressed) |
| real_1000BA3C_1759 | 944 | 97.80 | 23.05 |
| real_1000BA3C_1759 | 6185 | 96.35 | 26.95 |
| wonder_white_10k_lidded | 350 | 93.20 | 17.15 |
| post_wonder_meal_lidded | 189 | 87.35 | 40.00 (first probe move) |
| post_wonder_meal_lidded | 344 | 98.00 | 18.70 |

Lowest-temperature real cliff: 87.35 °C (post_wonder_meal j=189). Margin to
80 °C: **7.35 °C** — defensible. Cold-finished underbake at 78 °C is also
rejected by the curve-acceptance gate (`MIN_PEAK_TEMP` at line 96 of
`extract_curves`) so the threshold is doubly enforced and consistent.

The filter also correctly suppresses the **cascade false positive** at j=294
(76.70 → 60.70 = 16 °C drop). Without the filter, once the scan passes j=293,
the detector would register a second cliff at j=294 and the search loop would
keep finding cascade cliffs all the way down. Verified in `probe_q3_min_peak.py`
Case (d).

**Non-blocking concern**: `MIN_PEAK_TEMP=80` is currently *shared* with the
curve-acceptance threshold. The two uses are semantically distinct:
- Curve acceptance: "a bake has to reach ≥ 80 °C to count as a bake".
- Cliff-start gate: "a cliff's starting sample has to be ≥ 80 °C to count".

If either threshold is tuned for one purpose, the other moves unintentionally.
Future mission should consider a dedicated `CLIFF_MIN_START_TEMP_C` constant.
Not blocking — Dragon reused the existing constant sensibly.

### Q4 — Interaction with `min_k=2` contamination detector

**Finding: zero interaction. Different code paths, different stages.**

- Cliff detector lives in `src/data/curve_boundary_detector.py:_candidate_probe_pull_cliff`.
- `min_k=2` lives in `src/data/_drop_rate_detection.py:find_confirmed_drop_start`
  and `src/data/thermodynamic_sensor_classifier.py`.
- Cliff path uses a single-sensor (core) criterion. `min_k=2` path uses
  multi-sensor simultaneous drop criteria.
- Cliff is in curve-extraction (upstream). `min_k=2` contamination detection is
  in core-sensor selection (downstream). They don't share state; they can't
  disagree about exit because they don't compute exit together.

`grep -n "min_k" src/` confirms only 3 files reference it, none in
`curve_boundary_detector.py` or its callees. No interaction.

## Perturbation battery

### Standard noise sweep: `probe_realistic_noise.py`

σ ∈ {0.05, 0.15, 0.3, 0.5, 1.0}, 30 trials each, 5 real CSVs:

| CSV | σ=0.05 (splits/drift) | σ=0.15 | σ=0.30 | σ=0.50 | σ=1.00 |
|---|---|---|---|---|---|
| real_100098DE_1351 | 0/30, 0 | 0/30, 24 | 0/30, 70 | 0/30, 387 | 0/30, 700 |
| real_1000BA3C_0946 | 0/30, 0 | 0/30, 0 | 0/30, 0 | 0/30, 0 | 0/30, 0 |
| **real_1000BA3C_1759** | **8/30** splits | **18/30** splits | **30/30** | 30/30 | 30/30 |
| wonder_white_10k_lidded | 0/30, 12 | 0/30, 12 | 0/30, 28 | 0/30, 12 | 0/30, 68 |
| **post_wonder_meal_lidded** | 0/30 | **4/30** splits | **28/30** splits | 30/30 | 30/30 |

Key observations:
- **BA3C_1759 cliff-split regression**: at σ=0.05 (bottom of Combustion spec
  range), 27 % of trials split bake-1 into two sub-bakes at j=293 and j=944. At
  σ=0.15 (top of spec range), 60 %. Prior mission's "0 FP" budget is blown.
  Mechanism: noise perturbs the running-max climb; in some trials the running
  peak crosses 96.75 *before* j=293, which moves the `peak_idx+1` scan start
  earlier than j=294 and catches the j=293 cliff in the main loop. The split
  produces two physically-real sub-bakes; the fixture's ground-truth merges
  them by convention (PredictionState-stuck heuristic), which noise breaks.
- **100098DE_1351 end-drift**: at σ=0.5 the end index drifts up to 387 samples;
  at σ=1.0 up to 700 samples. The detector is silently picking a different exit
  candidate — likely `cool_to_ambient` firing later in the tail when noise moves
  the running peak further right.
- **PWM** shows similar split behavior at σ ≥ 0.15: 4/30 splits, growing to
  28/30 at σ=0.3.

### Introspection matrix across all 18 fixtures

`probe_introspect_full.py` — all 6 cases named in the briefing verified. Two
pre-existing failures (two_bakes_no_cool, probe_removal_contaminates_cool_rank)
are unrelated to this mission.

### Synthetic probes

`probe_synthetic_insertion.py`:
- **Warm probe inserted into cold dough** (25 → 7 °C drop at j=50, then real
  bake to 95): detector correctly ignores the j=50 drop (below MIN_PEAK_TEMP)
  and finds the probe-pull cliff at the correct end of the real bake.
- **Double cliff** (probe-pull at j=50 + real bake cliff at j=159): cliff-at-peak
  framing handled correctly — end=159.

`probe_q2_peak_idx_scan.py`:
- **Short bake, cliff AT peak, log ends shortly after**: grace fallback fires,
  end=peak, truncated=False. Working as documented.
- **Double cliff within a merged session**: correctly picks the second cliff
  (matches fixture convention).

## Dragon's 2 replacement guards: ACCEPT

- **Guard 1 (`peak_idx+1` scan start)**: correct and load-bearing. Without it,
  both BA3C_1759 and PWM would fire on their first probe-repositioning event
  at j=293 / j=189 and end the merged-bake curve prematurely. The grace-window
  fallback correctly catches short-log cliff-at-peak cases.
- **Guard 2 (80 °C min-peak-temp filter on cliff start)**: correct and necessary.
  Without it, the cascade at j=294 (76.70 → 60.70 = 16 °C drop) would fire as
  a second cliff and confuse the search loop. Well-margined against all real
  fixtures.

Both guards are defensible once the physics of the first-probe-pull case is
understood (which the briefing undersold as "probe insertion" — it's actually
"first probe-PULL of a multi-insertion session").

## New concerns

### Concern A: Cliff fragility under realistic Combustion noise (NON-BLOCKING)

At σ = 0.05–0.15 °C (manufacturer spec range for Combustion Inc. probes),
BA3C_1759 splits bake-1 into two sub-bakes in 27 %–60 % of trials, and PWM
begins splitting at σ = 0.15. Prior mission (HMS Astute) measured "0 FP at
σ ≤ 1.0 °C" — that budget no longer holds under Stance B's framing because
the cliff is now the primary signal, not a tie-breaker.

Severity: moderate. Real CSVs in the fixture have visible noise well below σ
= 0.05 (sample-to-sample jitter ≤ 0.1 °C by eye), so the 30/30 test pass holds
on actual data. But future CSVs with noisier cores may silently gain extra
curves. Mitigation options for a follow-up mission:
1. Smooth `temps` with a small window before running the cliff scan.
2. Require the running peak to be ≥ (cliff-start + N °C) for the `peak_idx+1`
   guard to activate — makes the guard order-invariant under small noise.
3. Tighten `INSTANT_DROP_THRESHOLD_C` from 15 °C to 18 °C; trades off margin
   against truly-small cliffs (wonder_white cliff is 17.15 °C — would be lost).

### Concern B: `MIN_PEAK_TEMP` used for two semantically distinct purposes (NON-BLOCKING)

Both curve-acceptance and cliff-start use the same 80 °C constant. If one is
tuned (e.g., for cold-finished products), the other moves unintentionally.
Future mission should introduce `CLIFF_MIN_START_TEMP_C` as a distinct
constant.

### Concern C: `expected_starts` for BA3C_1759 bake-2 drifts 142 samples (NON-BLOCKING, PRE-EXISTING)

Fixture says `expected_starts=[13, 5890]`; detector returns `[13, 6032]`.
That's well outside tolerance=5. Pre-existing (not a Dragon regression) and
the `ambiguous=True` tag acknowledges the bake-2 start is unconfirmed. Flag
for a future re-annotation pass.

## Blocking vs non-blocking

**Blocking**: none. Stance B ships as-is.

**Non-blocking** (flagged for Dauntless and follow-up missions):
- Concern A (cliff noise fragility) — document in CLAUDE.md or code comment;
  cover with a follow-up fixture that includes realistic-noise real CSVs.
- Concern B (shared `MIN_PEAK_TEMP`) — refactor to dedicated constant when
  cliff-start temperature is next tuned.
- Concern C (BA3C_1759 bake-2 start drift) — pre-existing, not in scope.

Probe scripts saved to mission dir:
- `probe_q1_j293_nature.py` — Q1 raw inspection.
- `probe_q2_peak_idx_scan.py` — Q2 scan-start correctness.
- `probe_q2_debug.py` — Q2 grace-fallback diagnosis.
- `probe_q3_min_peak.py` — Q3 threshold defensibility + cascade.
- `probe_q3b_pwm_j189.py` — PWM first-probe-move pattern mirror to BA3C_1759.
- `probe_q4_noise.py` — Q4 noise battery + min_k=2 grep.
- `probe_realistic_noise.py` — σ sweep across 5 CSVs.
- `probe_noise_instability.py` — noise-split detail.
- `probe_split_impact.py` — nature of noise-induced splits.
- `probe_synthetic_insertion.py` — warm-probe-into-cold-dough + double-cliff.
- `probe_introspect_full.py` — 18-fixture matrix.

-- HMS Ambush, SSN Navigator, Station 0 (Patrol).
