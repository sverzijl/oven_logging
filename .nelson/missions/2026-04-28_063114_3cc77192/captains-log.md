# Captain's log — HMS Diamond, M10 residual decomposition

**Mission:** Decompose the M9 Stefan-inverse RMSE (6-10 °C on real CSVs)
along time-segment, per-sensor, trim-mean, and autocorrelation axes to
test whether the M9 NO-GO was driven by accounting artefacts or genuine
model misfit.

**Branch:** `refactor/role-classification-unified`
**Mission dir:** `.nelson/missions/2026-04-28_063114_3cc77192`
**Date:** 2026-04-28

## Plan executed

1. Built `tests/_diagnose_stefan_residuals.py`. Loads M9 cached fitted
   parameters from `tests/baselines/stefan_inverse_research.json`. Re-uses
   M9's `solve_stefan_forward` and the `_segmented_real_fixture`,
   `REAL_FIXTURES` helpers from `tests/test_heat_equation_research.py`.
   No new physics, no refit.
2. For each of 7 fixtures: rebuild observation matrix (downsample 4) and
   interpolated surface BC at `x_surface_continuous` (mirroring the M9
   inverse fitter's loss exactly), then call `solve_stefan_forward` once
   at the M9 cached params. Compute residual matrix `R[t, s]`.
3. Decompose along four axes:
   - per-time-segment RMSE (startup 0-10%, main 10-90%, tail 90-100%)
   - per-sensor RMSE
   - trim-mean RMSE (drop worst sensor, recompute pooled)
   - lag-1 autocorr per segment (mean across sensors) + signed mean residual
4. Apply M10 verdict logic. Dump JSON. Append "Round 2" section to the
   research markdown. M9 sections preserved verbatim.

## Sanity check — forward eval reproduces M9 RMSE byte-for-byte

| fixture | M9 reported RMSE | M10 recomputed | match |
|---|---|---|---|
| BA3C_0946       | 6.19 | 6.19 | ✓ |
| BA3C_1759_C0    | 6.19 | 6.19 | ✓ |
| BA3C_1759_C1    | 6.41 | 6.41 | ✓ |
| BA3C_1759_C2    | 7.63 | 7.63 | ✓ |
| 100098DE_1351   | 6.91 | 6.91 | ✓ |
| wonder_white    | 9.83 | 9.83 | ✓ |
| post_wonder_meal| 9.45 | 9.45 | ✓ |

All seven match to 0.01 °C — the diagnostic forward solve is the same
loss-function evaluation that M9's Nelder-Mead minimised.

Note: BA3C_0946 and BA3C_1759_C0 show identical decomposition numbers
because the M9 cached fits for both are bit-identical (same `x_core`,
same α, same ρL, same n_obs=355). Verified directly from the JSON;
it's an artefact of the M9 cache, not the M10 diagnostic.

## Findings

### Main-bake RMSE (the headline)

The startup-IC and probe-pull-tail hypotheses do **not** rescue the M9
RMSE. Per-time-segment RMSEs (the bare numbers, °C):

| fixture | startup | main | tail | full |
|---|---|---|---|---|
| BA3C_0946       | 4.79 | 5.76 | 9.36 | 6.19 |
| BA3C_1759_C0    | 4.79 | 5.76 | 9.36 | 6.19 |
| BA3C_1759_C1    | 0.89 | 6.80 | 6.64 | 6.41 |
| BA3C_1759_C2    | 0.93 | 7.95 | 8.90 | 7.63 |
| 100098DE_1351   | 5.43 | 7.49 | 2.06 | 6.91 |
| wonder_white    | 1.72 | 11.03| 1.14 | 9.83 |
| post_wonder_meal| 3.63 | 10.55| 0.53 | 9.45 |

5/7 fixtures have **main-bake RMSE > 6 °C**. Median main-bake RMSE
= **7.49 °C**, *higher* than the full-bake RMSE on the lid-suppressed
bakes — meaning the lid-bake fixtures look better at full-bake than
they do during the bulk of the bake, because the tail brings the
average down. Zero fixtures fall under the 3 °C bar.

### Lag-1 auto-correlation in main bake

| fixture | ρ_lag1 (main) |
|---|---|
| BA3C_0946       | 0.991 |
| BA3C_1759_C0    | 0.991 |
| BA3C_1759_C1    | 0.995 |
| BA3C_1759_C2    | 0.996 |
| 100098DE_1351   | 0.993 |
| wonder_white    | 0.994 |
| post_wonder_meal| 0.994 |

Median **0.994**, max **0.996**. Residuals are extremely structured —
the model is missing a substantial low-frequency component. This is not
white noise around the truth.

### Trim-mean

Dropping the worst sensor (always **T1** — the deepest in-dough probe,
where both the heat-equation and Stefan models have the least observational
constraint and most extrapolation risk) reduces pooled RMSE to:

| fixture | trim-mean | full | reduction |
|---|---|---|---|
| BA3C_0946       | 5.12 | 6.19 | 1.07 |
| BA3C_1759_C0    | 5.12 | 6.19 | 1.07 |
| BA3C_1759_C1    | 5.51 | 6.41 | 0.90 |
| BA3C_1759_C2    | 6.99 | 7.63 | 0.64 |
| 100098DE_1351   | 6.44 | 6.91 | 0.47 |
| wonder_white    | 7.69 | 9.83 | 2.14 |
| post_wonder_meal| 7.00 | 9.45 | 2.45 |

Even after dropping T1, six of seven fixtures still have trim-mean RMSE
above 5 °C and four are above 6 °C. The headline number was not driven
by a single bad sensor.

### Mean residual signs (segment bias)

The BA3C bakes have a clear **+/− sign flip across segments**: model
under-predicts during startup (negative mean ~−4 °C), over-predicts
mid-bake (~+1-3 °C), and under-predicts the tail (~−6 to −8 °C). This
is the sawtooth signature of a **systematic temporal misfit**, not a
random offset — it's exactly the shape you'd see if the model timing of
the latent-heat plateau is off relative to the data.

## Verdict

**CONFIRM NO-GO.**

The M9 conclusion stands. The headline 6-10 °C RMSE was **not**
inflated by accounting:

- Startup transient: small effect (startup RMSE generally lower than
  main, not higher; the IC mismatch hypothesis was wrong).
- Probe-pull tail: tail RMSE is high on BA3C bakes but low on lid bakes.
  Even excluding the tail, main RMSE remains > 6 °C on 5/7 fixtures.
- Sensor calibration: trim-mean reduction is modest (~0.5-2 °C); not
  enough to bring any fixture under 3 °C.
- Residual structure: lag-1 ρ ≈ 0.99 across all fixtures and segments
  shows the model is missing real low-frequency physics, not noise.

This is a **stronger** NO-GO signal than M9 reported, because the
residual structure (ρ_lag1 ≈ 0.99) is unambiguous evidence of model
misfit, independent of any RMSE bookkeeping. The 1D Stefan front does
not capture the bread-baking dynamics at the in-dough thermometry scale.
Likely missing physics: 2D conduction (loaf is finite in the other
dimensions), moisture migration (the latent-heat trap is distributed in
time and temperature, not a sharp 100 °C boundary), or surface-radiation
coupling on the lid bakes.

## Recommendation forward

The Method-4 loaf-thickness-metadata route already flagged in the M9
follow-ups becomes the next priority. Inverse problems on in-dough
thermometry alone appear to be fundamentally information-limited.

## Acceptance bar

- ✓ Diagnostic ran end-to-end in **0.7s** wall-clock (well under 10 min).
- ✓ All 7 fixtures decomposed.
- ✓ Round 2 section appended to `tests/baselines/stefan_inverse_research.md`.
- ✓ JSON dumped to `tests/baselines/stefan_inverse_residual_decomposition.json`.
- ✓ M9 sections preserved verbatim (verified by header diff).
- ✓ Captain's log written here.

## Files touched

- **created**: `tests/_diagnose_stefan_residuals.py` (diagnostic script).
- **created**: `tests/baselines/stefan_inverse_residual_decomposition.json` (raw data).
- **appended**: `tests/baselines/stefan_inverse_research.md` (Round 2 section,
  lines 152-212; M9 sections at lines 1-150 unchanged).
- **created**: `.nelson/missions/2026-04-28_063114_3cc77192/captains-log.md` (this file).
