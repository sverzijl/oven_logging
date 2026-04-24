# Red-Cell Verdict — HMS Artful

## Verdict: ACCEPT_WITH_NOTES

The three mission deliverables (1759 re-annotated to 3 bakes, `peak_idx+1` guard removed from cliff scan, `_skip_probe_pull_tail` added) are **correct and self-consistent for the 5 real CSVs and 13+ synthetic fixtures exercised**. All 30 boundary tests pass. All perturbation scenarios behave as expected. The 1759 bake-3 start, however, exhibits the **same 10-sample bake_active_c=40 vs 35 drift** as bake 2 but is silently absorbed by `ambiguous=True` + `tolerance=5` — this is a concern worth surfacing but NOT a blocker for this mission.

## Independent test verification

- **30 boundary tests (`tests/test_curve_boundary_detection.py`)**: 30/30 pass.
- **Full suite 3 consecutive runs**: `135/8/1`, `135/8/1`, `136/7/1` — baseline held (8 pre-existing failures in unrelated modules: `test_visualization`, `test_surface_sensor_detection`, `test_curve_comparison_integration`, `test_internal_sensor_filtering`). `test_deep_insertion` flickered once (flake documented across 6 prior missions).
- **`test_deep_insertion` behaviour**: flaked once in 3 runs (1 pass, 2 fail). Matches the known pre-existing intermittent. Unrelated to this mission.

## Central questions

### Q1 — `_skip_probe_pull_tail` side effects on other CSVs — **CLEAN**

Single-curve CSVs remain 1-curve. Detailed skip-tail behaviour (probe `probe_q1_skip_side_effects.py`):

| Fixture | end_idx (cliff) | skip_from | skip_to | tail_length | max VCT in tail | samples >=40 in tail |
|---|---|---|---|---|---|---|
| `real_100098DE_1351` | 306 | 307 | 339 | 1900 | 33.15 °C | 0 |
| `real_1000BA3C_0946` | 293 | 294 | 300 | 0 (EOF) | — | — |
| `post_wonder_meal_lidded` | 344 | — (plateau_fired, skip_probe_pull_tail NOT invoked) | — | — | — | — |
| `wonder_white_10k_lidded` | 338 | — (plateau_fired, skip_probe_pull_tail NOT invoked) | — | — | — | — |

Key finding: on the lidded CSVs the exit candidate that fires is `_candidate_core_peak_plateau` (not cliff), so `cliff_fired=False` and `_skip_probe_pull_tail` is never invoked — exactly as the implementation intends. `_skip_plateau_tail` handles those instead. The two skip functions are cleanly separated by fire-flag.

On the two cliff-firing single-curve CSVs, the skip lands the search well inside the sustained sub-room-temp region, after which `_detect_start` finds no further bake (the remaining tail never crosses bake_active_c=40 again). Zero spurious curves.

### Q2 — Over-skip / dead-zone analysis on 1759 — **CLEAN**

From probe `probe_q2_skip_dead_zone.py`:

Between bake 1 (cliff@293) and bake 2 (start=775):
- `_skip_probe_pull_tail` stops at **idx 307** (VCT=30.40 °C, 3 consecutive sub-35 samples confirmed).
- `_detect_start` scans forward from 307 and fires at idx 775 (VCT=40.00 °C, first sample ≥ bake_active_c=40 with 3-sample confirmation).
- "Dead zone" = 468 samples of real cool-off + quiescent time where VCT < 40. This is NOT a detector dead zone — it's actual bread-free probe-idle time. **Correct behaviour**.

Between bake 2 (cliff@944) and bake 3 (detector=6032, annotation=6022):
- `_skip_probe_pull_tail` stops at idx 962 (VCT=31.30 °C).
- `_detect_start` fires at idx 6032 (VCT=40.15 °C, first sample ≥ bake_active_c=40).
- 5070-sample gap is genuine multi-hour probe idle. No overlap between skip and start.

**Admiral's 766→775 refinement is detector-correct** (detector uses bake_active_c=40; idx 775 is first sample where VCT≥40 with sustained confirm). The skip is *not* what drives the 9-sample shift — the shift is entirely `_detect_start`'s convention.

### Q3 — Bake 3 start (6032 vs 6022) correctness — **DETECTOR IS SELF-CONSISTENT; FIXTURE BAKE-3 STILL USES 35 °C CONVENTION**

From probe `probe_q2_skip_dead_zone.py`:

```
idx=6021  VCT=38.80
idx=6022  VCT=38.85    <-- annotated start (VCT > 35)
idx=6023  VCT=38.95
...
idx=6031  VCT=39.95
idx=6032  VCT=40.15    <-- detector start (VCT >= bake_active_c=40)
```

Detector's `6032` fires on the first sample where VCT ≥ `bake_active_c=40` — **exactly the same 10-sample pattern** as bake 2 (766→775). The detector is **self-consistent**: both bake-2 and bake-3 starts land at bake_active_c=40 with 3-sample confirmation.

The fixture correction raised bake-2's annotation from 766 (VCT > 35) to 775 (VCT ≥ 40) but did NOT raise bake-3's annotation from 6022 (VCT > 35) to 6032 (VCT ≥ 40). Under the strict start-check this would fail with diff=10 > tolerance=5, but `ambiguous=True` suppresses the start assertion for the whole fixture. The ambiguous flag masks the inconsistency.

**Is 6022 or 6032 "right"?** Both are defensible human choices on an ambiguous bake; neither corresponds to a PredictionState transition. **The detector is doing exactly what it does for every other curve in the suite.** Correcting only bake-2 and leaving bake-3 uncorrected is an annotation oversight — not a detector bug.

**Recommendation** (non-blocking): bump bake-3's annotation from 6022 → 6032 for consistency with the detector convention used on bake-2, so the fixture no longer relies on `ambiguous=True` to paper over the drift. This is polish scope (Task 5, HMS Spey).

### Q4 — `CLIFF_MIN_START_TEMP_C` necessity after `peak_idx+1` removal — **STILL NECESSARY (defense-in-depth)**

From probe `probe_q4_cliff_min_start_necessity.py`:

**End-to-end**: disabling the guard (`CLIFF_MIN_START_TEMP_C=0`) produces identical curves on all 5 real CSVs. At the detector-output level, the guard appears redundant with `_skip_probe_pull_tail`.

**Unit-level**, it is NOT redundant:
```
Cliff candidate (guard=OFF) scanning from 294 (inside bake-1 cascade): returns 294
Cliff candidate (guard=ON 80 °C) scanning from 294:                   returns None
```

Idx 294 on 1759 has VCT=76.70 with a 16 °C drop from 293 (VCT=96.75), satisfying the `INSTANT_DROP_THRESHOLD_C=15` and monotonic-confirm checks. Without the 80 °C gate, the candidate would fire inside the post-cliff cascade.

In production this is masked because `_skip_probe_pull_tail` advances `search_from` past idx 294 before the next cliff candidate scan begins. But:
- If a future fixture's cascade decays slowly enough that skip doesn't land past the 80 °C crossing (e.g. a very slow post-pull cooldown), the cliff could fire inside the cascade.
- Inside `_detect_curve_end` the cliff scans **within the current curve** (not post-skip). If a curve started mid-cascade (e.g. synthetic midbake_start, or a pre-warm scenario), the 80 °C gate ensures the cliff doesn't fire inside a still-descending region.

**Verdict**: `CLIFF_MIN_START_TEMP_C=80` is a cheap, physically meaningful guard. Removing it would work on the current fixtures but lose a defense-in-depth layer. **Keep.**

## Perturbation battery

From `probe_perturbation_battery.py`:

### Noise on 1759 (3-curve structure)
- σ=0.05 °C: 30/30 retain 3 curves.
- σ=0.10 °C: 30/30 retain 3 curves.
- σ=0.15 °C: 30/30 retain 3 curves.
- σ=0.30 °C: 30/30 retain 3 curves.

The 3-curve structure is robust — cliffs are large (20–27 °C drops) and well above any noise floor tested.

### Synthetic: two-cliff curve
Constructed a profile with bake 1 → cliff 1 → cold interlude → bake 2 → cliff 2. Detector produces **2 curves** correctly, each ending at its cliff.

### Synthetic: race between cliff-skip and new-start
Constructed a profile where cliff 1 fires, then temperature rapidly climbs back (no quiescent period). Detector produces **2 curves**. `_skip_probe_pull_tail` advances past the brief sub-35 window, and `_detect_start` then finds the re-rise. No merged or lost curves.

### Full-fixture introspection
19 non-raising fixtures probed (`probe_introspect_all.py`). All real CSVs land at expected boundaries. Synthetic mismatches are all tolerance-absorbed by the suite's tolerance / truncation / start-offset conventions (the same pattern documented across 6 prior missions' introspection matrices).

## Duncan's deviations

1. **`_skip_probe_pull_tail` design (mirror of `_skip_plateau_tail`): ACCEPT.**
   - The implementation symmetry with `_skip_plateau_tail` is exactly right — both skip hot tails, both gate on fire-flag, both use a room-temp / bake-active threshold + `_confirm_n`-sample confirmation. Identical shape reduces future-reviewer load.
   - The fast-forward loop (`while temps[j] > _room_temp_max`) followed by the confirm loop is the minimal safe construction: fast path for the dominant case, confirm path for noise-robustness. Not over-engineered.
   - One micro-nit (non-blocking): the confirm loop's `else` branch resets `confirmed=0` AND increments `j` unconditionally. If a noisy sample dips into the sub-room region then spikes back above it, this eats that sample and resumes scanning on the next. This is consistent with `_skip_plateau_tail` but slightly different semantics from a classic "require N consecutive" run (which would reset `confirmed` without advancing). The impact on real data is zero (cooldown is monotonic by physics); documenting the symmetry intent in a comment would help.

2. **Fixture tweak 766 → 775 (admiral-authorized): ACCEPT.**
   - Detector fires at 775 because VCT[775]=40.00 is the first sample where VCT ≥ `bake_active_c=40` with 3-sample confirmation. 766 was the "VCT > 35" estimate from the admiral. Aligning the annotation to the detector's actual threshold convention is correct.
   - **However**, bake 3 should have been migrated the same way (6022 → 6032). Not blocking — `ambiguous=True` + tolerance=5 currently absorb the drift — but it is a latent inconsistency in the fixture. See Q3 recommendation.

## New concerns

### Concern 1 — Bake-3 fixture annotation drift (non-blocking, hand off to Spey)
Bake 3's annotated start (6022) is offset 10 samples from where the detector actually fires (6032), same as bake-2 pre-correction. The ambiguous flag masks it. Recommend updating the fixture annotation from 6022 → 6032 with a rationale line mirroring bake 2's. One-line change, no test churn.

### Concern 2 — Two-guard redundancy on real CSVs (non-blocking, document only)
`_skip_probe_pull_tail` and `CLIFF_MIN_START_TEMP_C=80` both independently prevent the cascade-cliff-misfire scenario on the 5 real CSVs. On these fixtures, either one alone would suffice end-to-end. The guard IS necessary defense-in-depth (Q4 unit-level probe confirms), but this is worth a docstring note: "two lines of defence — skip moves `search_from` past cascade; min_start gate prevents cliff firing in-cascade if a future curve starts inside a cascade".

### Concern 3 — `_skip_probe_pull_tail` interaction with `_probe_cooking_continuous` heuristic (non-blocking)
`_probe_cooking_continuous` fires True on 1759 because its PredictionState never reverts after idx 13. This extends `cool_window` to ~1 hour of quiescence for cool-to-ambient exits, and combines with the skip to produce the 3-curve outcome. If a future CSV has the same firmware-stuck signature AND tight cliff-to-cliff spacing AND a skip that doesn't fully cover the inter-cascade region, the cool-to-ambient candidate could fire inside the long cool_window and absorb the gap. On current fixtures this is not reproducible; documenting the interaction is sufficient.

### Concern 4 — Noise-fragility carryover from prior mission
Prior mission (Ambush) measured σ=0.15 °C causing 27–60% spurious cliff-fire rate on 1759. My probe measures **0/30** wrong curve-count at σ=0.15 °C this mission. The change is the 3-curve annotation: with the now-correct ground truth, spurious cliffs that fire inside actual bake-cooldown windows no longer register as "spurious" — they correctly land on the real third cliff. The prior mission's noise concern was an artifact of the wrong annotation; this mission's re-annotation resolved it by accident. Documenting this would be valuable — the docstring block in `_candidate_probe_pull_cliff` still claims fragility that this mission's annotation correction actually resolved.

## Blocking vs non-blocking

**Blocking: none.** Mission deliverables are correct.

**Non-blocking (hand to Spey / polish)**:
1. Update fixture annotation for bake 3 on 1759: `6022 → 6032` + one-line rationale in description.
2. Docstring note on `_skip_probe_pull_tail` covering the two-layer defense with `CLIFF_MIN_START_TEMP_C`.
3. Docstring update on `_candidate_probe_pull_cliff`: prior mission's noise-fragility claim was annotation-driven, not detector-driven. Consider removing or rewording the fragility warning now that the ground truth is consistent.

**Recommendation**: ACCEPT_WITH_NOTES — Spey can pick up all three concerns as polish.

## Probe scripts saved

- `probe_q1_skip_side_effects.py` — verifies skip behaviour on single-curve CSVs
- `probe_q2_skip_dead_zone.py` — verifies no dead zone between skip and cold-start on 1759
- `probe_q4_cliff_min_start_necessity.py` — verifies `CLIFF_MIN_START_TEMP_C` unit-level necessity
- `probe_introspect_all.py` — full 19-fixture introspection table
- `probe_perturbation_battery.py` — noise + two-cliff + race-condition synthetics
