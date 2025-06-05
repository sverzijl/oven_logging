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