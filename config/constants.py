"""Constants for thermal profile analysis."""

# Temperature zones for bread baking (in Celsius)
TEMPERATURE_ZONES = {
    "YEAST_KILL": {
        "min": 55,
        "max": 57,
        "name": "Yeast Kill",
        "color": "#FF6B6B"
    },
    "STARCH_GELATINIZATION": {
        "min": 65,
        "max": 82,
        "name": "Starch Gelatinization",
        "color": "#4ECDC4"
    },
    "PROTEIN_DENATURATION": {
        "min": 71,
        "max": 85,
        "name": "Protein Denaturation",
        "color": "#45B7D1"
    },
    "CRUST_FORMATION": {
        "min": 110,
        "max": 180,
        "name": "Crust Formation",
        "color": "#F7DC6F"
    },
    "MAILLARD_REACTION": {
        "min": 105,
        "max": 150,
        "name": "Maillard Reaction",
        "color": "#D2691E"
    },
    "CARAMELIZATION": {
        "min": 150,
        "max": 200,
        "name": "Caramelization",
        "color": "#8B4513"
    },
    "TARGET_CORE": {
        "min": 93,
        "max": 98,
        "name": "Target Core Temperature",
        "color": "#52C41A"
    }
}

# S-Curve specific zones
S_CURVE_ZONES = {
    "OVEN_SPRING": {
        "min": 20,  # Ambient
        "max": 56,
        "name": "Oven Spring Zone",
        "description": "Final fermentation and volume expansion",
        "color": "#FFE5B4"
    },
    "CRITICAL_CHANGE": {
        "min": 56,
        "max": 93,
        "name": "Critical Change Zone",
        "description": "Yeast kill, starch gelatinization, protein denaturation",
        "color": "#B4D4FF"
    },
    "BAKE_OUT": {
        "min": 93,
        "max": 200,
        "name": "Bake-Out Zone",
        "description": "Moisture loss and final texture development",
        "color": "#FFB4B4"
    }
}

# S-Curve landmark benchmarks (as percentage of total bake time)
S_CURVE_BENCHMARKS = {
    "YEAST_KILL": {
        "temperature": 56,
        "target_percentage": (45, 55),  # 45-55% of total bake time
        "critical": True
    },
    "STARCH_COMPLETE": {
        "temperature": 82,
        "target_percentage": (55, 65),  # 55-65% of total bake time
        "critical": True
    },
    "ARRIVAL_TEMP": {
        "temperature": 93,
        "target_percentage": (80, 90),  # 80-90% of total bake time
        "critical": True
    }
}

# Bake-out targets by product type (percentage of total bake time)
BAKEOUT_TARGETS = {
    "white_pan": (15, 18),
    "whole_wheat": (12, 15),
    "multigrain": (2, 7),
    "sourdough": (18, 22),
    "baguette": (20, 25),
    "hamburger_bun": (10, 15),
    "dinner_roll": (8, 12),
    "artisan": (22, 28)
}

# Biochemical transformation temperatures
TRANSFORMATION_TEMPS = {
    "ENZYME_INACTIVATION": {
        "amylase": 75,
        "protease": 60
    },
    "MAILLARD_REACTION": {
        "onset": 105,
        "optimal": 140,
        "description": "Non-enzymatic browning"
    },
    "CARAMELIZATION": {
        "onset": 150,
        "optimal": 170,
        "description": "Sugar browning"
    }
}

# Sensor configuration
SENSOR_NAMES = {
    "T1": "Core 1",
    "T2": "Core 2", 
    "T3": "Core 3",
    "T4": "Core 4",
    "T5": "Middle 1",
    "T6": "Middle 2",
    "T7": "Near Surface",
    "T8": "Surface"
}

# Analysis parameters
ANALYSIS_PARAMS = {
    "smoothing_window": 3,  # Moving average window
    "gradient_threshold": 0.5,  # °C/s for significant heating
    "uniformity_threshold": 2.0,  # °C for acceptable uniformity
    "min_bake_time": 300,  # seconds
    "max_bake_time": 1800  # seconds
}

# Quality thresholds
QUALITY_THRESHOLDS = {
    "excellent": {
        "uniformity_cv": 0.02,  # Coefficient of variation
        "heating_rate_consistency": 0.9,
        "zone_coverage": 0.95
    },
    "good": {
        "uniformity_cv": 0.05,
        "heating_rate_consistency": 0.8,
        "zone_coverage": 0.85
    },
    "acceptable": {
        "uniformity_cv": 0.1,
        "heating_rate_consistency": 0.7,
        "zone_coverage": 0.75
    }
}

# Product-specific moisture parameters
PRODUCT_MOISTURE = {
    "white_pan": {
        "initial_moisture": 38.0,  # Initial moisture content %
        "target_final": (32, 34),  # Target final moisture range
        "k_factor": 0.018,  # Exponential decay constant
        "crust_factor": 0.7  # Crust barrier effect (0-1)
    },
    "whole_wheat": {
        "initial_moisture": 40.0,
        "target_final": (33, 35),
        "k_factor": 0.016,
        "crust_factor": 0.65
    },
    "multigrain": {
        "initial_moisture": 42.0,
        "target_final": (35, 37),
        "k_factor": 0.014,
        "crust_factor": 0.6
    },
    "sourdough": {
        "initial_moisture": 39.0,
        "target_final": (31, 33),
        "k_factor": 0.020,
        "crust_factor": 0.75
    },
    "baguette": {
        "initial_moisture": 36.0,
        "target_final": (28, 30),
        "k_factor": 0.025,
        "crust_factor": 0.8
    },
    "hamburger_bun": {
        "initial_moisture": 37.0,
        "target_final": (33, 35),
        "k_factor": 0.019,
        "crust_factor": 0.7
    },
    "dinner_roll": {
        "initial_moisture": 38.0,
        "target_final": (34, 36),
        "k_factor": 0.017,
        "crust_factor": 0.65
    },
    "artisan": {
        "initial_moisture": 37.0,
        "target_final": (29, 31),
        "k_factor": 0.023,
        "crust_factor": 0.85
    }
}

# Internal sensor detection configuration.
# Legacy temperature-threshold filter retained only for ``loader.get_internal_sensors``;
# a position-based replacement using ``SpatialAssignment.<role>.position_normalised``
# is a future follow-up. The new spatial-reconstruction classifier (M2a-M3a) does
# not consume any of these keys — see ``ROLE_CLASSIFIER_CONFIG`` below.
INTERNAL_SENSOR_CONFIG = {
    "TEMP_THRESHOLD": 103.0,  # Max temperature for internal crumb (100°C + 3°C margin)
    "TIME_THRESHOLD": 0.1,  # Max fraction of time above 100°C (10%)
    "USE_TIME_BASED_FILTERING": False,  # Whether to also check time spent >100°C
    "ALWAYS_INCLUDE_CORE": True  # Always include core sensor even if >100°C
}

# Curve boundary (bread entry/exit) detection configuration.
# Rates are expressed in °C/s so detection is invariant to the sample period.
CURVE_DETECTION_CONFIG = {
    "ROOM_TEMP_MAX": 35.0,              # °C — samples at/below this are "room temperature"
    "MIN_PEAK_TEMP": 80.0,              # °C — a curve must reach at least this to count
    # Cliff-start gate: cliff's starting sample must be at or above this temperature.
    # Semantically distinct from MIN_PEAK_TEMP (curve-acceptance): if one threshold
    # is tuned for cold-finished products the other must not move unintentionally.
    "CLIFF_MIN_START_TEMP_C": 80.0,     # °C — cliff scan ignores drops below this temp
    # Anchored to the `two_bakes_no_cool` synthetic fixture whose bake-1 is ~160 s.
    # A typical industrial bread bake is > 20 min; this value may need raising
    # (e.g. to 300 s) for production deployment once real-CSV fixtures are regenerated.
    "MIN_CURVE_DURATION_SECONDS": 120,  # seconds (NOT samples) — shortest acceptable bake
    "DROP_RATE_THRESHOLD_C_PER_SEC": 2.0,  # °C/s — sustained drop rate candidate
    "CONFIRMATION_WINDOW_SAMPLES": 3,   # N consecutive samples required to confirm an exit
    "POST_PEAK_GRACE_SAMPLES": 10,      # samples after peak before exit candidates may fire
    "LARGE_DROP_FROM_PEAK_C": 40.0,     # °C — absolute drop-from-peak candidate
    "START_RISE_THRESHOLD_C": 5.0,      # °C — single-sample rise from cold that triggers start
    # Core-peak-plateau candidate (mission 2026-04-23 HMS Warspite, lidded bakes).
    # Under a lid the loaf's thermal mass prevents the sharp post-peak decline
    # the other candidates expect; instead the core rate-of-change flatlines at
    # oven-exit.  Rates in °C/s and windows in seconds so detection is invariant
    # to sample period.  CONFIRM_SECONDS is tuned to 20 s (4 samples at 5 s/sample)
    # because the real wonder-white lidded CSV shows only ~4 samples of sub-0.01
    # °C/s plateau before the sharp post-oven-exit decline begins — a 60 s
    # confirmation window would never fire on that fixture.
    "CORE_PEAK_PLATEAU_RATE_C_PER_SEC": 0.01,
    # CONFIRM_SECONDS is a target, not a guarantee: effective confirm window =
    # max(round(CONFIRM_SECONDS / dt), CONFIRMATION_WINDOW_SAMPLES) × dt.
    # At sample periods ≥ 10 s the CONFIRMATION_WINDOW_SAMPLES floor dominates
    # (e.g. dt=10 s → round(20/10)=2 samples, floor raises to 3; dt=30 s → 1 sample,
    # floor raises to 3 = 90 s effective window).  This is intentional and defensive,
    # not a bug.  See mission 2026-04-23_121616_b56f691b red-cell Note C.
    "CORE_PEAK_PLATEAU_CONFIRM_SECONDS": 20,
    "CORE_PEAK_PLATEAU_RATE_WINDOW_SECONDS": 30,
    # Probe-pull cliff candidate (mission 2026-04-24_040134_3c51ae77, HMS Ark Royal;
    # Stance B mission 2026-04-24_070615_fee9ec8f, HMS Dragon).
    # Fires universally on lidded and unlidded bakes: a single-sample ≥15 °C drop
    # followed by weakly monotonic decline is the probe-pull cliff — the real
    # bread-in-oven endpoint regardless of product.  The prior CLIFF_PRE_PEAK guard
    # (Ark Royal) was removed in Stance B because the physics analysis (Astute Q3)
    # established that the cliff is always a probe-pull event, not ordinary cooldown.
    "INSTANT_DROP_THRESHOLD_C": 15.0,
    # Number of consecutive sub-samples that must continue cooling (weakly monotonic
    # decline, equality allowed) after the cliff for the candidate to confirm.
    # 5 samples = 25 s at 5 s/sample — long enough to rule out noise but short
    # enough to fit inside any truncated tail we care about.
    "CLIFF_MONOTONIC_CONFIRM_SAMPLES": 5,
    # °C — VCT threshold below which the probe is treated as "no longer baking".
    "BAKE_ACTIVE_THRESHOLD_C": 40.0,
    # -----------------------------------------------------------------
    # Optional expected-bake-time hint + sigmoid refinement (M2 HMS
    # Resolution, mission 2026-04-24_135328_1963f3d2).  These entries
    # are consumed by src/data/sigmoid_refinement.py and by the hint-
    # driven arbitration paths added in M3 Agincourt (end) and M4 Hood
    # (start).  When the detector runs with expected_durations_s=None
    # for a given curve, none of these thresholds are read — the
    # existing earliest-wins behaviour is byte-identical.
    # -----------------------------------------------------------------
    # ±fraction around expected duration within which end candidates
    # remain eligible for sigmoid-weighted arbitration.  0.15 = ±15 %,
    # e.g. a 25 min expected bake accepts candidates in 21.25–28.75 min.
    "EXPECTED_DURATION_TOLERANCE_FRAC": 0.15,
    # Absolute floor on the tolerance band so very short bakes keep a
    # sensible window (e.g. a 2-min expected bake isn't gated to ±18 s).
    "EXPECTED_DURATION_MIN_TOLERANCE_SECONDS": 60.0,
    # Minimum fit R² for the sigmoid shape to contribute to the
    # composite candidate score.  Below this the R² term drops to 0
    # and only the proximity term can steer arbitration.
    "SIGMOID_FIT_MIN_R2": 0.85,
    # Windows smaller than this skip curve_fit entirely — protects the
    # hot path from paying solver cost on trivially short candidates.
    "SIGMOID_FIT_MIN_SAMPLES": 30,
    # Composite score weights.  Must sum to 1.0 by convention; the
    # module clamps final scores to [0, 1] anyway.
    "SIGMOID_FIT_COMPOSITE_WEIGHT_R2": 0.6,
    "SIGMOID_FIT_COMPOSITE_WEIGHT_PROXIMITY": 0.4,
    # Upper bound on start-refinement shifts (M4 HMS Hood, mission
    # 2026-04-24_145238_a5f28423).  When a hint is supplied and the
    # native start (from Method 1 / 2a / 2b) sits outside the expected-
    # start window, the detector may shift start toward the window —
    # but never by more than this many seconds.  Protects the recent
    # Method 2b max-sensor start (mission 2026-04-24_105032_1b3801f8)
    # and NC-1/NC-2 coupling with _skip_probe_pull_tail from being
    # disturbed by a long-shift hint.
    "EXPECTED_DURATION_MAX_START_SHIFT_SECONDS": 30.0,
}

# Combined-rank core helper still used by curve-boundary detection's
# probe-removal-contamination path (``identify_core_sensor_combined_rank``
# in ``src/data/thermodynamic_sensor_classifier.py``) and by the shared
# ``_drop_rate_detection`` helper. The class-level ``ThermodynamicSensorClassifier``
# was deleted in M3b HMS Bellerophon — ``spatial_reconstruction.classify`` is the
# canonical role classifier — but the combined-rank function and its tunables
# below remain part of the curve-boundary contamination detector.
#
# CONFIDENCE_GAP_MIN / ENABLED / COOL_REFERENCE_MODE entries were dropped in the
# M5 finale (mission 2026-04-27_123109_e0029555) — they belonged to the deleted
# class and had no readers in src/. The probe-noise calibration story for the
# old gap-of-4 threshold lives in mission 2026-04-23_231637_4ed7fcd1.
CORE_DETECTION_CONFIG = {
    # Heating-side anchor. All sensors spend less time below 80 °C than above
    # under a typical oven profile, so time-to-reach-80 °C is the most reliable
    # "slower = deeper" signal during active heating.
    "HEAT_THRESHOLD_C": 80.0,
    # Cool window: cooling is measured from a SHARED reference point (the
    # latest peak across T1..T8) over this many seconds. Used by
    # identify_core_sensor_combined_rank.
    "COOL_WINDOW_SECONDS": 60,
    # Probe-removal contamination detection in the cool-rank window
    # (mission 2026-04-24_015052_25705c7a, HMS Vanguard).
    # Physics: when the operator pulls the probe out of the loaf shortly after
    # peak, ALL 8 sensors drop rapidly together — the retained-temperature reading
    # no longer reflects bread thermal mass, it reflects probe-pull mechanics, so
    # cool-rank scoring is meaningless. When confirmed within the cool window we
    # fall back to heat-only ranking (same branch as cool_available=False).
    # Rate threshold mirrors CURVE_DETECTION_CONFIG["DROP_RATE_THRESHOLD_C_PER_SEC"]
    # so the two detectors agree on the probe-pull signature.
    "PROBE_REMOVAL_RATE_C_PER_SEC": 2.0,
    # Confirmation is tighter than curve_boundary_detector's CONFIRMATION_WINDOW_SAMPLES
    # (3) because the classifier only needs to detect contamination, not decide the
    # exact end of the curve; two consecutive confirming samples suffice and avoid
    # under-triggering on short post-peak tails.
    "PROBE_REMOVAL_CONFIRM_SAMPLES": 2,
    # Minimum number of sensors that must SIMULTANEOUSLY exceed the rate threshold
    # on the same sample to count toward confirmation (mission 2026-04-24_015052_25705c7a,
    # HMS Audacious red-cell verdict).
    # Physics: a real probe pull extracts the WHOLE probe at once — multiple sensors
    # exit the loaf simultaneously, so ≥2 sensors drop rapidly on the same sample.
    # A single-sensor noise spike at any given sample is uncorrelated across sensors.
    # Empirical validation (probe_alternative_semantics.py, Audacious):
    #   min_k=1 (Vanguard): BA3C_1759 FP=13%, 100098DE FP=62% at σ=1.0 °C noise
    #   min_k=2 (this):     BA3C_1759 FP= 4%, 100098DE FP=17% at σ=1.0 °C noise
    # min_k=2 retains PWM true-positive while cutting BA3C_1759 false-positive
    # below the 5% REVISE threshold. min_k=3 eliminates all FP but misses PWM.
    "PROBE_REMOVAL_MIN_SIMULTANEOUS_SENSORS": 2,
}

# Canonical list of physical sensor channels on a Combustion Inc. probe.
# Ordered T1..T8 from probe tip toward probe stem.
SENSOR_LIST = ('T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8')

# Terminal-temperature tolerance (°C) for grouping lid-contact sensors into a
# "lid plateau" cluster. A genuine lid touches multiple adjacent sensors at
# similar plateaued temperatures; the spatial_reconstruction classifier
# requires >= 2 candidate sensors whose terminal temperatures fall within this
# band of each other before accepting a lid. Lifted from the inline 15.0 magic
# constant that previously appeared in both the lid pre-pass and lid-selection
# blocks of classifier.py (M28 H3 consolidation).
LID_CLUSTER_TOLERANCE_C = 15.0


# ---------------------------------------------------------------------------
# Spatial-reconstruction role classifier (M2a HMS Indefatigable, mission
# 2026-04-27_074742_ad37cb29).
#
# Replaces the discrete-sensor heuristics in SURFACE_DETECTION_CONFIG /
# CORE_DETECTION_CONFIG / INTERNAL_SENSOR_CONFIG. The new module
# (src/data/spatial_reconstruction) treats T(x_1..x_8) as samples of a 1D
# temperature profile and infers role positions, not sensor labels.
#
# Each constant carries a calibration story in the spirit of
# CORE_DETECTION_CONFIG['CONFIDENCE_GAP_MIN'].
# ---------------------------------------------------------------------------
ROLE_CLASSIFIER_CONFIG = {
    # ------------------------------------------------------------------
    # Plateau-near-100°C detection (latent-heat signature)
    # ------------------------------------------------------------------
    # Water in the dough boils/evaporates at 100 °C; the strongest in-dough
    # physics signature is a temperature plateau in this band. Tight 95–105
    # window matches INTERNAL_SENSOR_CONFIG.TEMP_THRESHOLD's 100 °C + 3 °C
    # margin spirit; the lower 95 °C floor accepts pre-boil approach since
    # real probes never sit exactly on 100 °C.
    "PLATEAU_NEAR_100_LOWER_C": 95.0,
    "PLATEAU_NEAR_100_UPPER_C": 105.0,
    # Slope below which a sample is plateau-like. 0.05 °C/s = 0.25 °C/sample
    # at 5 s/sample — well below noise floor on real CSVs (σ < 0.5 °C
    # observed on 1000BA3C plateau samples). Also well below typical heating
    # rates of 0.3–1.5 °C/s in dough.
    "PLATEAU_RATE_THRESHOLD_C_PER_S": 0.05,
    # Minimum dwell to *count* as a plateau-bounded curve. 60 s = 12 samples
    # at 5 s/sample. Below this an apparent "plateau" is likely an
    # inflection point rather than a latent-heat signature.
    "PLATEAU_MIN_DWELL_SECONDS": 60,

    # ------------------------------------------------------------------
    # Rise-slope feature
    # ------------------------------------------------------------------
    # Band over which the pre-plateau heating slope is measured. 30–80 °C
    # covers the linear conduction phase before 100 °C boundary effects
    # dominate. Air-side sensors clear this band quickly (high slope);
    # dough sensors traverse it slowly (low slope).
    "RISE_SLOPE_LOWER_C": 30.0,
    "RISE_SLOPE_UPPER_C": 80.0,

    # ------------------------------------------------------------------
    # Terminal-temperature window
    # ------------------------------------------------------------------
    # Robust mean of last X% of curve. 5% gives ~6 samples on a 130-sample
    # synthetic and ~17 samples on a 340-sample real bake — enough for the
    # 5–95 percentile clip to remove probe-pull spikes without losing all
    # signal. Mirrors the spirit of CORE_DETECTION_CONFIG's
    # COOL_WINDOW_SECONDS (60 s = ~5% of typical bake duration).
    "TERMINAL_WINDOW_FRACTION": 0.05,

    # ------------------------------------------------------------------
    # Oven-proxy / ambient classification
    # ------------------------------------------------------------------
    # Tolerance band around the cavity proxy max(T1..T8). Sensors whose
    # terminal temperature lies within this many °C of the proxy terminal
    # value are considered to be in oven air. 5 °C is large enough to
    # tolerate noise + small spatial gradient between adjacent air-side
    # sensors but smaller than typical core-vs-air gap (~30+ °C).
    "OVEN_PROXY_TOLERANCE_C": 5.0,

    # ------------------------------------------------------------------
    # Lid-contact detection
    # ------------------------------------------------------------------
    # Minimum gap between lid plateau and cavity setpoint to flag lid
    # contact. 20 °C calibrated against synthetic_lid_touch fixture: cavity
    # proxy ~220 °C, lid plateau ~150 °C → 70 °C gap. Below 20 °C the lid
    # signal is indistinguishable from cavity-air noise / position effects.
    "LID_TEMP_BELOW_CAVITY_C": 20.0,
    # Sanity upper bound — gap larger than this likely indicates a sensor
    # that is in dough, not lid contact. 60 °C empirically distinguishes
    # lid-contact (~30–70 °C below cavity in synthetic data) from dough
    # plateau (cavity − 100 °C+ when oven setpoint is ~220 °C).
    "LID_TEMP_BELOW_CAVITY_MAX_C": 80.0,

    # ------------------------------------------------------------------
    # Dough/air interface detection
    # ------------------------------------------------------------------
    # Minimum adjacent-sensor terminal-temperature jump to flag a dough/
    # air interface. 15 °C: real CSVs show jumps of 25–30 °C across the
    # interface (T6→T7 in 1000BA3C, T7→T8 in 100098DE); 15 is the smallest
    # observed jump on lidded fixtures. Below this we suppress to avoid
    # false interfaces from noise within a single region.
    "MONOTONIC_GRADIENT_MIN_JUMP_C": 15.0,

    # ------------------------------------------------------------------
    # Confidence reporting
    # ------------------------------------------------------------------
    # Score gap (as fraction of max score) below which a role's confidence
    # is downgraded from "high" to "medium". 0.15 mirrors the
    # ENABLED-with-margin pattern of CORE_DETECTION_CONFIG['CONFIDENCE_GAP_MIN']
    # (gap of 4 on a 16-point scale = 0.25; 0.15 is a tighter floor since
    # the spatial fit reduces noise relative to discrete rank-summing).
    "CONFIDENCE_GAP_MIN_FRACTION": 0.15,

    # ------------------------------------------------------------------
    # Multi-curve / segmentation handling
    # ------------------------------------------------------------------
    # When the input DataFrame is longer than this many samples AND
    # contains multiple bakes, classify() will run CurveBoundaryDetector
    # to extract the longest curve before fitting. 500 samples ≈ 40 min
    # at 5 s/sample, which exceeds any single bake we have seen.
    "MULTI_CURVE_SEGMENT_THRESHOLD_SAMPLES": 500,

    # ------------------------------------------------------------------
    # Default spatial-fit model (M2b HMS Vanguard)
    # ------------------------------------------------------------------
    # Set by the empirical comparison in
    # tests/baselines/spatial_model_comparison.md. Loader (M3a) passes this
    # through to classify(model=...). "piecewise" is the M2a default; M2b's
    # comparison harness can flip this to "stefan" if it wins on
    # role-pass count + position-error metrics.
    "DEFAULT_MODEL": "piecewise",

    # Stefan-physics-constrained model — minimum α (per-unit-x) below
    # which the air-region rise is considered ill-determined and the fit
    # falls back to the proxy asymptote. 0.05 is the floor used by
    # _fit_alpha_crust to clamp pathological fits.
    "STEFAN_ALPHA_MIN": 0.05,
    # Maximum α — clamps overfit on noisy fixtures.
    "STEFAN_ALPHA_MAX": 100.0,
    # Stefan front pin temperature (latent-heat plateau). Pinned at exactly
    # 100 °C; the constant is exposed for testability and future probe-
    # specific calibration (e.g. high-altitude oven where the boil point
    # shifts).
    "STEFAN_FRONT_TEMP_C": 100.0,
}