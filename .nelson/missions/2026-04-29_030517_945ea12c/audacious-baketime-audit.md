# HMS Audacious — Bake-Time-to-Physics Audit (M19, Task 1)

## Step 1 — Geometry inputs (anchored)

| Input | Value | Source |
| --- | --- | --- |
| Bake time t | 22-25 min (1320-1500 s) | User confirmed real bake |
| Probe span T1-T8 | 95 mm | Crew briefing |
| Probe insertion (min) | 54 mm | Crew briefing |
| Loaf height | 100-130 mm | Sandwich tin |
| Slab half-thickness L | 40-65 mm typical (one-side insulated tin -> L_eff = full loaf thickness 100-130 mm) | Geometry |
| T_oven | 200-240 deg C | Crew briefing |
| T_initial | 22-25 deg C | Crew briefing |
| Target T_core | 93-98 deg C | `config/constants.py:TEMPERATURE_ZONES.TARGET_CORE` |
| theta_centre = (95-200)/(22-200) | 0.59 | Dimensionless |

The tin floor is insulated/poorly-conductive relative to the open top, so the loaf behaves as a slab of length L = loaf_height (one-sided heating). Half-thickness L for the symmetric-slab equivalent therefore lies in 50-65 mm (loaf 100-130 mm).

## Step 2 — Implied effective alpha

Two regimes:

* **tau ~ 1** (centre approaches surface T): alpha = L^2 / t. Aggressive upper bound.
* **Heisler chart, theta_c = 0.59, Bi >> 1**: Fo ~ 0.35 -> alpha = 0.35 L^2 / t. Realistic lower bound.

| L (mm) | t (min) | alpha (tau=1) m^2/s | alpha (Heisler) m^2/s |
| ---: | ---: | ---: | ---: |
| 40 | 22 | 1.21e-6 | 4.24e-7 |
| 40 | 25 | 1.07e-6 | 3.73e-7 |
| 50 | 22 | 1.89e-6 | 6.63e-7 |
| 50 | 25 | 1.67e-6 | 5.83e-7 |
| 60 | 22 | 2.73e-6 | 9.55e-7 |
| 60 | 25 | 2.40e-6 | 8.40e-7 |
| 65 | 22 | 3.20e-6 | 1.12e-6 |

**Implied alpha_eff range = 4e-7 to 3e-6 m^2/s.** Best central estimate (L=55 mm, t=23 min, Heisler) ~ **8e-7 m^2/s**. Notice the wide span: alpha is quadratic in L. If we mis-estimate the effective slab thickness by ~30%, alpha doubles.

### Comparison vs missions

| Mission | alpha used / fitted (m^2/s) | Bound? | Consistent with 22-25 min? |
| --- | --- | --- | --- |
| M9 Stefan baseline (literature/SI) | 1.4e-7 (dough), 1.0e-7 (crust) | hard-pinned literature | **TOO LOW by 3-20x** |
| M9 Stefan phase3 free joint fit | 3.6e-4 (dough!), 1.1e-3 (crust) | optimiser scaling-bug regime | **TOO HIGH by ~100x** (clearly mm^2/s units, not SI) |
| M11/M12 Zurcher (k_d, k_c only) | not directly param'd alpha; effective alpha ~ k/(rho c) ~ 0.2/(700*2500) = 1.1e-7 | implicit | **TOO LOW by 5x** |
| M14 Luikov inverse | alpha pinned at **1.4e-7** | hard pin | **TOO LOW by 5x** |
| M15 Luikov-tin | inherited alpha = 1.4e-7 (Ko/Bi non-dim) | hard pin | **TOO LOW by 5x** |
| M17 Endeavour 6-param | alpha_pre **fit = 4.91e-6** at upper bound 5.0e-6 | **at hi bound** | Optimiser pushed against the cap to reach 22-25 min bake; bound is barely-large-enough |

Stefan phase3 "joint" alpha values (~9.5e-4) are in mm^2/s, equal to ~9.5e-10 m^2/s in SI -- absurdly low. They are also fit-pathological (one fixture has alpha=1705!). The "phase3.pinned" lit_si values (1.4e-7) confirm M9 hard-pinned literature dough alpha at 1.4e-7 m^2/s.

## Step 3 — Biot and Stefan (Kossovich)

**Bi = h L / k**, k = 0.4 W/m/K (dough):

| L (mm) | h=30 | h=60 | h=100 |
| ---: | ---: | ---: | ---: |
| 40 | 3.0 | 6.0 | 10.0 |
| 50 | 3.75 | 7.5 | 12.5 |
| 60 | 4.5 | 9.0 | 15.0 |

**Implied physical Bi range = 3 to 15** (top side, with combined radiation+convection at 200 deg C).

**Ste = c dT / (Lv w)** = 2000 * 200 / (2.26e6 * 0.4) = **0.443**.
**Ko = 1 / Ste = 2.26.** Latent stored per unit mass equals ~2.26x the sensible heating budget -- evaporation is dominant.

### Comparison vs missions

| Mission | Bi_top | Ko | Bound at? |
| --- | --- | --- | --- |
| M11 Zurcher v1 | not Bi-parametrised | Ko fitted: most fixtures **at 30 (hi bound)** or 0.10 (lo bound) | **at bounds** |
| M12 Zurcher v2 | similar | Ko 7.8-30, mostly at hi=30 | **at hi bound** |
| M14 Luikov | Bi bounds (0.1, 50); fitted ~1-3 | Ko fitted 0.93-3.33 (truth=4.0) | interior |
| M15 Luikov-tin synthetic | Bi_top truth=8 -> fitted 7.4-12.2 | truth Ko=5 -> fitted 3.1-4.4 | interior |
| M15 Luikov-tin BA3C_0946 | Bi_top fitted **6.7** (bounds 0.5-500) | Ko fitted 3.6 | **interior** |
| M17 Endeavour | uses observed h_eff(t) extracted | not Ko-paramd | -- |

**Bi observation: M15 fitted Bi_top = 6.7 (bounds 0.5-500). 6.7 sits right in the middle of the physical range (3-15). Bi was NOT bound-limited.** This contradicts the briefing's hypothesis that "Bi_top hit the upper bound on M15".

**Ko observation: Zurcher M11/M12 Ko values pegged at hi=30 are 13x larger than physical Ko = 2.3. The Zurcher parametrisation was free-fitting a non-physical Ko, then bouncing off whatever bound was nearest.**

## Step 4 — Audit verdict per mission

| Mission | alpha right? | Bi right? | Ko right? | True failure mode |
| --- | --- | --- | --- | --- |
| M9 Stefan (lit-pinned phase) | NO (1.4e-7 vs needed 8e-7, 5x low) | n/a | implicit via rhoL_eff | alpha too small => model underbakes; freezing underprediction below 6 deg C floor consistent with too-slow conduction. |
| M9 Stefan (free phase3) | NO (unit-bug: 1e-3 mm^2/s) | n/a | rhoL_eff fitted | unit confusion; "best result" claim because joint fit absorbed magnitude error into rhoL_eff. |
| M11 Zurcher v1 | implicit alpha ~ 1e-7 (5x low) | n/a | Ko at bound | alpha too low AND Ko unphysical. |
| M12 Zurcher v2 | same as M11 | n/a | Ko at bound | same. |
| M14 Luikov | NO, pinned at 1.4e-7 | interior | interior | alpha too small. |
| M15 Luikov-tin | NO, pinned alpha (1.4e-7) | **interior, fitted 6.7 -- physical** | interior | alpha 5-7x too low; model could not bake in 25 min so attributed signal to other parameters. |
| M17 Endeavour | freed alpha_pre, hit **4.9e-6** at hi bound 5e-6 | uses observed h | -- | alpha bound 5e-6 is BARELY large enough. Optimiser is rail-pinned. |

### Verdict

**The systematic bug is alpha, not Bi or Ko.**

* The 22-25 min bake time **requires** alpha_eff in the range **4e-7 to 3e-6 m^2/s**, with central estimate ~**8e-7 m^2/s**.
* M9, M11, M12, M14, M15 all used (or implied) alpha = 1.0-1.4e-7 m^2/s -- **5-7x too small**. With alpha that low, Fo at 25 min is only 0.07-0.10 (with L=55 mm), so the centre simply cannot heat past ~50 deg C in the model. This is exactly the "6 deg C floor" symptom: when the physics model's centre rises slowly, residuals against real fast-baking data accumulate at the centre node.
* M15 Bi_top = 6.7 was **not** bound-limited. The Bi physics was right; the alpha was wrong.
* M17 freed alpha_pre and the optimiser ran straight to the upper bound (4.91e-6 of cap 5.0e-6). This is the smoking gun: **with literature-pinned alpha ~1.4e-7 the model literally cannot fit a 22-25 min bake; M17 confirmed this empirically by demanding 35x larger alpha**.
* Ko on Zurcher (M11/M12) hitting hi=30 is a **separate** unphysical-parameter bug -- the physical Ko is 2.26, so Ko=30 means Zurcher's fitter was using Ko as an absorption coefficient for unrelated mismatch, not as the Kossovich number.

### One-line recommendation

Re-run M9/M14/M15 with alpha (or alpha_pre) freed in **(5e-7, 1e-5)** (not pinned at 1.4e-7 and not capped at 5e-6). Expect the optimiser to settle at **6e-7 to 3e-6**, removing the 6 deg C floor failure. The literature value 1.4e-7 m^2/s is for **raw dough at room temperature**; effective alpha during baking is dominated by evaporation-condensation-driven enthalpy transport (Datta, de Vries) and is order ~1e-6 m^2/s, exactly what M17 found.
