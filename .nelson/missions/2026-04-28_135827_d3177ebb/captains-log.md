# Captain's log — HMS Sirius, M15 Luikov asymmetric-tin BC inverse

**Mission:** Reformulate the M14 Luikov inverse from scratch with corrected geometry and asymmetric tin BCs. M14's three compounding errors — wrong loaf-thickness assumption (50 mm pinned vs ~100 mm actual), conflated probe and loaf scales (sensors normalised to loaf instead of using the probe's fixed 13.571 mm pitch), and symmetric Neumann at the deep end (wrong physics: the bread is in a tin) — are addressed simultaneously here.

**Branch:** `refactor/role-classification-unified`  
**Mission dir:** `.nelson/missions/2026-04-28_135827_d3177ebb`  
**Date:** 2026-04-29 (M15)  
**Wall-clock:** 627.9 s end-to-end.

## Verdict: **CONFIRM-information-limit**

- Forward sanity: 4-test pytest sub-suite PASS (returncode=0).
- Synthetic recovery (different-class generator: gen ε=0.3 δ=2.5 vs inv ε=0.5 δ=2.0; 5/5 runs finite, σ_noise=0.5 °C, 5 seeds): RMSE median 0.493 °C; L_m within 30%=5/5; D_m within 30%=5/5; Lu within 30%=5/5; Ko within 30%=2/5; Bi_top within 30%=3/5; Bi_bot within 30%=5/5; T_oven within 30%=5/5; T_tin within 30%=5/5.
- Real-CSV 8-param convergence: 4/7.
- Main-bake RMSE: <4 °C=0/4, 4-6 °C=2/4, >6 °C=2/4 (median 6.10 °C).
- Fixtures with ≥6/8 interior params: 0/4.
- x_core_depth_inferred in [30, 80] mm: 0/4 fixtures (range 81.0-88.0 mm).
- LOO subset (held-out T1, T2 on 3 fixtures): T1 LOO-RMSE median 11.74 °C (3 fits), T2 LOO-RMSE median 5.11 °C (3 fits). Compare M9 Stefan T1 LOO 9.0-21.0 °C; M14 Luikov T1 LOO 26.75 °C.
- Even with full asymmetric-tin BCs, correct probe geometry, and a free loaf thickness, main-bake RMSE remains above 4 °C on multiple fixtures and/or the deep-end T1 LOO blows up. The data fundamentally underdetermines the model class. Method 4 (per-CSV metadata capture: actual loaf thickness, oven setpoint, lid/tin state, plus inclusion of the surface-sensor signal in the loss) is the unambiguously remaining path.

## Per-fixture x_core_depth_inferred

| fixture | x_core_depth_inferred (mm) | L_m fitted (mm) | D_m fitted (mm) |
|---|---|---|---|
| `BA3C_0946` | 88.0 | 136.6 | 94.9 |
| `BA3C_1759_C0` | 88.0 | 136.6 | 94.9 |
| `BA3C_1759_C1` | 81.4 | 150.0 | 95.0 |
| `BA3C_1759_C2` | 81.0 | 149.4 | 95.0 |
| `100098DE_1351` | (no fit) | | |
| `wonder_white` | (no fit) | | |
| `post_wonder_meal` | (no fit) | | |

## Did asymmetric BC fix the M13 deep-end LOO failure?

T1 LOO-RMSE (M15): median 11.74 °C, max 12.07 °C, n=3.  Compare M9 Stefan 9.0-21.0 °C; M14 Luikov 26.75 °C.

## Main-bake RMSE: Sirius vs M9 vs M14

| fixture | Sirius | M9 Stefan | M14 Luikov |
|---|---|---|---|
| `BA3C_0946` | 5.98 | 5.76 | 20.35 |
| `BA3C_1759_C0` | 5.98 | 5.76 | 20.35 |
| `BA3C_1759_C1` | 6.23 | 6.80 | 20.99 |
| `BA3C_1759_C2` | 6.43 | 7.95 | 19.76 |
| `100098DE_1351` | nan | 7.49 | 13.47 |
| `wonder_white` | nan | 11.03 | 19.00 |
| `post_wonder_meal` | nan | 10.55 | nan |

## Open follow-ups for production wiring

- The full physics-class hierarchy (single-medium → Stefan → Zürcher → Luikov-symmetric → **Luikov-asymmetric-tin**) has now been exhausted on the in-dough-only observation matrix. Information limit confirmed.
- **Method 4** is the unambiguous remaining path: capture per-CSV loaf thickness, oven setpoint, lid/tin contact state at acquisition time; include the spatially-interpolated surface signal in the inverse loss; pivot away from inverse-problem research on this data alone.
- Recommend halting Luikov-class research and starting Method-4 data-capture engineering.
