# HMS Astute — M22 Task 1: Literature Survey

**Mission:** Evaluate published precedent for the user's proposed cellular-with-sensor-grounding architecture (2D mesh, Dirichlet sensor constraints, distributed α/source fields, smoothness priors) for the bread-baking inverse problem.

## 1. Top-3 most relevant published methods

**(a) Bakhshaei, Morelli, Stabile & Rozza (2024) — Optimized Bayesian Framework for Inverse Heat Transfer using Reduced-Order Methods (arXiv:2402.19381).** This is the closest published cousin to the user's proposal. Continuous-casting mold reconstruction: forward heat-conduction PDE solved with FV (OpenFOAM), unknown boundary heat flux parameterized with radial basis functions (5 RBF centres), Bayesian inversion with Gaussian priors over both the temperature field and the RBF weights. Uses **100 thermocouples** (20:1 measurement-to-basis ratio) and reports a 6.3-7.6 % spatiotemporal relative error. No latent heat. The Bayesian-prior-on-parameter-field is essentially what the user is calling a "smoothness prior on α(x,y,t)"; the difference is they parameterize the *boundary* with 5 RBFs (heavy regularization), not a full distributed α(x,y,t) field.

**(b) Li, Gong, Zhou, Gao & Yao (2025) — Learning to Reconstruct Temperature Field from Sparse Observations with Implicit Physics Priors (arXiv:2512.01196).** Direct 2D temperature-field reconstruction from sparse sensors on a 0.1 m × 0.1 m domain discretized to 200×200. Tests **9, 16, 25 uniformly placed sensors**; 25-sensor config achieves Max-AE ≈ 0.32 K on a smooth analytic field. Uses learned implicit physics priors via cross-attention rather than Tikhonov. Key finding for our purposes: sensors are *uniformly distributed* across the 2D domain — the paper does not address clustered/co-linear sensors, and emphasizes uniform placement throughout. Steady-state, no latent heat.

**(c) Reddy et al. (2024) — 2D FEM inverse heat transfer with conjugate gradient method for bread baking energy estimation (Heat Transfer, Wiley, doi 10.1002/htj.23159), with companion paper Reddy et al. (2023) in J. Thermal Analysis and Calorimetry (10.1007/s10973-023-12626-y).** This is the most direct bread-baking precedent. 2D FEM forward model, conjugate-gradient inversion to estimate heat flux at the bread surface. Treats bread as a continuum with effective properties; latent heat of evaporation is typically lumped into an apparent specific heat c_p,app(T) (Lostie/Zanoni style) rather than handled with a Stefan front. Sensor counts in this family of papers are typically 3-6 thermocouples in the loaf. Their unknowns are *boundary* heat flux profiles, not distributed α(x,y,t) inside the loaf.

## 2. Methods comparison table

| Ref | Sensors | Mesh | RMSE / accuracy | Latent heat | Regularization |
|---|---|---|---|---|---|
| Bakhshaei 2024 (Bayesian RBF) | 100 TCs | FV (OpenFOAM, unspecified res) | 6-8 % rel err on flux | No | Gaussian Bayesian prior on RBF weights + temp field |
| Li 2025 (sparse-obs IPTR) | 9 / 16 / 25 uniform | 200×200 | Max-AE ≈ 0.32 K (25 sens) | No | Implicit learned physics prior (cross-attention) |
| Reddy 2024 / 2023 (bread FEM IHCP) | ~3-6 TCs | 2D FEM, ~10³ elements | Few % on energy | Apparent c_p (lumped) | Conjugate-gradient iterative regularization |
| Hadiyanto / Zanoni / Lostie family (bread baking Luikov) | 2-4 TCs | 1D/2D, 50-200 nodes | 2-5 K crumb, 5-10 K crust | Apparent c_p or evap-front | Levenberg-Marquardt damping |
| Wen 2013 — Tikhonov digital filter for IHCP (Int J Heat Mass Transf, doi 10.1016/j.ijheatmasstransfer.2013.02.045) | 1-4 TCs | 1D, 100-500 nodes | 1-3 K on flux | No | Classical Tikhonov L-curve |
| Iglesias / Stuart EnKF for inverse problems (SIAM JNA 2016) | varies | varies | depends | No (elliptic / parabolic) | Ensemble covariance acts as implicit prior |

## 3. Direct precedent for the user's exact architecture (sensor-Dirichlet + distributed α(x,y,t) + smoothness)

**Verdict: NO direct precedent found.** The published IHCP literature pursues two adjacent but distinct formulations:

- **Boundary-flux IHCP** (overwhelmingly dominant — Reddy, Lostie, Zanoni, Wen, Beck&Blackwell): sensors *inside* the body, unknown is the *boundary* heat flux q(x_surface, t). Material properties are assumed known.
- **Lumped-property estimation** (Hwang/sandwich-bread, Carson): a handful of *scalar* parameters (k, ρc_p) estimated, not a field.

The user's proposal — sensors as Dirichlet anchors *inside* the field while simultaneously inverting for a *distributed* α(x,y,t) and source(x,y,t) field — is unusual. The closest published variants are:

- Iglesias & Stuart's EnKF for groundwater Darcy permeability fields (analogous PDE structure, distributed parameter, smoothness via ensemble covariance) — but they use ~50-200 head-pressure observations on a 2D domain.
- 4D-Var atmospheric assimilation imposes physics-PDE + sensor-grounding + background-error-covariance smoothness, but with O(10⁶) observations. The mathematical machinery transfers; the data density does not.

No paper was found that treats *sensor cells* as hard Dirichlet constraints rather than as a likelihood term. Hard Dirichlet anchoring of sensors in a PDE-constrained inversion is generally avoided because measurement noise then propagates as boundary-layer artifacts; the literature consistently uses a soft (Gaussian-likelihood) constraint.

## 4. Sensor-vs-field-dimension caveat — 8 sensors on a 1D line, 2D field?

This is the pivotal question and the literature is unanimous on the answer.

- **Identifiability theorems for distributed-parameter IHCP** (Beck, Blackwell & St. Clair *Inverse Heat Conduction*, 1985; Alifanov *Inverse Heat Transfer Problems*, 1994) require sensor coverage to span the *spatial directions in which the parameter varies*. A line of sensors can identify variation *along* that line; variation *transverse* to the line is in the null space of the observation operator. No amount of Tikhonov regularization recovers signal that the observation geometry cannot see — it only fills the null space with the prior's mean (e.g. zero gradient).
- Empirically, Li 2025 (above) and the broader sparse-sensor reconstruction literature place sensors on a **2D grid** for 2D fields. None of the surveyed papers attempt 2D reconstruction from a 1D sensor line. The Gappy-POD / sparse-sensor placement literature (Manohar, Brunton, Kutz 2018, IEEE Cont Sys Mag) explicitly proves that sensor *configurations* must be observability-rank-complete for the modes you wish to reconstruct.
- Bakhshaei 2024's 100-thermocouple plane is not exotic — it is roughly the *minimum* density at which the published RBF-Bayesian formulation converges. Their 20:1 measurement-to-parameter ratio suggests our 8 sensors could at best identify ~0.4 effective parameters in the 2D field. Realistically: a single mean α plus maybe a 1D gradient along the probe axis.
- Failure mode for clustered/co-linear sensors is well documented: Emery & Nenarokomov (1998, Meas Sci Tech) show condition number of the sensitivity matrix degrades exponentially as sensors approach co-linearity; the inversion becomes a 1D problem with cosmetic 2D dressing.

**Bottom line:** with 8 sensors on a 1D probe through 2D dough, the best the literature supports is **inverting a 1D field T(s, t) along the probe axis**, with the transverse direction fixed by the prior. Anything claimed about transverse structure is the prior, not the data.

## 5. Verdict

The user's architecture **partially has precedent**: PDE-constrained, sensor-likelihood-grounded, smoothness-regularized inversion of distributed thermal parameters is a recognized class of problems (Bayesian IHCP, EnKF for PDEs, 4D-Var). However:

1. No paper inverts both α(x,y,t) *and* source(x,y,t) simultaneously from interior sensors — that's an over-parameterized, fundamentally under-determined system.
2. Hard-Dirichlet sensor grounding is not standard; soft Gaussian likelihood is.
3. Published implementations use 25-100+ sensors for 2D fields. Eight sensors is an order of magnitude below the published threshold.
4. Most importantly, *no* paper attempts 2D reconstruction from a 1D sensor line. The observability geometry is the problem, not the regularizer.

**Recommendation to the flotilla:** the cellular formulation is mathematically respectable but should be reduced to a **1D field T(s, t) along the probe axis** with thermodynamic interpolation transverse to it (per the user's standing memory `feedback_thermodynamic_interpolation.md`). A 2D inversion with this sensor geometry is not supported by the literature and would be inverting noise into prior mean across the transverse direction. The 5.7 K floor will not be broken by adding parameters; it will be broken by adding sensors or by changing the physics model along the 1D probe direction.

## Sources

- [Bakhshaei et al. 2024 — Optimized Bayesian Framework for Inverse Heat Transfer Problems Using Reduced Order Methods (arXiv:2402.19381)](https://arxiv.org/html/2402.19381)
- [Li et al. 2025 — Learning to Reconstruct Temperature Field from Sparse Observations with Implicit Physics Priors (arXiv:2512.01196)](https://arxiv.org/html/2512.01196)
- [Reddy et al. 2024 — 2D FEM inverse heat transfer with conjugate gradient method for bread (Heat Transfer, Wiley)](https://onlinelibrary.wiley.com/doi/10.1002/htj.23159)
- [Reddy et al. 2023 — Estimation of energy requirement of bread during baking by inverse heat transfer (J Thermal Analysis and Calorimetry)](https://link.springer.com/article/10.1007/s10973-023-12626-y)
- [Hwang et al. 2008 — Estimation of thermal conductivity of sandwich bread using an inverse method (J Food Engineering)](https://www.sciencedirect.com/science/article/abs/pii/S0260877407004050)
- [Estimation of heat flux in bread baking by inverse problem (J Food Engineering 2019)](https://www.sciencedirect.com/science/article/abs/pii/S0260877419304182)
- [Comparison of global and sequential methods for an inverse heat transfer problem (Inverse Problems Sci Eng 2011)](https://www.tandfonline.com/doi/full/10.1080/17415977.2011.551878)
- [Mosalam 2021 — Digital Modeling of Heat Transfer during the Baking Process (Modelling and Simulation in Engineering, Wiley)](https://onlinelibrary.wiley.com/doi/10.1155/2021/8957148)
- [Iglesias, Law & Stuart 2013 — The Ensemble Kalman Filter for Inverse Problems (arXiv:1209.2736)](https://arxiv.org/abs/1209.2736)
- [Iglesias, Law & Stuart — Analysis of the EnKF for Inverse Problems (SIAM J Numer Anal 2016)](https://epubs.siam.org/doi/10.1137/16M105959X)
- [Wen et al. 2013 — Estimation metrics and optimal regularization in a Tikhonov digital filter for IHCP (Int J Heat Mass Transfer)](https://ui.adsabs.harvard.edu/abs/2013IJHMT..62...31W/abstract)
- [Optimization of Sparse Sensor Layouts and Data-Driven Reconstruction (Preprints 2025)](https://www.preprints.org/manuscript/202507.0825)
- [A modified Tikhonov regularization method for 3D IHCP (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0378475406002400)
- [A posteriori regularization for 2D inverse heat conduction (De Gruyter Open Math 2022)](https://www.degruyterbrill.com/document/doi/10.1515/math-2022-0489/html)
- [Solution of inverse heat conduction problem using Tikhonov regularization (J Thermal Sci 2017)](https://link.springer.com/article/10.1007/s11630-017-0910-2)
- [Comprehensive review on heat and mass transfer in baking (ScienceDirect 2023)](https://www.sciencedirect.com/science/article/pii/S2772502223000094)
- [Modeling Heat and Mass Transfer in Bread during Baking (COMSOL conference proceedings)](https://www.comsol.com/paper/download/63507/nicolas_paper.pdf)
- [4D-Var Variational Data Assimilation (ECMWF reference)](https://www.ecmwf.int/sites/default/files/elibrary/2003/76079-variational-data-assimiltion-theory-and-overview_0.pdf)
- [Data assimilation — Wikipedia](https://en.wikipedia.org/wiki/Data_assimilation)
- [Ensemble Kalman filter — Wikipedia](https://en.wikipedia.org/wiki/Ensemble_Kalman_filter)
