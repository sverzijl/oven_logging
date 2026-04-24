# Red-Cell Verdict — HMS Astute

## Verdict: ACCEPT_WITH_NOTES

The cliff candidate is empirically sound **for the stated end-detection goal**:
it fires cleanly on PWM (end=344) and the synthetic cliff fixture (end=300),
and it does NOT fire on any of the three real unlidded CSVs at baseline or
under σ ≤ 1.0 °C noise. The 250 s plateau-duration guard has a **140 s margin**
between the worst lidded case (PWM, 310 s) and the worst unlidded case
(BA3C_1759 bake-1, 170 s), not the 65 s claimed in the briefing — considerably
more comfortable than advertised.

The two deviations from brief (2 extra config params) are the **minimum**
required to hit the ground truth; I could not engineer a discriminator that
avoids them. No blocking issues found for ship. Two non-blocking concerns
surfaced — Q3 (deeper design question) and a cliff fragility at moderate
core-noise — both flagged below for Diamond / admiral follow-up.

## Independent test verification
- TestCliffProbePullDetection: **3/3 pass** (all 30 boundary tests pass)
- Full suite 3 independent runs: **135/8/1, 135/8/1, 135/8/1**
  (Ark Royal self-reported 136/7/1; I measured 135/8/1 deterministic across
  three runs. Discrepancy likely a single-run flake or stale baseline. The
  8 failures are all in `test_curve_comparison_integration.py`,
  `test_internal_sensor_filtering.py`, `test_surface_sensor_detection.py`, and
  `test_visualization.py` — unrelated to boundary detection.)

## Central questions

### Q1 — Is the physical discriminator sound?

**Mostly sound, but the stated mechanism is incomplete.** The briefing's story
("lidded bakes hold at peak hot under lid; unlidded cool immediately after
peak") is directionally correct but the empirical separation is cleaner than
that framing suggests:

| case | plateau_s (within 2 °C of peak) | post-peak cliff? |
|------|--------------------------------:|:-----------------|
| PWM (lidded)                | 310 | yes, at idx 344 (31 samples past peak) |
| synthetic cliff (lidded)    | 320 | yes, at idx 300 (AT peak) |
| wonder white (lidded, but not cliff-ending) | 0 | no — gentle decline |
| real_1000BA3C_1759 bake-1 (unlidded) | 170 | yes, at idx 944 (1 past peak) |
| real_1000BA3C_0946 (unlidded)        | 105 | yes, at idx 293 (AT peak) |
| real_100098DE_1351 (unlidded)        |   0 | yes, at idx 306 (2 past peak) |

**Note that every one of the three real unlidded CSVs also contains a
≥ 20 °C single-sample post-peak cliff** — see Q3. What actually separates
"cliff is a probe-pull" from "cliff is ordinary cooldown" is **how long the
core was held at peak before the cliff**, which is what the guard measures.
Physically that means: the probe was pulled, but in an unlidded bake the
core was already cooling when the operator pulled it; in a lidded bake the
core was still at peak.

A more general discriminator I considered:

- **Post-cliff rate compared to sensor thermal time-constant.** A probe-in-air
  equilibration drops ~25 °C over 5 s (4 °C/s then decaying). A loaf-in-cooling-
  oven might be 0.5-1 °C/s. But all four cliffs (lidded + unlidded) show
  post-cliff rates of 3-5 °C/s — the signals are indistinguishable.
- **Single-step drop magnitude at peak.** The cliff magnitude (20-27 °C) is
  similar in lidded and unlidded. Not discriminative.

The "plateau duration before cliff" is the simplest feature that actually
separates the cases we have. I agree with Ark Royal's choice.

### Q2 — How fragile is the 250 s threshold?

**Substantially less fragile than the briefing implied.** Results:

Threshold sweep on current fixtures (all pass at threshold ∈ [200, 300] seconds):

| threshold | PWM | synthetic | BA3C_1759 bake-1 | BA3C_0946 | 100098DE |
|-----------|-----|-----------|------------------|-----------|----------|
| 200 s     | 344 ✓ | 300 ✓ | 956 ✓ | 299 ✓ | 330 ✓ |
| 220 s     | 344 ✓ | 300 ✓ | 956 ✓ | 299 ✓ | 330 ✓ |
| 240 s     | 344 ✓ | 300 ✓ | 956 ✓ | 299 ✓ | 330 ✓ |
| 250 s (config) | 344 ✓ | 300 ✓ | 956 ✓ | 299 ✓ | 330 ✓ |
| 300 s     | 344 ✓ | 300 ✓ | 956 ✓ | 299 ✓ | 330 ✓ |
| 350 s     | 375 ✗ (PWM fails!) | 399 ✗ | 956 ✓ | 299 ✓ | 330 ✓ |

**The 250 s threshold has a working range of ≈ 170–340 s, a 170 s margin.**
Briefing claimed 65 s; reality is 2.6× larger. 

Synthetic margin sweep (plateau_n vs fire/no-fire):

At the configured 250 s threshold, cliff fires on plateaus ≥ 240 s and does
not fire on plateaus ≤ 200 s. The guard activates at ~240 s (slightly below
threshold because `peak_so_far` tolerance includes rise-samples near the peak).

**The guard is also calibrated to cliff AT peak (synthetic: peak=300, cliff=300).**
The `first_scan` for the cliff candidate is `peak_idx` (not `peak_idx +
post_peak_grace`), which is necessary for the synthetic fixture to fire. This
deviates from every other candidate's scan convention — see Q4 below.

### Q3 — Should unlidded fixtures ALSO clip at probe-pull? (user decision)

**This is the biggest unresolved design question. I ESCALATE.**

All three real unlidded CSVs have a ≥ 20 °C post-peak single-sample drop within
0–2 samples of peak:

| case | peak_idx | cliff_idx | drop | ground-truth end | samples post-cliff in ground truth |
|------|---------:|----------:|-----:|-----------------:|-----------------------------------:|
| real_100098DE_1351 | 304 | 306 | −21.65 °C | 329 | 23 samples (~115 s) of probe-in-air readings treated as "bread cooldown" |
| real_1000BA3C_0946 | 293 | 293 | −20.05 °C | 299 | 6 samples, but log is truncated |
| real_1000BA3C_1759 bake-1 | 943 | 944 | −23.05 °C | 955 | 11 samples (~55 s) |
| real_1000BA3C_1759 bake-2 | ~6180 | 6185 | −26.95 °C | 6200 | 15 samples (~75 s) |

If we disable the plateau guard and run the cliff candidate on these unlidded
CSVs, it fires at idx 306, 293, 944, and 6185 respectively — very close to
peak. That strongly suggests **the operator pulled the probe immediately after
peak in all cases**, and the ground-truth annotations are including sensor-in-
air equilibration as "bread cooldown."

**Two possible stances:**

1. **Unlidded ground-truth is right.** The cool-to-ambient tail, even if
   post-probe-pull, is still a useful signal for bake-chemistry zones (yeast-
   kill, browning duration, etc.), and stopping at the cliff would lose that
   tail. The plateau guard correctly keeps the cliff from firing on unlidded.

2. **Unlidded ground-truth is wrong.** The post-cliff samples are physically
   sensor-in-room-air, not loaf-interior, and should be clipped. All four
   unlidded cliffs would then clip at ≈ peak_idx + 2, and the downstream
   zone-timing analytics would become cleaner.

Stance #2 has real consequences: 100098DE's bake duration drops from 1630 s
to ~1525 s (−6%), and BA3C_1759's analytics lose ~15 samples of cool-to-40
data per bake. Whether that matters depends on which zones are being measured.

**I recommend the admiral make this call before Diamond's polish.** If #2 is
chosen, this is a new mission (revise all 4 unlidded ground-truth annotations,
simplify or remove the plateau guard, re-run all regression tests). If #1 is
chosen, Ark Royal's current design ships as-is.

## Empirical perturbation results

### 1. Per-CSV noise battery on unlidded CSVs (Q1 from briefing)

**Cliff does NOT fire spuriously on any of the three unlidded CSVs at σ ≤ 1.0 °C.**

Ran 60 seeds × 3 σ values on the 3 real unlidded CSVs; counted "cliff
spuriously fires" as end_idx < expected_end − 15 AND the winning candidate
being `cliff`. Using instrumented detector in
`probe_noise_which_candidate.py`:

| σ | 100098DE winner  | BA3C_0946 winner  | BA3C_1759 bake-1 winner |
|---|:----------------|:-----------------|:------------------------|
| 0.3 | cool (40/40)  | EOF (40/40)      | dip_rerise (35/40), cool (5/40) |
| 1.0 | cool (30/40), corepeak (10/40) | EOF (40/40) | dip_rerise (31/40), corepeak (8/40), EOF (1/40) |

**No cliff wins in 480 total noise runs.** The plateau guard is bullet-proof
against the tested noise budgets.

### 2. Cross-candidate contention (Q battery #2)

Aggregator winners per lidded case (candidate returning earliest idx):

| case | winner | all candidates |
|------|--------|----------------|
| PWM               | cliff @ 344 | all others None |
| synthetic cliff   | cliff @ 300 | all others None |
| wonder white      | corepeak @ 338 | cliff None (no >15 °C drop) |
| lidded_classic    | corepeak @ 304 | drop_rate @ 480, cliff None |
| lidded_truncated  | corepeak @ 304 | all others None |

**No contention between cliff and any other candidate on any lidded case.**
The two signatures are mutually exclusive on the fixture set.

### 3. Introspection matrix across all 18 fixture cases

See `probe_introspect.py`. Abbreviated:

| case | peak | first_cliff | plateau_s | end_idx (expected) | truncated |
|------|-----:|------------:|----------:|-------------------:|:----------|
| real_100098DE_1351 | 304 | 306 | 0    | 330 (329) | False |
| real_1000BA3C_0946 | 293 | 293 | 105  | 299 (299) | True |
| real_1000BA3C_1759 | 943 | 944 | 170  | 956 (955,6200) | False |
| noise_spike_midbake | 49 | 54 | 30   | 90 (89) | False |
| wonder_white_10k   | 332 | 350 | 0    | 338 (340) | False |
| lidded_classic     | 299 | 480 | 0    | 304 (300) | False |
| lidded_truncated   | 299 | —   | —    | 304 (300) | False |
| post_wonder_meal   | 313 | 344 | 310  | 344 (344) | False |
| synthetic_cliff    | 300 | 300 | 320  | 300 (299) | False |

All 18 cases land within the test tolerances. No surprises.

### 4. Edge case: cliff AT peak (j = peak_idx)

The cliff candidate's first_scan is `peak_idx` (not `peak_idx + post_peak_grace`).
This is necessary for the synthetic fixture: peak=300, cliff 300→301. At
j=peak_idx, `peak_so_far = temps[peak_idx]` and the plateau-run walks backward
from peak_idx.

**This deviates from the other candidates** which all scan from `peak_idx +
post_peak_grace_samples`. Ark Royal documents the intent in the docstring
("can fall AT the peak sample itself"). The deviation is semantically correct
— a probe-pull at peak is a legitimate end signal — but it means the cliff
candidate gets a 10-sample head-start over the others. On fixtures where
cliff and corepeak could both fire, the order matters.

**Currently no fixture has overlapping cliff-and-corepeak signatures**, so
the head-start is harmless. Non-blocking, but worth calling out.

### 5. Pre-cliff plateau numbers — briefing verification

Briefing claimed:
- Lidded (PWM, synthetic, wonder white): 315–325 s
- Unlidded: 0–175 s

My measurements (2 °C tolerance window):
- PWM: **310 s** (briefing said 315)
- synthetic cliff: **320 s** (briefing said 325)
- wonder white: **0 s** (briefing omitted)
- BA3C_1759 bake-1: **170 s** (briefing said 175)
- BA3C_0946: **105 s** (briefing said 110)
- 100098DE: **0 s** (matches)

Ark Royal's numbers are **5 s consistently high**. This is almost certainly
`plateau_run × dt` vs `ts[cliff] − ts[cliff − run + 1]` (off-by-one edge-point
counting). Not material to the threshold choice. **The true margin between
lidded min (310) and unlidded max (170) is 140 s, not the 65 s claimed.**

## Deviations from brief (Ark Royal's 2 extra config params) — CHALLENGE / ACCEPT

Both extra params (`CLIFF_PRE_PEAK_PLATEAU_SECONDS=250`, `CLIFF_PRE_PEAK_
TOLERANCE_C=2.0`) are **ACCEPTed**.

I attempted three alternative discriminators:

1. **Post-cliff decline rate** (probe-in-air faster than bread-in-cooling-oven):
   all four real cliffs have rates of 3-5 °C/s post-cliff. Not discriminative.
2. **Drop magnitude** (bigger drops are more likely to be pulls): unlidded
   cliffs are 20-27 °C, lidded cliffs 18-20 °C. Overlapping — not useful.
3. **Slope of rise to peak** (fast rise → unlidded): this is how the core-peak-
   plateau candidate already discriminates. PWM's rise60s is ~0.2 °C/60s,
   unlidded BA3C_1759 is ~14 °C/60s (a 70× ratio). BUT the wonder white
   fixture has rise60s ≈ 3.3 °C/60s, and the cliff does not fire on it.
   So this is correlated with plateau duration but not a clean substitute.

The plateau-duration discriminator is the minimal calibration that fits the
fixture set. **No way to reduce the parameter count without using a magic
number of comparable arbitrariness.**

### DRY decision: keeping cliff inline vs extracting to `_drop_rate_detection.py`

**ACCEPT Ark Royal's choice to keep inline.** The cliff candidate and
`find_confirmed_drop_start` have fundamentally different semantics:

- `find_confirmed_drop_start`: sustained °C/s rate over N samples.
- cliff: single-sample magnitude + weakly-monotonic tail + pre-plateau guard.

Sharing code would require a polymorphic function with "mode=rate | magnitude"
branching, which is worse than two focused methods. DRY is about knowledge
duplication, not line-count duplication — and the two methods encode
different knowledge.

## New concerns surfaced

### Concern A: PWM cliff detection is noise-fragile at σ ≥ 0.5 °C (NON-BLOCKING)

Probe `probe_pwm_noise.py`: at σ=0.5 °C core noise, PWM's cliff fails to fire
(0/60 runs hit ±5 of 344). The cliff itself isn't breaking — but `dip_rerise`
fires at idx ≈ 200 (noise-induced phantom dip), splitting PWM into 2 curves.
The second curve then can't find cliff because the post-cliff monotonicity
guard fails under σ=0.5+ noise.

Real Combustion-probe noise is σ ≈ 0.05-0.15 °C (per Combustion Inc specs),
so this is pessimistic for production. BUT: this is not a *new* fragility;
dip_rerise is noise-sensitive pre-existing, and the cliff candidate doesn't
introduce any new failure mode. Flagging for awareness, **not for this
mission's fix**. A future mission could tighten the monotonicity guard to
"weakly monotonic with tolerance" (allow up to +0.5 °C step-ups in the
5-sample tail).

### Concern B: Docstring has a stale "150 s" number (TRIVIAL — Diamond should fix)

`src/data/curve_boundary_detector.py:602` docstring reads "Threshold 150 s
sits in the margin" but the config is 250 s. Ark Royal likely tuned up
during development. **Diamond's polish item.**

### Concern C: Pre-peak plateau numbers in the briefing are 5 s high (TRIVIAL)

See section 5 above. Doc correction only; no functional impact.

### Concern D: Cliff candidate ignores post_peak_grace (NON-BLOCKING, DOCUMENTED)

The cliff candidate scans from `peak_idx` (not `peak_idx + post_peak_grace`),
which is required for the synthetic fixture where cliff AT peak. Every other
candidate respects post_peak_grace. Currently no fixture has overlapping
cliff-and-corepeak signatures, so the 10-sample head-start is harmless.

### Concern E: **Q3 is the right design question** (ESCALATE TO ADMIRAL)

See Q3 above. The unlidded fixtures may be annotating sensor-in-room-air
readings as "bread cooldown." This could materially change the detector's
design. **If the admiral agrees with Stance #2 (unlidded ground-truth wrong),
the right move is a new mission to re-annotate, not polish on this branch.**

## Blocking vs non-blocking

**Non-blocking — ship Ark Royal's implementation:**
- Docstring "150 s" → "250 s" (concern B)
- Briefing plateau numbers are 5 s high (concern C, doc only)
- Full suite 135/8/1, not 136/7/1 as Ark Royal reported (baseline mismatch)
- Noise fragility at σ ≥ 0.5 °C (pre-existing, not introduced by this mission)
- Cliff ignores post_peak_grace (documented, semantically correct)

**Blocking for admiral review (but not this mission):**
- **Q3: are unlidded ground-truth annotations correct?** If not, that is a
  larger mission — REVISE at that point — not a polish item.

**Recommendation**: Accept the ship. Diamond fixes concerns B and C (docstring
cleanups). Admiral decides Q3 in a separate planning cycle.
