# HMS Astute — Damage Report

**Mission:** M24 task 2 red-cell verification of Foxhound's isothermal-tracking temporal wrapper
**Artefacts reviewed:** `isothermal-traces-BA3C_0946.png`, `isothermal-data-BA3C_0946.json`, `src/data/spatial_reconstruction/isothermal.py`
**Bake:** ProbeData_1000BA3C_2025-05-30 09_46_16.csv — 46 strides at 30 s

## Verdict: APPROVE-WITH-CONCERNS

Physical traces are sensible. Foxhound's wrapper produces monotone, well-ordered, non-crossing isotherm fronts and a clean sigmoidal core climb. One pre-existing low-confidence label on `fixed_core_x` (declared by the JSON itself) is the only caveat — not introduced by this change.

## Per-check evaluation

### (a) 100 °C front monotone-inward — APPROVE
`isotherm_positions["100.0"]` first appears at stride 5 (t=150 s) at x=0.988 and decreases monotonically every stride to x=0.592 at stride 46 (t=1380 s). Spot checks: 0.988 → 0.952 → 0.922 → 0.901 → 0.882 → 0.865 → 0.847 → … → 0.601 → 0.596 → 0.592. No backsteps in the smoothed array; raw array (`isotherm_positions_raw["100.0"]`) is also monotone non-increasing. Front advances surface→core as expected for the moisture-evaporation Stefan front.

### (b) Isotherm ordering — APPROVE
Verified at every stride where all four are finite (strides 6–46). Representative samples:
- Stride 6 (t=180 s): 60=0.769, 80=0.880, 100=0.952, 110=0.984 → 110>100>80>60 ✓
- Stride 20 (t=600 s): 60=0.421, 80=0.580, 100=0.740, 110=0.792 ✓
- Stride 30 (t=900 s): 60=0.130, 80=0.413, 100=0.693, 110=0.760 ✓
- Stride 37 (t=1110 s): 60=0.0 (clamped, past T1), 80=0.056, 100=0.656, 110=0.751 ✓
- Stride 46 (t=1380 s): 60=0.0, 80=0.0, 100=0.592, 110=0.730 ✓

Once a colder isotherm clamps to 0 (probe-tip saturation), the strict-greater-than degenerates to greater-or-equal between siblings still saturated — physically equivalent to "front off the probe", not a crossing. No genuine crossings observed.

### (c) T_at_fixed_core sigmoidal climb — APPROVE
Starts at 34.35 °C, climbs monotonically every stride to 96.5 °C at stride 46. Three regimes visible:
- **Slow lag** strides 1–15 (34.35 → 37.2 °C, ~0.2 °C/stride)
- **Fast rise** strides 20–35 (38.4 → 73.6 °C, ~2.4 °C/stride)
- **Plateau onset** strides 40–46 (92.1 → 96.5 °C, ~0.7 °C/stride decelerating to ~0.5)

Never exceeds 100 °C — consistent with latent-heat-suppressed core. Strictly non-decreasing. The 34 °C start (rather than ~22 °C room-temp) is mild — bake CSV evidently begins after the dough has equilibrated in the prover, not from cold. Not a defect.

### (d) Artefacts — APPROVE-WITH-CONCERNS
- **No isotherm crossings.**
- **Max stride-to-stride jump** in smoothed array: 60 °C front stride 32→33 (0.0735→0.0231, Δ=0.050) and 80 °C front stride 36→37 (0.156→0.056, Δ=0.100). Both well under the 0.2-unit flag threshold and occur as the front saturates at the probe tip — physically expected acceleration, not noise.
- **Positions ∈ [0, 1]:** all values bounded; surface-side max 0.988, core-side min 0.0. Clamp to 0 when front passes T1 is per `isothermal.py` lines 405–411 (smoothed clamp on contiguous finite runs).
- **T_at_fixed_core monotone:** verified across all 46 strides, no mid-bake drops.

**Concern (pre-existing, not Foxhound's regression):** the JSON self-reports `core_confidence: "low"` with `core_reason: "extrapolated past probe tip: relaxed parabolic clamp places core at x=-0.0414"`. `fixed_core_x` is then clamped to 0.0 as documented at `src/data/spatial_reconstruction/isothermal.py:317-319`. This means `T_at_fixed_core_t` is being reported at the probe tip rather than at the geometric core, so the absolute temperatures (especially the 96.5 °C terminal value) are an upper bound on the true core T — true geometric core would be ~1.4% deeper and slightly cooler. The label is preserved through to the operator-facing metadata, which is the correct behaviour. Recommend operator-side bake-metadata input (per `core_reason`) for high-accuracy runs; no code change needed for this mission.

## Sign-off

Foxhound's isothermal-tracking wrapper passes all four physical-sanity checks. The implementation in `_find_isotherm_position` (surface→core walk with linear interpolation), `_smooth_savgol_contiguous` (per-run SavGol with [0,1] clamp), and the `fixed_core_x = clip(raw_core_x, 0, 1)` guard are all defensible. Approve for merge. Track the low-confidence-core caveat against the existing M2a follow-up for operator metadata input — not a Foxhound regression.

— HMS Astute, M24 red-cell
