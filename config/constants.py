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

# Physics-based surface detection configuration
SURFACE_DETECTION_CONFIG = {
    "USE_PHYSICS_BASED_DETECTION": True,  # Enable physics-based surface sensor detection
    "CONFIDENCE_THRESHOLD": 60,  # Minimum confidence % to apply correction
    "LOG_CORRECTIONS": True,  # Log when corrections are applied
    "SHOW_IN_UI": True  # Show detection status in UI
}

# Internal sensor detection configuration
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
}

# Physics-based core-sensor classifier configuration.
# Combined-rank detector: the true core sensor should be slowest BOTH to heat
# and to cool. Single-metric heuristics fail when the two signals disagree
# (e.g. wonder-white lidded bake: slowest heat = T5/T6, slowest cool = T8).
# Combined rank requires consistency across both signals before overriding the
# firmware VirtualCoreSensor pick. Anchor case: wonder white 10k 13.01.2026.csv
# (firmware returns T1; true core is T5/T6). Mission 2026-04-23_231637_4ed7fcd1.
CORE_DETECTION_CONFIG = {
    # Heating-side anchor. All sensors spend less time below 80 °C than above
    # under a typical oven profile, so time-to-reach-80 °C is the most reliable
    # "slower = deeper" signal during active heating.
    "HEAT_THRESHOLD_C": 80.0,
    # Documentation value: cooling is measured from a SHARED reference point
    # (the latest peak across T1..T8) rather than each sensor's own peak.
    # Per-sensor peaks bias the rank toward early-peaking (surface-like)
    # sensors because their cooling has a head start.
    "COOL_REFERENCE_MODE": "common_post_oven_exit",
    "COOL_WINDOW_SECONDS": 60,
    # With 8 sensors ranked 1..8 on two metrics, combined score ranges 2..16.
    # A gap of 4 is calibrated as 1 point above the empirical noise floor
    # observed on identical-physics synthetic fixtures.
    #
    # Empirical noise-floor calibration: Monte-Carlo 200 seeds, identical-
    # physics-with-noise at σ=0.5 °C.
    #   4-sensor path:  gap-to-runner-up p95 = 3, max = 4
    #   8-sensor production path: gap-to-runner-up p95 = 4, max = 5
    # The 8-sensor production path has a THINNER margin than the 4-sensor
    # calibration implies: the margin-of-1 reasoning does not straightforwardly
    # extend — at p95 the noise floor already reaches the threshold.
    #
    # Mitigation: real-CSV perturbation (probe_noise_real.py, mission
    # 2026-04-23_231637_4ed7fcd1) at σ=1.0 °C shows 0/100 flips on all 3
    # real CSVs; at σ=2.0 °C only 5/100 flips on real_100098DE_1351 (a
    # near-coin-flip between T3/T4 at that noise level). Threshold 4 is safe
    # in practice on the known real CSVs but optimistic in theory for the
    # production 8-sensor path. For replay see probe_monte_carlo.py and
    # probe_noise_real.py in the mission directory.
    #
    # Threshold still fires correctly on target cases:
    #   - wonder-white lidded (gap 7, target flip)
    #   - synthetic unambiguous (gap 12, target flip)
    #   - synthetic disagreeing metrics (gap 10, target flip)
    # Real unlidded CSVs have firmware gaps 0, 0, 1 and do NOT flip.
    # Smaller gap = firmware stays (conservative): only override when physics
    # is unambiguously louder than noise.
    "CONFIDENCE_GAP_MIN": 4,
    "ENABLED": True,
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