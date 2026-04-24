"""Red-cell probe: introspect each real CSV through current detector and
report what path start-detection took, and what each method would have
returned independently.
"""

import os
import sys

REPO = r"C:\Users\simeon.Verzijl\OneDrive - Wilmar International Limited\Dandenong\projects\combustion\oven_logging"
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import numpy as np
import pandas as pd

from config.constants import CURVE_DETECTION_CONFIG as BOUNDARY_DETECTION_CONFIG
from src.data.curve_boundary_detector import (
    CurveBoundaryDetector,
    _resolve_max_sensor_series,
    PROBE_NOT_INSERTED_STATE,
    _SENSOR_COLUMNS,
)
from src.data.column_helpers import resolve_core_temperature_series
from tests.fixtures.curve_boundary_cases import (
    load_real_case,
    load_wonder_white,
    load_post_wonder_meal,
)


def load_cases():
    return {
        "100098DE_1351": load_real_case("100098DE_1351"),
        "1000BA3C_0946": load_real_case("1000BA3C_0946"),
        "1000BA3C_1759": load_real_case("1000BA3C_1759"),
        "wonder_white_10k_lidded": load_wonder_white(),
        "post_wonder_meal_lidded": load_post_wonder_meal(),
    }


def first_pred_state_transition(pred_state):
    if pred_state is None:
        return None
    for j in range(len(pred_state) - 1):
        if pred_state[j] == PROBE_NOT_INSERTED_STATE and pred_state[j + 1] != PROBE_NOT_INSERTED_STATE:
            return j + 1
    return None


def first_crossing(series, threshold, confirm_n, start=0):
    n = len(series)
    for j in range(start, n):
        if series[j] < threshold:
            continue
        look = min(confirm_n - 1, n - 1 - j)
        ok = all(series[j + k] >= threshold for k in range(1, look + 1))
        if ok:
            return j
    return None


def main():
    det = CurveBoundaryDetector(BOUNDARY_DETECTION_CONFIG)
    bake_active = 40.0
    room_temp_max = float(BOUNDARY_DETECTION_CONFIG["ROOM_TEMP_MAX"])
    confirm_n = int(BOUNDARY_DETECTION_CONFIG["CONFIRMATION_WINDOW_SAMPLES"])

    for name, df in load_cases().items():
        print("=" * 70)
        print(f"CASE: {name}  rows={len(df)}")
        print("-" * 70)
        has_all_sensors = all(c in df.columns for c in _SENSOR_COLUMNS)
        core = resolve_core_temperature_series(df).to_numpy(dtype=float)
        max_sensor = _resolve_max_sensor_series(df, core)
        pred_state = df["PredictionState"].to_numpy() if "PredictionState" in df.columns else None

        print(f"  has_all_sensors(T1..T8): {has_all_sensors}")
        print(f"  has_pred_state:          {pred_state is not None}")
        if pred_state is not None:
            unique_states = list(pd.unique(pred_state))
            print(f"  pred_state unique set:   {unique_states}")
            first_trans = first_pred_state_transition(pred_state)
            print(f"  first PredictionState transition idx: {first_trans}")

        print(f"  core[0]={core[0]:.2f}  max_sensor[0]={max_sensor[0]:.2f}")
        # Independent scans
        cross_core = first_crossing(core, bake_active, confirm_n)
        cross_max = first_crossing(max_sensor, bake_active, confirm_n)
        print(f"  first_crossing(core>=40,confirm={confirm_n}):       idx={cross_core}")
        print(f"  first_crossing(max>=40, confirm={confirm_n}):       idx={cross_max}")

        # Which method fires for the first curve?
        curves = det.extract_curves(df)
        print(f"  extract_curves -> n_curves={len(curves)}")
        for i, c in enumerate(curves):
            print(f"    curve {i+1}: start={c['start_idx']} end={c['end_idx']} "
                  f"duration_min={c['duration']:.2f} max_temp={c['max_temp']:.2f} "
                  f"truncated={c['truncated']} samples={c['samples']}")

        # Full trace: mid-bake vs cold-start
        mid_bake_fires = (core[0] >= room_temp_max)
        print(f"  mid-bake fires at 0? (core[0]>={room_temp_max}): {mid_bake_fires}")

        if len(curves) >= 1:
            s0 = curves[0]['start_idx']
            print(f"  -> first curve start = {s0}")
            # Deduce which method produced it
            fp = first_pred_state_transition(pred_state)
            if fp is not None and fp == s0:
                print(f"     method: PredictionState (method 1) — idx {fp}")
            elif mid_bake_fires and s0 == 0:
                print(f"     method: mid-bake (2a) — first sample already >=room_temp_max")
            elif cross_max is not None and cross_max == s0:
                print(f"     method: cold-start max-sensor (2b) — idx {cross_max}")
            else:
                print(f"     method: UNCLEAR — fp={fp}, cross_max={cross_max}, cross_core={cross_core}")

        # For 1759: also report bake 2/3 cross-over points in detail
        if name == "1000BA3C_1759":
            print("  --- 1759 DEEP DIVE ---")
            print(f"    core[0..20]: {core[0:20].tolist()}")
            if has_all_sensors:
                t8 = df['T8'].to_numpy(dtype=float)
                print(f"    T8 at idx 640..665: "
                      f"{[(i, round(t8[i],2)) for i in range(640, min(666, len(t8)))]}")
                print(f"    max at idx 640..665: "
                      f"{[(i, round(max_sensor[i],2)) for i in range(640, min(666, len(max_sensor)))]}")
                print(f"    T8 at idx 5880..5895: "
                      f"{[(i, round(t8[i],2)) for i in range(5880, min(5896, len(t8)))]}")
                print(f"    core at idx 5880..5895: "
                      f"{[(i, round(core[i],2)) for i in range(5880, min(5896, len(core)))]}")
                # Bake 3 trajectory
                b3_start = 5888 if 5888 < len(core) else None
                if b3_start is not None:
                    print(f"    VCT @ bake3 start ({b3_start}): {core[b3_start]:.2f}")
                    # Span to peak and cliff
                    b3_end = min(6185, len(core) - 1)
                    span = core[b3_start:b3_end + 1]
                    pk_offset = int(np.argmax(span))
                    print(f"    VCT @ bake3 peak  ({b3_start + pk_offset}): {span[pk_offset]:.2f}")
                    print(f"    VCT @ bake3 end   ({b3_end}): {core[b3_end]:.2f}")
                    # Sample a few VCT midpoints in bake 3
                    for s in [b3_start, b3_start + 30, b3_start + 60, b3_start + 120, b3_start + 180, b3_start + 240, b3_start + 280]:
                        if s <= b3_end:
                            print(f"    VCT @ {s}: {core[s]:.2f}")


if __name__ == "__main__":
    main()
