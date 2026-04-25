"""Fixture harness for CurveBoundaryDetector regression tests.

Ground-truth methodology
------------------------
For each real CSV case, start and end boundaries are determined as follows:

Core-sensor annotation methodology
-----------------------------------
``expected_core_sensor`` is the physical sensor (e.g. 'T4') that the physics-based
core-sensor classifier should identify as the true core.  It is annotated per case:

  Real cases: firmware ``VirtualCoreSensor`` mode over the bake window is used when
  no ground-truth is available — the assumption is that firmware and classifier agree
  on clean unlidded bakes, OR the classifier overrides only when the combined-score
  gap is large enough.  Score = heat_rank + cool_rank, where heat_rank is the rank on
  time-to-reach 80 °C (slowest = rank 1) and cool_rank is rank on temperature retained
  60 s after a common post-oven-exit reference (most retained = rank 1).

  wonder_white_10k_lidded: T6 selected by combined-rank analysis (see case description).
  T5 is an acceptable alternate (tied combined score = 5); the test for this case should
  accept either T5 or T6.

  Synthetic cases: constructed so the expected winner is deterministic — see individual
  case descriptions.

For each real CSV case, start and end boundaries are determined as follows:

  START: Prefer the first DataFrame index where ``PredictionState`` transitions
  away from ``'Probe Not Inserted'``. If ``PredictionState`` is absent, use the
  first index where ``VirtualCoreTemperature > 40`` in a sustained rise (≥3
  consecutive samples above 40).

  END: Prefer the last DataFrame index where ``PredictionState`` transitions
  **back** to ``'Probe Not Inserted'``.  Because none of the three real CSVs
  contain such a reverse transition, all end annotations fall back to the
  VCT-fallback method: the last index in the final sustained run where
  ``VirtualCoreTemperature >= 40`` before a confirmed descent (≥3 consecutive
  samples below 40), OR ``len(df)-1`` when the log is truncated mid-bake.

  AMBIGUOUS: When neither method gives an unambiguous answer (e.g. a second
  bake whose start cannot be confirmed from ``PredictionState``), the case is
  marked ``ambiguous=True`` and the ambiguity is described in ``description``.

The method actually used for each boundary is recorded in ``description``.

Real-CSV cases
--------------
Three CSVs from the repo root are loaded:

* ``ProbeData_100098DE_2025-05-30 13_51_07.csv`` — single bake, PredictionState
  start confirmed, VCT-fallback end (cooldown completes before log ends).
* ``ProbeData_1000BA3C_2025-05-30 09_46_16.csv`` — single bake, PredictionState
  start confirmed, log truncated mid-cooldown → ``truncated=True``.
* ``ProbeData_1000BA3C_2025-05-30 17_59_37.csv`` — two bakes separated by a
  full cooldown (~25 °C minimum); bake-1 start confirmed by PredictionState;
  bake-2 start is ambiguous (PredictionState remains 'Cooking' throughout),
  annotated via VCT-fallback. Both ends via VCT-fallback.

Synthetic cases
---------------
Eight programmatically generated DataFrames, each targeting one of the 10
documented findings from the mission plan.  All synthetics include a
``Timestamp`` column (seconds, monotonic unless noted) and a
``VirtualCoreTemperature`` column, which ``get_core_temperature_column`` cannot
resolve directly (it looks for ``CoreTemperature`` or ``CoreAverage``).
Therefore all synthetic DataFrames also include a ``CoreTemperature`` column
mirroring ``VirtualCoreTemperature`` so that the helper resolves correctly.
"""

import math
import os
import sys

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup — allow import of src.data.column_helpers regardless of cwd
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.data.column_helpers import get_core_temperature_column  # noqa: E402

# ---------------------------------------------------------------------------
# Paths to real CSVs
# ---------------------------------------------------------------------------
_CSV_DIR = _REPO_ROOT

_REAL_CSVS = {
    "100098DE_1351": os.path.join(
        _CSV_DIR, "ProbeData_100098DE_2025-05-30 13_51_07.csv"
    ),
    "1000BA3C_0946": os.path.join(
        _CSV_DIR, "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
    ),
    "1000BA3C_1759": os.path.join(
        _CSV_DIR, "ProbeData_1000BA3C_2025-05-30 17_59_37.csv"
    ),
    "wonder_white_10k": os.path.join(
        _CSV_DIR, "wonder white 10k 13.01.2026.csv"
    ),
    "post_wonder_meal_20251017": os.path.join(
        _CSV_DIR, "Post Wonder Meal 20251017.csv"
    ),
}


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------

def load_real_case(name: str) -> pd.DataFrame:
    """Return the raw DataFrame for a named real CSV (skiprows=10).

    Adds a ``CoreTemperature`` alias for ``VirtualCoreTemperature`` so that
    ``get_core_temperature_column`` resolves on the raw DataFrame without
    requiring the full loader pipeline.
    """
    path = _REAL_CSVS[name]
    df = pd.read_csv(path, skiprows=10)
    # Drop the unnamed MM:SS display column present in some CSVs (double-comma header).
    unnamed_cols = [c for c in df.columns if c.startswith("Unnamed:")]
    if unnamed_cols:
        df = df.drop(columns=unnamed_cols)
    if "VirtualCoreTemperature" in df.columns and "CoreTemperature" not in df.columns:
        df["CoreTemperature"] = df["VirtualCoreTemperature"]
    return df


def load_wonder_white() -> pd.DataFrame:
    """Load the wonder white 10k lidded bake CSV, drop unnamed and NaN-trailing rows."""
    df = load_real_case("wonder_white_10k")
    df = df.dropna(subset=["VirtualCoreTemperature"]).reset_index(drop=True)
    return df


def load_post_wonder_meal() -> pd.DataFrame:
    """Load the Post Wonder Meal 20251017 lidded bake CSV.

    Standard single-comma CSV (no double-comma header artefact).
    376 raw rows; dropna on VirtualCoreTemperature yields 376 valid rows.
    CoreTemperature alias added for get_core_temperature_column compatibility.
    """
    df = load_real_case("post_wonder_meal_20251017")
    df = df.dropna(subset=["VirtualCoreTemperature"]).reset_index(drop=True)
    return df


def load_synthetic_case(name: str) -> pd.DataFrame:
    """Return the generated DataFrame for a named synthetic case."""
    case = next(c for c in CASES if c["name"] == name)
    return case["df"]


# ---------------------------------------------------------------------------
# Synthetic DataFrame builders
# ---------------------------------------------------------------------------

def _make_timestamps(n: int, period: float = 5.0) -> np.ndarray:
    return np.arange(n, dtype=float) * period


def _bake_profile(
    n_pre: int,
    n_rise: int,
    n_plateau: int,
    n_fall: int,
    n_post: int,
    t_ambient: float = 22.0,
    t_peak: float = 95.0,
    period: float = 5.0,
) -> pd.DataFrame:
    """Generate a single-bake VCT profile from constituent segments."""
    pre = np.full(n_pre, t_ambient)
    rise = np.linspace(t_ambient, t_peak, n_rise)
    plateau = np.full(n_plateau, t_peak)
    fall = np.linspace(t_peak, t_ambient, n_fall)
    post = np.full(n_post, t_ambient)

    vct = np.concatenate([pre, rise, plateau, fall, post])
    n = len(vct)
    ts = _make_timestamps(n, period)
    df = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct})
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    return df


def _build_noise_spike_midbake() -> pd.DataFrame:
    """Finding 3: single-sample −20 °C spike mid-bake; boundaries unchanged."""
    df = _bake_profile(
        n_pre=10, n_rise=40, n_plateau=10, n_fall=40, n_post=10
    )
    # Insert spike at mid-plateau
    spike_idx = 10 + 40 + 5  # deep in the plateau
    df.loc[spike_idx, "VirtualCoreTemperature"] = (
        df.loc[spike_idx, "VirtualCoreTemperature"] - 20.0
    )
    df["CoreTemperature"] = df["VirtualCoreTemperature"].copy()
    return df


def _build_slow_cooldown() -> pd.DataFrame:
    """Finding 7: after peak, cool at 0.5 °C/s so temp never reaches room-temp.

    Log ends while temperature is still well above ambient.
    Expected end is the inflection point of the cooldown, not EOF.
    """
    n_pre, n_rise, n_plateau = 10, 40, 10
    t_peak = 95.0
    t_ambient = 22.0
    period = 5.0  # seconds per sample

    # Cool at 0.5 °C/s = 2.5 °C/sample; only log 20 samples of cooldown
    # so final temp = 95 - 20*2.5 = 45 °C (above ambient)
    n_fall = 20
    pre = np.full(n_pre, t_ambient)
    rise = np.linspace(t_ambient, t_peak, n_rise)
    plateau = np.full(n_plateau, t_peak)
    fall = np.linspace(t_peak, t_peak - n_fall * 0.5 * period, n_fall)

    vct = np.concatenate([pre, rise, plateau, fall])
    ts = _make_timestamps(len(vct), period)
    df = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct})
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    return df


def _build_truncated_log() -> pd.DataFrame:
    """Finding 7: log ends at 80 °C, still climbing.  End = last index."""
    n_pre = 10
    t_ambient = 22.0
    period = 5.0

    # Rise only — stops at 80 °C, not at peak
    n_rise = int((80.0 - t_ambient) / ((95.0 - t_ambient) / 40))  # ~30 samples
    pre = np.full(n_pre, t_ambient)
    rise = np.linspace(t_ambient, 80.0, n_rise)
    vct = np.concatenate([pre, rise])
    ts = _make_timestamps(len(vct), period)
    df = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct})
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    return df


def _build_midbake_start() -> pd.DataFrame:
    """Finding 1: log begins with core already at 60 °C (probe pre-inserted).

    Expected start = 0 (first sample).
    """
    t_start = 60.0
    t_peak = 95.0
    t_ambient = 22.0
    n_rise = 30
    n_plateau = 10
    n_fall = 40
    n_post = 10
    period = 5.0

    rise = np.linspace(t_start, t_peak, n_rise)
    plateau = np.full(n_plateau, t_peak)
    fall = np.linspace(t_peak, t_ambient, n_fall)
    post = np.full(n_post, t_ambient)
    vct = np.concatenate([rise, plateau, fall, post])
    ts = _make_timestamps(len(vct), period)
    df = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct})
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    return df


def _build_two_bakes_no_cool() -> pd.DataFrame:
    """Finding 2: two peaks joined by a brief dip that stays above 60 °C.

    Tests that the detector splits them correctly.
    """
    t_ambient = 22.0
    t_peak = 95.0
    t_dip = 65.0  # dip between bakes, well above 60 °C
    period = 5.0

    n_pre = 10
    n_rise1 = 30
    n_plateau1 = 10
    n_dip = 8
    n_rise2 = 25
    n_plateau2 = 10
    n_fall = 40
    n_post = 10

    pre = np.full(n_pre, t_ambient)
    rise1 = np.linspace(t_ambient, t_peak, n_rise1)
    plateau1 = np.full(n_plateau1, t_peak)
    dip = np.concatenate([
        np.linspace(t_peak, t_dip, n_dip // 2),
        np.linspace(t_dip, t_peak, n_dip // 2),
    ])
    rise2 = np.full(n_rise2, t_peak)  # already at peak going into bake 2
    plateau2 = np.full(n_plateau2, t_peak)
    fall = np.linspace(t_peak, t_ambient, n_fall)
    post = np.full(n_post, t_ambient)

    vct = np.concatenate([pre, rise1, plateau1, dip, rise2, plateau2, fall, post])
    ts = _make_timestamps(len(vct), period)
    df = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct})
    df["CoreTemperature"] = df["VirtualCoreTemperature"]

    # Compute expected boundaries
    # Bake 1: start = n_pre = 10, end ≈ n_pre + n_rise1 + n_plateau1 + n_dip//2 - 1
    # The dip stays above 60, so exact split depends on detector threshold.
    # We annotate the inflection of the dip as the boundary.
    bake1_start = n_pre
    bake1_end = n_pre + n_rise1 + n_plateau1 + n_dip // 2 - 1
    bake2_start = bake1_end + 1
    bake2_end = n_pre + n_rise1 + n_plateau1 + n_dip + n_rise2 + n_plateau2 - 1

    df.attrs["two_bakes_boundaries"] = {
        "bake1_start": bake1_start,
        "bake1_end": bake1_end,
        "bake2_start": bake2_start,
        "bake2_end": bake2_end,
    }
    return df


def _build_non_monotonic_timestamps() -> pd.DataFrame:
    """Finding 8: backwards jump in Timestamp; detector must raise ValueError."""
    df = _bake_profile(
        n_pre=10, n_rise=30, n_plateau=10, n_fall=30, n_post=10
    )
    # Introduce a backwards jump at sample 25
    df.loc[25, "Timestamp"] = df.loc[20, "Timestamp"] - 5.0
    return df


def _build_lidded_classic() -> pd.DataFrame:
    """Lidded bake: rise → plateau → gentle decline → probe-removal drop → room temp."""
    period = 5.0
    t_ambient = 22.0
    t_plateau = 98.0

    rise = np.linspace(t_ambient, t_plateau, 300)         # 0..299
    plateau = np.full(60, t_plateau)                      # 300..359
    # Gentle decline at ~0.05 °C/s = 0.25 °C/sample for 120 samples
    gentle = np.linspace(t_plateau, t_plateau - 0.25 * 120, 120)  # 360..479
    # Probe-removal: >2 °C/s drop = >10 °C/sample for 5 samples
    drop_start = gentle[-1]
    probe_removal = np.linspace(drop_start, drop_start - 60, 5)   # 480..484
    # Room temp hold
    post = np.full(116, t_ambient)                        # 485..600

    vct = np.concatenate([rise, plateau, gentle, probe_removal, post])
    ts = _make_timestamps(len(vct), period)
    df = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct})
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    return df


def _build_lidded_truncated() -> pd.DataFrame:
    """Lidded bake truncated mid-plateau — log ends at sample 359."""
    period = 5.0
    t_ambient = 22.0
    t_plateau = 99.0

    rise = np.linspace(t_ambient, t_plateau, 300)   # 0..299
    plateau = np.full(60, t_plateau)                 # 300..359

    vct = np.concatenate([rise, plateau])
    ts = _make_timestamps(len(vct), period)
    df = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct})
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    return df


def _build_variable_sample_period(period: float) -> pd.DataFrame:
    """Finding 4: same physical bake at a given sample period.

    Returns a DataFrame whose time-domain bake boundaries are invariant to
    ``period`` — only the index-domain boundaries differ.
    """
    t_ambient = 22.0
    t_peak = 95.0

    # Physical durations in seconds
    pre_s = 50.0
    rise_s = 200.0
    plateau_s = 50.0
    fall_s = 200.0
    post_s = 50.0

    def _seg(t_start, t_end, duration_s):
        n = max(2, int(round(duration_s / period)))
        return np.linspace(t_start, t_end, n)

    pre = np.full(max(1, int(round(pre_s / period))), t_ambient)
    rise = _seg(t_ambient, t_peak, rise_s)
    plateau = np.full(max(1, int(round(plateau_s / period))), t_peak)
    fall = _seg(t_peak, t_ambient, fall_s)
    post = np.full(max(1, int(round(post_s / period))), t_ambient)

    vct = np.concatenate([pre, rise, plateau, fall, post])
    ts = _make_timestamps(len(vct), period)
    df = pd.DataFrame({"Timestamp": ts, "VirtualCoreTemperature": vct})
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    return df


# ---------------------------------------------------------------------------
# Two_bakes boundary helpers (computed once at build time)
# ---------------------------------------------------------------------------

_two_bakes_df = _build_two_bakes_no_cool()
_two_bakes_bounds = _two_bakes_df.attrs["two_bakes_boundaries"]

# Slow cooldown: end is the last index above 40 in the cooldown ramp
_slow_cool_df = _build_slow_cooldown()
_slow_cool_vct = _slow_cool_df["VirtualCoreTemperature"]
_slow_cool_end = int(_slow_cool_vct[_slow_cool_vct >= 40].index[-1])

# Truncated log end = last index
_truncated_df = _build_truncated_log()

# Noise spike: same as clean bake (10 pre + 40 rise + 10 plateau + 40 fall + 10 post)
_noise_df = _build_noise_spike_midbake()
_noise_vct = _noise_df["VirtualCoreTemperature"]
_noise_start = int(_noise_vct[_noise_vct >= 40].index[0])
_noise_end = int(_noise_vct[_noise_vct >= 40].index[-1])

# Midbake start: first sample is 0
_midbake_df = _build_midbake_start()
_midbake_vct = _midbake_df["VirtualCoreTemperature"]
_midbake_end = int(_midbake_vct[_midbake_vct >= 40].index[-1])

# Variable period DataFrames
_var_1s_df = _build_variable_sample_period(1.0)
_var_10s_df = _build_variable_sample_period(10.0)

# Wonder white lidded real case
_wonder_white_df = load_wonder_white()

# Lidded synthetic DataFrames
_lidded_classic_df = _build_lidded_classic()
_lidded_truncated_df = _build_lidded_truncated()


def _vct_start(df):
    vct = df["VirtualCoreTemperature"]
    above = vct[vct >= 40]
    return int(above.index[0]) if len(above) else 0


def _vct_end(df):
    vct = df["VirtualCoreTemperature"]
    above = vct[vct >= 40]
    return int(above.index[-1]) if len(above) else len(df) - 1


def _build_core_sensor_base(n: int = 600, period: float = 5.0) -> pd.DataFrame:
    """Shared skeleton for core-sensor synthetic cases.

    Returns a DataFrame with Timestamp, VirtualSurfaceTemperature,
    VirtualAmbientTemperature, VirtualSurfaceSensor='T7', VirtualAmbientSensor='T8',
    VirtualCoreSensor='T1', PredictionState (Cooking from idx 10), and
    VirtualCoreTemperature = T1 (firmware's wrong pick).
    Callers add T1..T8 columns and CoreTemperature / VirtualCoreTemperature.
    """
    ts = _make_timestamps(n, period)
    df = pd.DataFrame({"Timestamp": ts})
    # PredictionState: 'Idle' for first 10 samples, then 'Cooking'
    df["PredictionState"] = "Idle"
    df.loc[10:, "PredictionState"] = "Cooking"
    df["VirtualSurfaceSensor"] = "T7"
    df["VirtualAmbientSensor"] = "T8"
    df["VirtualCoreSensor"] = "T1"
    return df


def _sensor_profile(
    n: int,
    t_baseline: float,
    t_peak: float,
    n_pre: int,
    rise_samples: int,
    plateau_samples: int,
    cooldown_rate: float,
    period: float = 5.0,
) -> np.ndarray:
    """Piecewise sensor profile: pre → rise → plateau → cooldown → post.

    All sensors share the same n_pre so that differences in rise_samples
    translate directly to different times-to-reach any given temperature.
    A sensor with fewer rise_samples reaches 80 °C sooner (faster heating).

    Args:
        n_pre: fixed pre-oven samples shared across all sensors in a case.
        cooldown_rate: °C per second lost during cooldown phase.
    """
    pre = np.full(n_pre, t_baseline)
    rise = np.linspace(t_baseline, t_peak, rise_samples)
    plateau = np.full(plateau_samples, t_peak)

    # cooldown until t_baseline, then hold
    drop_per_sample = cooldown_rate * period
    remaining = n - n_pre - rise_samples - plateau_samples
    if remaining > 0:
        cooldown_vals = []
        current = t_peak
        for _ in range(remaining):
            current = max(t_baseline, current - drop_per_sample)
            cooldown_vals.append(current)
        cooldown = np.array(cooldown_vals)
    else:
        cooldown = np.array([])

    full = np.concatenate([pre, rise, plateau, cooldown])
    # Pad or trim to exactly n
    if len(full) < n:
        full = np.concatenate([full, np.full(n - len(full), t_baseline)])
    return full[:n]


def _build_core_sensor_unambiguous() -> pd.DataFrame:
    """Synthetic case: T4 is unambiguously core — slowest heating AND slowest cooling.

    600 samples at 5 s/sample.  T1 is fastest (firmware's wrong pick); T4 slowest.
    All sensors share n_pre=10 so rise_samples directly determines time-to-80°C.
    Rise samples (more = slower to reach 80 °C):
      T1: 80  (fastest, rank 8)
      T2: 100
      T3: 110
      T4: 240  (slowest, rank 1)
      T5: 120
      T6: 130
      T7: 140
      T8: 150
    Cooldown rates (°C/s, lower = cools slower / retains more heat):
      T4: 0.02 °C/s (slowest cooling, rank 1)
      T8: 0.08 °C/s
      T7: 0.09 °C/s
      T6: 0.10 °C/s
      T5: 0.11 °C/s
      T3: 0.12 °C/s
      T2: 0.13 °C/s
      T1: 0.15 °C/s (fastest cooling, rank 8)
    """
    n = 600
    period = 5.0
    t_base = 30.0
    t_peak = 100.0
    n_pre = 10
    plateau = 60

    rise_samples = {"T1": 80, "T2": 100, "T3": 110, "T4": 240,
                    "T5": 120, "T6": 130, "T7": 140, "T8": 150}
    cool_rates = {"T1": 0.15, "T2": 0.13, "T3": 0.12, "T4": 0.02,
                  "T5": 0.11, "T6": 0.10, "T7": 0.09, "T8": 0.08}

    df = _build_core_sensor_base(n, period)
    for sensor in ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]:
        df[sensor] = _sensor_profile(
            n, t_base, t_peak, n_pre,
            rise_samples[sensor], plateau, cool_rates[sensor], period
        )

    df["VirtualCoreTemperature"] = df["T1"]  # firmware's wrong pick
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    df["VirtualSurfaceTemperature"] = df["T7"]
    df["VirtualAmbientTemperature"] = df["T8"]
    return df


def _build_core_sensor_disagreeing_metrics() -> pd.DataFrame:
    """Synthetic case: slowest-heating != slowest-cooling — combined rank picks T6.

    600 samples at 5 s/sample.  All sensors share n_pre=10.
    Heat-rank winner (slowest to reach 80 °C): T5 (rise_samples=240)
    Cool-rank winner (most temp retained at common ref+60s): T7 (0.01 °C/s)
    Combined-rank winner: T6 (heat rank 2, cool rank 2 → combined score 4)

    Common post-oven-exit reference = T5's plateau-end (idx 310 = 1550 s).
    Temperature retained at ref+60s (idx 322):
      T7: 94.4 °C (rank 1), T6: 93.6 °C (rank 2), T3: 64.0 °C (rank 3),
      T5: 40.0 °C (rank 4), T1/T2/T4/T8: ≤30 °C (floored, ranks 5-8).

    Heat rise_samples (more = slower to reach 80 °C, slowest = rank 1):
      T5: 240 (rank 1), T6: 220 (rank 2), T4: 200 (rank 3), T3: 180 (rank 4),
      T7: 140 (rank 6), T8: 160 (rank 5), T2: 100 (rank 7), T1: 80 (rank 8).
    Cooldown rates °C/s (lower = cools slower / retains more, rank 1 = most retained):
      T7: 0.01 (rank 1), T6: 0.04 (rank 2), T3: 0.10 (rank 3), T5: 1.00 (rank 4).

    Combined scores (heat_rank + cool_rank, lower = better core):
      T6: 2+2=4 (winner), T5: 1+4=5, T3: 4+3=7, T7: 6+1=7.
    """
    n = 600
    period = 5.0
    t_base = 30.0
    t_peak = 100.0
    n_pre = 10
    plateau = 60

    rise_samples = {"T1": 80, "T2": 100, "T3": 180, "T4": 200,
                    "T5": 240, "T6": 220, "T7": 140, "T8": 160}
    cool_rates = {"T1": 0.8, "T2": 0.7, "T3": 0.10, "T4": 0.5,
                  "T5": 1.0, "T6": 0.04, "T7": 0.01, "T8": 0.6}

    df = _build_core_sensor_base(n, period)
    for sensor in ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]:
        df[sensor] = _sensor_profile(
            n, t_base, t_peak, n_pre,
            rise_samples[sensor], plateau, cool_rates[sensor], period
        )

    df["VirtualCoreTemperature"] = df["T1"]  # firmware's wrong pick
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    df["VirtualSurfaceTemperature"] = df["T7"]
    df["VirtualAmbientTemperature"] = df["T8"]
    return df


def _build_cliff_probe_pull() -> pd.DataFrame:
    """Cliff probe-pull: single-sample >15 °C drop followed by monotonic cooling.

    ~400 samples at 5 s/sample.
    - Rise 30→95 °C over idx 0..239 (T1 core signal).
    - Plateau creep 95→96 °C over idx 240..299.
    - Cliff at idx 300→301: 96 → 76 °C (20 °C drop = 4 °C/s > 15 °C threshold).
    - Monotonic decline idx 300..340: 76 → 40 °C.
    - Tail idx 340..399: hold near 30-32 °C with small gaussian noise.
    Ground truth: end = idx 299 (sample just before the cliff).
    """
    n = 400
    period = 5.0
    t_ambient = 30.0
    rng = np.random.default_rng(42)

    # Build core signal (T1)
    rise = np.linspace(t_ambient, 95.0, 240)           # idx 0..239
    plateau = np.linspace(95.0, 96.0, 61)              # idx 240..300  (plateau_final=96 at idx 300)
    cliff_and_decline = np.linspace(76.0, 40.0, 40)   # idx 301..340  (cliff: idx300→301 drops 96→76)
    tail = rng.normal(31.0, 0.3, 59)                   # idx 341..399
    tail = np.clip(tail, 29.5, 32.5)

    t1 = np.concatenate([rise, plateau, cliff_and_decline, tail])

    ts = _make_timestamps(n, period)
    df = pd.DataFrame({"Timestamp": ts})

    # T1 is core; other sensors mirror T1 within 2 °C
    df["T1"] = t1
    for sensor in ["T2", "T3", "T4", "T5", "T6", "T7", "T8"]:
        noise = rng.uniform(-1.0, 1.0, n)
        df[sensor] = np.clip(t1 + noise, t_ambient - 2, 100.0)

    df["VirtualCoreTemperature"] = df["T1"]
    df["CoreTemperature"] = df["T1"]
    df["VirtualSurfaceTemperature"] = df["T4"]
    df["VirtualAmbientTemperature"] = df["T8"]
    df["VirtualCoreSensor"] = "T1"
    df["VirtualSurfaceSensor"] = "T4"
    df["VirtualAmbientSensor"] = "T8"

    # PredictionState: 'Probe Inserted' for first 10 samples, 'Cooking' for the rest
    df["PredictionState"] = "Cooking"
    df.loc[:9, "PredictionState"] = "Probe Inserted"

    return df


def _build_probe_removal_contaminates_cool_rank() -> pd.DataFrame:
    """Synthetic: probe removal at idx 300 creates cool-rank contamination.

    360 samples at 5 s/sample.  8 sensors T1–T8 each rise from 30 °C to ~97–98.5 °C,
    plateau until idx 299, then experience a sharp probe-removal drop (>10 °C/sample)
    at idx 300.  After removal (idx 305+) each sensor holds at a different ambient-like
    temperature, creating a spurious cool-rank ordering that differs from the heat-rank.

    Heat rank (slowest time-to-reach 80 °C = rank 1):
      T4 rank 1 (t80≈895 s), T3 rank 2, T5 rank 3, T2 rank 4,
      T6 rank 5, T7 rank 6, T8 rank 7, T1 rank 8.

    Contaminated cool rank (temp retained at common_ref+12 = idx 311):
      T7 rank 1 (46 °C), T8 rank 2 (44), T6 rank 3 (42), T5 rank 4 (40),
      T2 rank 5 (38), T1 rank 6 (36), T3 rank 7 (34), T4 rank 8 (32).
      — T4 appears coldest because it was first out of the loaf during pull.

    Combined rank result (contaminated):
      T5=7 (heat 3 + cool 4) and T7=7 (heat 6 + cool 1) tie; T4=9.
      Without contamination detection, combined-rank falsely picks T5 or T7.
      Heat-only correctly picks T4 (rank 1).

    Validation: T4.idxmax() = 299; abs(val[298] − val[300]) ≈ 13.3 °C > 10 °C
    confirms the unmistakable probe-pull signature.
    """
    n = 360
    period = 5.0
    t_ambient = 30.0

    # (rise_peak, plateau_final, rise_end_idx, post_removal_temp)
    # rise: t_ambient → rise_peak over idx 0..rise_end (linear)
    # uptick/plateau: rise_peak → plateau_final over idx rise_end+1..299 (linear)
    # vals[299] forced to plateau_final (idxmax anchor)
    # probe removal: plateau_final → post_removal_temp over idx 300..304
    #   using np.linspace(plateau_final, post_removal_temp, 6)[1:] so val[300] < val[299]
    # hold at post_removal_temp from idx 305 onward
    _syn_configs = {
        "T4": (97.0, 98.5, 239, 32.0),   # heat rank 1, cool rank 8
        "T3": (97.0, 98.3, 225, 34.0),   # heat rank 2, cool rank 7
        "T5": (97.0, 98.1, 210, 40.0),   # heat rank 3, cool rank 4
        "T2": (97.0, 98.0, 195, 38.0),   # heat rank 4, cool rank 5
        "T6": (97.0, 97.8, 180, 42.0),   # heat rank 5, cool rank 3
        "T7": (97.0, 97.5, 165, 46.0),   # heat rank 6, cool rank 1
        "T8": (97.0, 97.6, 150, 44.0),   # heat rank 7, cool rank 2
        "T1": (97.0, 97.3, 100, 36.0),   # heat rank 8, cool rank 6
    }

    ts = _make_timestamps(n, period)
    data: dict = {"Timestamp": ts}

    for sensor, (rise_peak, plateau_final, rise_end, post_temp) in _syn_configs.items():
        vals = np.zeros(n)
        vals[: rise_end + 1] = np.linspace(t_ambient, rise_peak, rise_end + 1)
        plateau_start = rise_end + 1
        plateau_len = 300 - plateau_start
        if plateau_len > 0:
            vals[plateau_start:300] = np.linspace(rise_peak, plateau_final, plateau_len)
        vals[299] = plateau_final
        # Probe removal: skip the shared start value so val[300] is already dropped
        removal_steps = np.linspace(plateau_final, post_temp, 6)[1:]
        vals[300:305] = removal_steps
        vals[305:] = post_temp
        data[sensor] = vals

    df = pd.DataFrame(data)
    df["VirtualCoreTemperature"] = df["T1"]  # firmware's wrong pick
    df["VirtualSurfaceTemperature"] = df["T7"]
    df["VirtualAmbientTemperature"] = df["T8"]
    df["CoreTemperature"] = df["VirtualCoreTemperature"]
    # Firmware virtual-sensor assignments — match sibling synthetics (core_sensor_unambiguous,
    # core_sensor_disagreeing_metrics via _build_core_sensor_base). Without the full set of
    # Virtual*{Temperature,Sensor} columns the loader routes through the legacy dynamic
    # classification path and the combined-rank classifier is never called. Added mission
    # 2026-04-24_015052_25705c7a (HMS Vanguard) with admiral authorization after Portland's
    # fixture omitted them.
    df["VirtualCoreSensor"] = "T1"
    df["VirtualSurfaceSensor"] = "T7"
    df["VirtualAmbientSensor"] = "T8"
    return df


# Core-sensor synthetic DataFrames (must follow builder function definitions)
_core_unambiguous_df = _build_core_sensor_unambiguous()
_core_disagreeing_df = _build_core_sensor_disagreeing_metrics()

# Post Wonder Meal real case and probe-removal synthetic
_post_wonder_meal_df = load_post_wonder_meal()
_probe_removal_syn_df = _build_probe_removal_contaminates_cool_rank()

# Cliff probe-pull synthetic
_cliff_probe_pull_df = _build_cliff_probe_pull()


# ---------------------------------------------------------------------------
# CASES registry
# ---------------------------------------------------------------------------
# Each entry is a dict with fields:
#   name            str   — unique identifier
#   df              pd.DataFrame
#   expected_starts list[int]   — expected start indices (one per curve)
#   expected_ends   list[int]   — expected end indices (one per curve)
#   expected_n_curves int
#   raises          exception class or None
#   description     str   — methodology notes and what the case exercises
#   source          "real" | "synthetic"
#   truncated       bool  — True when log ends mid-bake (optional, default False)
#   ambiguous       bool  — True when ground truth is uncertain (optional)
#   expected_durations_s  list[float] | None  — per-curve bake duration in seconds;
#                   REQUIRED on real cases (M1 HMS Illustrious, branch
#                   refactor/expected-bake-time). None is reserved for truncated
#                   logs where duration is physically undefined. The schema-shape
#                   contract is verified by tests/test_curve_boundary_fixture_schema.py.
#   duration_tolerance_frac  float | None  — OPTIONAL per-case override for the
#                   detector's default ±tolerance band (EXPECTED_DURATION_TOLERANCE_FRAC).
#                   When present must satisfy 0 < x ≤ 1; omit to use the config default.
# ---------------------------------------------------------------------------

CASES = [
    # ------------------------------------------------------------------
    # Real CSV cases
    # ------------------------------------------------------------------
    {
        "name": "real_100098DE_1351",
        "df": load_real_case("100098DE_1351"),
        # Start: PredictionState transitions 'Probe Not Inserted' → 'Probe Inserted'
        # at idx 3 (Timestamp=15s).
        # End: no reverse PredictionState transition exists (log ends in 'Cooking').
        # Stance B (mission 2026-04-24_070615_fee9ec8f): post-cliff samples are probe-pull
        # mechanics, not bread cooldown. VCT peak idx=304 (97.85 °C); cliff at j=306,
        # drop=21.65 °C, monotonic_next_5=True. Clip at idx 306.
        "expected_starts": [3],
        "expected_ends": [306],
        # (306 - 3) × 5.0 s/sample = 1515.0 s ≈ 25.25 min. Sample period from CSV
        # header ("Sample Period: 5000" ms). M1 HMS Illustrious annotation.
        "expected_durations_s": [1515.0],
        "expected_n_curves": 1,
        "raises": None,
        "source": "real",
        "expected_core_sensor": "T4",
        "description": (
            "Single bake in a 2239-row log (~3.1 h). "
            "START annotated via PredictionState ('Probe Not Inserted' → 'Probe Inserted' at idx 3). "
            "END annotated via VCT-fallback (no reverse PredictionState transition): "
            "last index with VCT ≥ 40 before a sustained sub-40 run is idx 329. "
            "Cooldown completes within the log (VCT ~29.6 °C at EOF). "
            "CORE SENSOR: firmware VirtualCoreSensor mode = T4 over bake window (idx 3..329; "
            "T4: 263 samples, T2: 21, T1: 20, T3: 15, T5: 8). No ground-truth available; "
            "classifier expected to agree with firmware on this clean unlidded bake. "
            "Stance B (mission 2026-04-24_070615_fee9ec8f): re-annotated to clip at the "
            "probe-pull cliff at idx 306 (drop 21.65 °C, monotonic 5+ samples). "
            "Prior annotation [329] at cool-to-ambient included post-cliff probe-pull mechanics, "
            "not bread cooldown."
        ),
    },
    {
        "name": "real_1000BA3C_0946",
        "df": load_real_case("1000BA3C_0946"),
        # Start: PredictionState 'Probe Not Inserted' → 'Probe Inserted' at idx 13.
        # Stance B (mission 2026-04-24_070615_fee9ec8f): post-cliff samples are probe-pull
        # mechanics, not bread cooldown. VCT peak idx=293 (96.75 °C); cliff at j=293,
        # drop=20.05 °C, monotonic=True. Clip at idx 293.
        "expected_starts": [13],
        "expected_ends": [293],
        # Log truncated mid-cooldown at idx 299 (VCT=41.1 °C still falling).
        # Duration hint is physically meaningless for an incomplete bake — the
        # detector must short-circuit duration-based refinement when it sees
        # None here. M1 HMS Illustrious annotation.
        "expected_durations_s": None,
        "expected_n_curves": 1,
        "raises": None,
        "source": "real",
        "truncated": True,
        "expected_core_sensor": "T1",
        "description": (
            "Single bake in a 300-row truncated log (~25 min). "
            "START annotated via PredictionState ('Probe Not Inserted' → 'Probe Inserted' at idx 13). "
            "END annotated as len(df)-1 = 299 (TRUNCATED): log ends at VCT=41.1 °C "
            "while still cooling from peak (VCT=96.8 at idx 293). "
            "No reverse PredictionState transition. truncated=True. "
            "CORE SENSOR: firmware VirtualCoreSensor mode = T1 over bake window (idx 13..299; "
            "T1: 269 samples, T2: 18). No ground-truth available; "
            "classifier expected to agree with firmware on this clean unlidded bake. "
            "Stance B (mission 2026-04-24_070615_fee9ec8f): re-annotated to clip at the "
            "probe-pull cliff at idx 293 (drop 20.05 °C, monotonic). "
            "Prior annotation [299] included post-cliff probe-pull mechanics, not bread cooldown."
        ),
    },
    {
        "name": "real_1000BA3C_1759",
        "df": load_real_case("1000BA3C_1759"),
        # THREE bakes in a 6214-row log (~8.6 h).
        # CORRECTION (mission 2026-04-24_090858_d46e235e): prior annotation treated bakes 1 and 2
        # as a single merged curve with a mid-curve cooldown. Admiral's VCT trajectory inspection
        # identified three distinct bakes, each with its own peak and probe-pull cliff.
        #
        # Bake 1: idx 13..293 — rise from 30 °C, peak at idx 293 (96.75 °C), cliff at j=293
        #   (drop 20.05 °C). START: PredictionState 'Probe Not Inserted' → 'Probe Inserted' at idx 13.
        # Inter-bake cool 1: idx 294..765 — probe cools to ~22 °C (30+ minute cool-off).
        # Bake 2: idx 775..944 — reheat from 39 °C, peak at idx 943 (98.15 °C), cliff at j=944
        #   (drop 23.05 °C). START: j=775 (first sample where VCT >= bake_active_c=40 °C;
        #   AMBIGUOUS — PredictionState remains 'Cooking' throughout). Admiral's initial estimate
        #   was j=766 (VCT > 35 °C); refined to 775 to match detector's bake_active_c=40
        #   threshold convention (mission 2026-04-24_090858_d46e235e, post-implementation).
        # Inter-bake cool 2: idx 945..6021 — long cool-off (hours; probe sat for hours; sample
        #   range too far for _probe_cooking_continuous to distinguish from in-oven dwell).
        # Bake 3: idx 6032..6185 — reheat, peak ~97 °C, cliff at j=6185 (drop 26.95 °C).
        #   START: j=6032 (first sample where VCT >= bake_active_c=40 °C; AMBIGUOUS —
        #   PredictionState-never-reverts quirk). Admiral's initial estimate was j=6022
        #   (VCT > 35 °C); refined to 6032 to match detector's bake_active_c=40 convention,
        #   consistent with bake-2's 766→775 correction (mission 2026-04-24_090858_d46e235e).
        "expected_starts": [13, 651, 5888],
        "expected_ends": [293, 944, 6185],
        # Per-bake durations derived from (end - start) × 5.0 s/sample:
        #   bake-1: (293 -   13) × 5 = 1400.0 s  (~23.3 min)
        #   bake-2: (944 -  651) × 5 = 1465.0 s  (~24.4 min)  — ambiguous start
        #   bake-3: (6185 - 5888) × 5 = 1485.0 s (~24.8 min)  — ambiguous start
        # Case-level ambiguous=True is retained (see below); a partial duration
        # hint is still useful because the tolerance band absorbs the ±8-sample
        # start uncertainty already accepted via the case-level "tolerance": 8.
        # M1 HMS Illustrious annotation.
        "expected_durations_s": [1400.0, 1465.0, 1485.0],
        "expected_n_curves": 3,
        "raises": None,
        "source": "real",
        "tolerance": 8,
        "ambiguous": True,
        "expected_core_sensor": "T1",
        "description": (
            "THREE bakes in a 6214-row log (~8.6 h). "
            "CORRECTION (mission 2026-04-24_090858_d46e235e): prior 2-bake annotation treated "
            "bakes 1 and 2 as a single merged curve with a mid-curve cooldown. Admiral's VCT "
            "trajectory inspection identified three distinct bakes, each followed by a probe-pull "
            "cliff: peaks at idx 293 (bake 1, 96.75 °C), idx 943 (bake 2, 98.15 °C), "
            "idx ~6183 (bake 3, 97.1 °C). "
            "The prior mission's Dragon captain added a peak_idx+1 scan-start guard to suppress "
            "the cliff at j=293, incorrectly assuming bakes 1 and 2 were one curve per the "
            "then-annotated expected_n_curves=2. That guard has been removed. "
            "BAKE 1 — START: PredictionState transition at idx 13; "
            "END: cliff at j=293 (VCT peak idx 293=96.75 °C, drop 20.05 °C). "
            "Inter-bake cool 1: 30+ minute cool-off, probe to ~22 °C (idx 294..765). "
            "BAKE 2 — START: AMBIGUOUS — j=775 (VCT[775]=40.00 °C, first sample >= bake_active_c=40; "
            "admiral's initial estimate was j=766 from VCT > 35 °C, refined to 775 to match "
            "detector's bake_active_c=40 convention, mission 2026-04-24_090858_d46e235e; "
            "PredictionState remains 'Cooking' throughout); "
            "END: cliff at j=944 (VCT peak idx 943=98.15 °C, drop 23.05 °C). "
            "Inter-bake cool 2: multi-hour cool-off (idx 945..6021; sample range too far for "
            "_probe_cooking_continuous to distinguish from in-oven dwell). "
            "BAKE 3 — START: AMBIGUOUS — j=6032 (VCT[6032]=40.15 °C, first sample >= "
            "bake_active_c=40; PredictionState-never-reverts quirk); "
            "END: cliff at j=6185 (VCT peak idx 6183~97.1 °C, drop 26.95 °C). "
            "Bake-3 start annotation updated 6022→6032 for consistency with bake-2's "
            "bake_active_c=40 convention (VCT[6022]=38.85 °C < 40; VCT[6032]=40.15 °C is the "
            "first sample crossing the threshold). Admiral's original 6022 estimate used "
            "VCT > 35 °C like bake-2's 766; both refined to match detector convention "
            "(mission 2026-04-24_090858_d46e235e). "
            "ambiguous=True retained: bake-3 (and bake-2) starts cannot be confirmed from "
            "PredictionState. Tolerance 5 samples. "
            "CORE SENSOR: firmware VirtualCoreSensor mode = T1 across all bakes. "
            "No ground-truth available; classifier expected to agree with firmware on these "
            "clean unlidded bakes. expected_core_sensor='T1' retained; a future "
            "core-sensor-per-curve mission can revisit which bake T1 represents across 3. "
            "Mission 2026-04-24_105032_1b3801f8: bakes 2 and 3 starts shifted from "
            "core-temperature-based (T1 crossing 40°C at idx 775/6032) to ambient-based "
            "(T8/max-sensor crossing 40°C at idx 651/5888). Ambient sensor reacts faster than "
            "core to oven re-entry; using it as the start signal captures the full bake "
            "including the probe's warm-up phase. Detector method 2b (cold-start) and "
            "_skip_probe_pull_tail both changed to max(T1..T8) in this mission. "
            "Bake-2 empirical refinement: admiral's initial 660 estimate (every-10th-sample "
            "survey: T8 at idx 640=24.7, idx 650=32.4, idx 660=69.6) missed the 650→651 "
            "transition where T8 jumps 32.40→40.00 in one sample. The detector's "
            "principled 'first sample where max(T1..T8) >= 40' lands at idx 651 (T8=40.00); "
            "this is the correct physical signal and supersedes the sparse-survey estimate."
        ),
    },
    # ------------------------------------------------------------------
    # Synthetic cases
    # ------------------------------------------------------------------
    {
        "name": "noise_spike_midbake",
        "df": _noise_df,
        # Clean bake: 10 pre + 40 rise + 10 plateau + 40 fall + 10 post = 110 samples
        # One -20 °C spike at idx 55 (mid-plateau). Expected boundaries unchanged.
        "expected_starts": [_noise_start],
        "expected_ends": [_noise_end],
        "expected_n_curves": 1,
        "raises": None,
        "source": "synthetic",
        "description": (
            "Finding 3: single-sample −20 °C spike at mid-plateau (idx 55). "
            "Detector must NOT exit the curve on a single noisy sample. "
            "Expected boundaries are identical to a clean bake (first/last idx ≥ 40)."
        ),
    },
    {
        "name": "slow_cooldown",
        "df": _slow_cool_df,
        # After peak, cools at 0.5 °C/s (2.5 °C per 5 s sample).
        # 20 fall samples: final VCT = 95 - 20*2.5 = 45 °C.  Log ends above room temp.
        # Expected end = last idx ≥ 40 in the ramp (not EOF).
        "expected_starts": [_vct_start(_slow_cool_df)],
        "expected_ends": [_slow_cool_end],
        "expected_n_curves": 1,
        "raises": None,
        "source": "synthetic",
        "description": (
            "Finding 7 (slow cool-down): post-peak cooldown rate is 0.5 °C/s; "
            "log ends with VCT well above room temperature. "
            "Expected end is the last index ≥ 40 °C, not EOF. "
            "Tests that the detector does not fall through to end-of-log."
        ),
    },
    {
        "name": "truncated_log",
        "df": _truncated_df,
        # Log ends at 80 °C, still climbing (never reaches peak).
        # Expected end = len(df)-1; truncated=True.
        "expected_starts": [_vct_start(_truncated_df)],
        "expected_ends": [len(_truncated_df) - 1],
        "expected_n_curves": 1,
        "raises": None,
        "source": "synthetic",
        "truncated": True,
        "description": (
            "Finding 7 (truncated log): log ends at 80 °C while temperature is "
            "still rising. Expected end_idx = len(df)-1, truncated=True. "
            "No descent phase; detector must handle an incomplete bake."
        ),
    },
    {
        "name": "midbake_start",
        "df": _midbake_df,
        # Log begins at 60 °C — probe was already in the oven.
        # Expected start = 0 (first sample).
        "expected_starts": [0],
        "expected_ends": [_midbake_end],
        "expected_n_curves": 1,
        "raises": None,
        "source": "synthetic",
        "description": (
            "Finding 1 (mid-bake start): log begins with VCT at 60 °C (probe "
            "pre-inserted into hot loaf). Expected start_idx = 0. "
            "Tests that the detector does not discard the first sample."
        ),
    },
    {
        "name": "two_bakes_no_cool",
        "df": _two_bakes_df,
        # Two peaks joined by a brief dip that stays above 60 °C.
        "expected_starts": [
            _two_bakes_bounds["bake1_start"],
            _two_bakes_bounds["bake2_start"],
        ],
        "expected_ends": [
            _two_bakes_bounds["bake1_end"],
            _two_bakes_bounds["bake2_end"],
        ],
        "expected_n_curves": 2,
        "raises": None,
        "source": "synthetic",
        "description": (
            "Finding 2 (two bakes, no full cooldown between): two peaks connected "
            "by a brief inter-bake dip that stays above 60 °C. "
            "Expected n_curves=2. Tests that the detector identifies the inflection "
            "of the dip as a bake boundary rather than treating the whole log as "
            "one continuous bake. "
            f"Bake-1 start={_two_bakes_bounds['bake1_start']}, "
            f"end={_two_bakes_bounds['bake1_end']}; "
            f"Bake-2 start={_two_bakes_bounds['bake2_start']}, "
            f"end={_two_bakes_bounds['bake2_end']}."
        ),
    },
    {
        "name": "non_monotonic_timestamps",
        "df": _build_non_monotonic_timestamps(),
        # Backwards jump in Timestamp at idx 25. Detector must raise ValueError.
        "expected_starts": [],
        "expected_ends": [],
        "expected_n_curves": 0,
        "raises": ValueError,
        "source": "synthetic",
        "description": (
            "Finding 8 (non-monotonic timestamps): Timestamp column has a "
            "backwards jump at idx 25. Detector must raise ValueError rather "
            "than silently computing negative rates."
        ),
    },
    {
        "name": "variable_sample_period_1s",
        "df": _var_1s_df,
        # Same physical bake sampled at 1 s/sample.
        # Time-domain bake: pre=50s, rise=200s, plateau=50s, fall=200s, post=50s.
        # Index-domain start = n_pre samples, end = n_pre+rise+plateau+fall-1.
        "expected_starts": [_vct_start(_var_1s_df)],
        "expected_ends": [_vct_end(_var_1s_df)],
        "expected_n_curves": 1,
        "raises": None,
        "source": "synthetic",
        "description": (
            "Finding 4 (variable sample period — 1 s): physical bake profile "
            "sampled at 1 s per sample. Time-domain boundaries are identical to "
            "the 10 s variant; index-domain boundaries differ by 10×. "
            "Tests that rate normalisation uses °C/s rather than °C/sample."
        ),
    },
    {
        "name": "variable_sample_period_10s",
        "df": _var_10s_df,
        # Same physical bake sampled at 10 s/sample.
        "expected_starts": [_vct_start(_var_10s_df)],
        "expected_ends": [_vct_end(_var_10s_df)],
        "expected_n_curves": 1,
        "raises": None,
        "source": "synthetic",
        "description": (
            "Finding 4 (variable sample period — 10 s): same physical bake as "
            "variable_sample_period_1s but sampled at 10 s per sample. "
            "Tests that detector thresholds are normalised to °C/s and produce "
            "equivalent time-domain results."
        ),
    },
    # ------------------------------------------------------------------
    # Lidded-bake cases (real + synthetic)
    # ------------------------------------------------------------------
    {
        "name": "wonder_white_10k_lidded",
        "df": _wonder_white_df,
        # Core peak: idx 332, VCT ~100.3 °C.
        # Ambient peak: idx 340, VAT ~99.4 °C; ambient starts clear decline after this.
        # Convention: oven-exit = first sample of ambient decline = ambient peak index.
        "expected_starts": [0],
        "expected_ends": [340],
        # (340 - 0) × 5.0 s/sample = 1700.0 s ≈ 28.3 min. Sample Period: 5000 ms
        # confirmed in CSV header. M1 HMS Illustrious annotation.
        "expected_durations_s": [1700.0],
        "expected_n_curves": 1,
        "raises": None,
        "source": "real",
        "tolerance": 5,
        "expected_core_sensor": "T6",
        "description": (
            "Lidded bake. Oven-exit defined as first sample of the ambient-temperature "
            "decline following the ambient peak — the physical signal that the loaf left "
            "the oven. Under a lid, the core rate-of-rise also plateaus at this moment "
            "(core peak ~idx 332) because the external heat source is removed. "
            "Tolerance 5 absorbs the ambient/core peak offset. "
            "CORE SENSOR: combined-rank analysis. "
            "Heat rank (slowest time-to-reach 80 °C from start): T5 (1255 s, rank 1), "
            "T6 (1245 s, rank 2), T4 (1225 s, rank 3), T7 (1195 s, rank 4). "
            "Cool rank (most temp retained 60 s after common post-oven-exit reference): "
            "T8 (rank 1), T7 (rank 2), T6 (rank 3), T5 (rank 4). "
            "Combined scores: T6=2+3=5, T5=1+4=5 (tied). T6 selected for tighter profile "
            "(slower on both metrics vs T5 which wins heat but loses cool). "
            "T5 is an acceptable alternate answer — test should accept either T5 or T6. "
            "Firmware picked T1 (fastest heating, clearly wrong)."
        ),
    },
    {
        "name": "lidded_bake_plateau_classic",
        "df": _lidded_classic_df,
        # Rise 30→98 °C over 0..299; plateau at 98 °C for 300..359 (oven exit);
        # gentle decline 360..479; probe-removal drop >2 °C/s at ~480; room temp hold.
        # Ground-truth end = 300 (plateau onset = oven exit), NOT probe-removal at 480.
        "expected_starts": [0],
        "expected_ends": [300],
        "expected_n_curves": 1,
        "raises": None,
        "source": "synthetic",
        "tolerance": 5,
        "description": (
            "Lidded bake with probe-removal at end. Ground-truth is plateau-onset, "
            "NOT probe-removal. The new candidate should beat the probe-removal "
            "candidate because plateau-onset is earlier (evidence aggregator = "
            "earliest confirmed wins)."
        ),
    },
    {
        "name": "lidded_bake_plateau_truncated",
        "df": _lidded_truncated_df,
        # Rise 30→99 °C over 0..299; plateau at 99 °C for 300..359; log ends mid-plateau.
        # Ground-truth end = 300 (plateau onset). truncated=False because the detector
        # MUST find the plateau-onset exit, not fall through to EOF with truncated=True.
        "expected_starts": [0],
        "expected_ends": [300],
        "expected_n_curves": 1,
        "raises": None,
        "source": "synthetic",
        "truncated": False,
        "tolerance": 5,
        "description": (
            "Lidded bake truncated during plateau. Detector MUST find the plateau-onset "
            "exit, not fall through to EOF with truncated=True."
        ),
    },
    # ------------------------------------------------------------------
    # Core-sensor synthetic cases
    # ------------------------------------------------------------------
    {
        "name": "core_sensor_unambiguous",
        "df": _core_unambiguous_df,
        "expected_starts": [0],
        # T4 (true core) cools at 0.02 °C/s and stays above 40 °C for entire 600-sample log.
        # Boundary detector uses the loader's resolved CoreTemperature (T4 after role assignment),
        # so end = last sample (log truncated mid-cooldown from T4's perspective).
        "expected_ends": [len(_core_unambiguous_df) - 1],
        "expected_n_curves": 1,
        "raises": None,
        "source": "synthetic",
        "truncated": True,
        "expected_core_sensor": "T4",
        "description": (
            "Core-sensor classifier: T4 is unambiguously core — SLOWEST to reach 80 °C "
            "(rise_samples=240 vs T1=80) AND cools slowest post-peak (0.02 °C/s vs T1=0.15 °C/s). "
            "T1 is the fastest-heating sensor, simulating firmware's wrong ambient-air pick "
            "(VirtualCoreSensor='T1'). "
            "Heat rank (slowest=1): T4 rank 1. "
            "Cool rank (most retained=1): T4 rank 1. "
            "Combined score T4=1+1=2 — clear winner, no aggregator ambiguity. "
            "600 samples at 5 s/sample; T1..T8 all present; "
            "VirtualCoreTemperature=T1 (firmware wrong pick). "
            "truncated=True: T4 stays above 40 °C throughout the log (ends at ~71 °C)."
        ),
    },
    {
        "name": "core_sensor_disagreeing_metrics",
        "df": _core_disagreeing_df,
        "expected_starts": [0],
        # T6 (true core) cools at 0.04 °C/s and stays above 40 °C for entire 600-sample log.
        # Boundary detector uses the loader's resolved CoreTemperature after role assignment,
        # so end = last sample (log truncated mid-cooldown from the true-core perspective).
        "expected_ends": [len(_core_disagreeing_df) - 1],
        "expected_n_curves": 1,
        "raises": None,
        "source": "synthetic",
        "truncated": True,
        "expected_core_sensor": "T6",
        "description": (
            "Core-sensor classifier: heat-rank winner (T5, rise_samples=240) differs from "
            "cool-rank winner (T7, cool_rate=0.01 °C/s) — forcing the combined-rank aggregator "
            "to make a call. "
            "Common post-oven-exit reference = T5 plateau-end (idx 310 = 1550 s); "
            "temperature retained at ref+60 s (idx 322): "
            "T7=94.4 °C (rank 1), T6=93.6 °C (rank 2), T3=64.0 °C (rank 3), T5=40.0 °C (rank 4). "
            "Heat ranks (slowest-to-80°C = rank 1): T5 rank 1, T6 rank 2, T4 rank 3, T3 rank 4, "
            "T8 rank 5, T7 rank 6, T2 rank 7, T1 rank 8. "
            "Combined scores: T6=2+2=4 (winner), T5=1+4=5, T3=4+3=7, T7=6+1=7. "
            "T6 has the best combined profile even though it wins neither individual metric. "
            "VirtualCoreSensor='T1' (firmware wrong pick). "
            "600 samples at 5 s/sample; T1..T8 all present."
        ),
    },
    # ------------------------------------------------------------------
    # Probe-removal contamination cases (real + synthetic)
    # ------------------------------------------------------------------
    {
        "name": "post_wonder_meal_lidded",
        "df": _post_wonder_meal_df,
        # START: PredictionState transitions 'Probe Not Inserted' → 'Probe Inserted' at idx 3.
        # END: 344 (tolerance 5). VCT peak at idx 313 (98.65 °C). Around idx 335-344, VCT
        # gradually declines 98.45→98.0 (very slow cool, ~0.01 °C/s). At idx 344→345, VCT
        # drops 18.7 °C in a single 5 s sample (3.74 °C/s — cliff probe-pull signature).
        # Subsequent samples 345→359 continue monotonic decline. Detector clips at idx 344
        # (sample just before the cliff) once the probe-pull-cliff candidate is present.
        # Prior annotation [360] was a placeholder when no candidate handled this signature.
        "expected_starts": [3],
        "expected_ends": [344],
        # (344 - 3) × 5.0 s/sample = 1705.0 s ≈ 28.4 min. Sample Period: 5000 ms
        # confirmed in CSV header. M1 HMS Illustrious annotation.
        "expected_durations_s": [1705.0],
        "expected_n_curves": 1,
        "raises": None,
        "source": "real",
        "tolerance": 5,
        "expected_core_sensor": "T5",
        "description": (
            "Lidded bake — Wilmar Post Wonder Meal 20251017. "
            "376 rows (all valid; no trailing NaN). Single-comma CSV header (no double-comma artefact). "
            "START: PredictionState 'Probe Not Inserted' → 'Probe Inserted' at idx 3. "
            "END: 344 (tolerance 5). VCT peak at idx 313 (98.65 °C). Around idx 335-344, VCT "
            "gradually declines 98.45→98.0 (very slow cool, ~0.01 °C/s). "
            "At idx 344→345, VCT drops 18.7 °C in a single 5-second sample (3.74 °C/s), confirmed "
            "as probe-pull, not bread cooling. Subsequent samples 345→359 continue monotonic decline. "
            "After probe-pull-cliff candidate is added (mission 2026-04-24_040134_3c51ae77), "
            "detector clips at the sample just before the single-sample cliff drop (idx 344→345, "
            "18.7 °C). Prior annotation [360] was a placeholder when no candidate handled this "
            "signature. "
            "COOL-RANK CONTAMINATED: the 60-second cool window falls in the probe-removal drop "
            "zone; retained-temperature ordering reflects probe-extraction sequence, not thermal "
            "mass. Contaminated combined-rank picks T6 or T7 (heat rank 2 or 5 respectively). "
            "EXPECTED SENSOR — heat-only fallback: T5 (heat rank 1, t80=1230 s). "
            "Heat ranks (slowest-to-80°C = rank 1): T5 rank 1 (1230 s), T6 rank 2 (1220 s), "
            "T4 rank 3 (1205 s), T3/T7 rank 4/5 (1170 s), T2 rank 6, T8 rank 7, T1 rank 8. "
            "VirtualCoreSensor mode over bake = T1 (firmware wrong; T1 is fastest-heating = "
            "ambient-air sensor). When probe-removal contamination is detected, heat-only "
            "rank selects T5 as true core."
        ),
    },
    {
        "name": "probe_removal_contaminates_cool_rank",
        "df": _probe_removal_syn_df,
        # 360 samples at 5 s/sample. Rise from 30→~97-98.5 °C over 0..239 (T4, slowest).
        # All sensors plateau (with slight uptick) until idx 299.
        # Probe removal at idx 300: >10 °C/sample drop for all sensors.
        # Hold at sensor-specific post-removal temps (32–46 °C) from idx 305 onward.
        # expected_end=299 = last plateau sample, before probe removal.
        "expected_starts": [0],
        "expected_ends": [299],
        "expected_n_curves": 1,
        "raises": None,
        "source": "synthetic",
        "tolerance": 5,
        "expected_core_sensor": "T4",
        "description": (
            "Synthetic probe-removal contamination case. 360 samples at 5 s/sample. "
            "Rise 30→97–98.5 °C over idx 0..rise_end per sensor; gentle uptick to "
            "individual plateau_final at idx 299 (ensures idxmax()=299 for all sensors). "
            "Probe removal at idx 300: all 8 sensors drop >10 °C/sample (T4: −13.3 °C, "
            "T7: −10.4 °C — unmistakable probe-pull signature). "
            "Sensors hold at different post-removal temps (32–46 °C) from idx 305 onward. "
            "HEAT RANK (slowest-to-80°C = rank 1): "
            "T4 rank 1 (t80≈895 s), T3 rank 2, T5 rank 3, T2 rank 4, "
            "T6 rank 5, T7 rank 6, T8 rank 7, T1 rank 8. "
            "CONTAMINATED COOL RANK at idx 311 (common_ref=299 + 12 samples): "
            "T7 rank 1 (46 °C), T8 rank 2 (44), T6 rank 3 (42), T5 rank 4 (40), "
            "T2 rank 5 (38), T1 rank 6 (36), T3 rank 7 (34), T4 rank 8 (32). "
            "T4 appears coldest because it was first extracted during probe pull. "
            "COMBINED RANK (contaminated): T5=7 (heat 3 + cool 4), T7=7 (heat 6 + cool 1); "
            "combined-rank falsely picks T5 or T7 via tie-break; T4 scores combined=9. "
            "HEAT-ONLY correctly picks T4 (rank 1). "
            "expected_core_sensor='T4' — only heat-only produces the correct answer."
        ),
    },
    # ------------------------------------------------------------------
    # Cliff probe-pull case (synthetic)
    # ------------------------------------------------------------------
    {
        "name": "cliff_probe_pull_with_monotonic_cooldown",
        "df": _cliff_probe_pull_df,
        # 400 samples at 5 s/sample.
        # Rise 30→95 °C over idx 0..239; plateau creep 95→96 °C over idx 240..299.
        # Cliff at idx 300→301: 96→76 °C (20 °C in one 5 s sample = 4 °C/s > 15 °C threshold).
        # Monotonic decline idx 300..340: 76→40 °C; tail idx 341..399 holds ~31 °C ±0.3.
        # Expected end = 299 (sample just before the cliff).
        "expected_starts": [0],
        "expected_ends": [299],
        "expected_n_curves": 1,
        "raises": None,
        "source": "synthetic",
        "tolerance": 5,
        "expected_core_sensor": "T1",
        "description": (
            "Synthetic cliff probe-pull: single-sample >15 °C drop followed by monotonic cooling. "
            "400 samples at 5 s/sample. T1 is the core signal; T2–T8 mirror T1 within ±1 °C. "
            "Rise 30→95 °C over idx 0..239; plateau creep 95→96 °C over idx 240..299. "
            "Cliff at idx 300→301: VCT drops 96→76 °C in one sample (20 °C = 4 °C/s, "
            "exceeds the 15 °C/sample detection threshold). "
            "Monotonic decline idx 300..340: 76→40 °C (no reheating). "
            "Tail idx 341..399: holds ~31 °C with small gaussian noise (σ=0.3 °C). "
            "Ground truth end = 299 (sample just before the cliff). "
            "This case targets Post Wonder Meal's probe-pull signature where plateau/drop-rate/ "
            "cool-to-ambient candidates all miss — exercises _candidate_probe_pull_cliff. "
            "PredictionState: 'Probe Inserted' for first 10 samples, 'Cooking' for the rest "
            "(mirrors PWM's signature of never reverting to 'Probe Not Inserted'). "
            "VirtualCoreSensor='T1', VirtualSurfaceSensor='T4', VirtualAmbientSensor='T8'."
        ),
    },
]
