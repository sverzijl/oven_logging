"""Figure out WHICH candidate is firing on noisy unlidded CSVs.

Monkey-patches CurveBoundaryDetector's candidate methods to log which one won.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _ROOT)

from config import constants  # noqa: E402
from src.data.curve_boundary_detector import CurveBoundaryDetector  # noqa: E402
from tests.fixtures.curve_boundary_cases import CASES  # noqa: E402


def make_instrumented():
    """Return a subclass that records which candidate fired per curve."""
    class Instrumented(CurveBoundaryDetector):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.winners = []

        def _evaluate_exit_candidates(self, temps, timestamps, j, peak_idx, peak_temp, cool_window):
            first_scan = peak_idx + self._post_peak_grace
            upto = j + 1
            cands = {}
            cands["drop_rate"] = self._candidate_drop_rate(temps[:upto], timestamps[:upto], first_scan)
            cands["cool"] = self._candidate_cool_to_ambient(temps[:upto], first_scan, cool_window)
            cands["roomplateau"] = self._candidate_room_temp_plateau(temps[:upto], first_scan, cool_window)
            cands["dip_rerise"] = self._candidate_dip_with_rerise(temps[:upto], peak_idx, peak_temp)
            cands["corepeak"] = self._candidate_core_peak_plateau(temps[:upto], timestamps[:upto], peak_idx, first_scan)
            cands["cliff"] = self._candidate_probe_pull_cliff(temps[:upto], timestamps[:upto], peak_idx)
            valid = {k: v for k, v in cands.items() if v is not None}
            if not valid:
                return None, False
            winner_key = min(valid, key=lambda k: valid[k])
            winner_idx = valid[winner_key]
            plateau_fired = (cands["corepeak"] is not None and winner_idx == cands["corepeak"])
            return winner_idx, plateau_fired

        def extract_curves(self, df):
            self.winners = []
            self._current_per_curve_winners = []
            # Need to hook per-curve to attribute the winning candidate.
            return super().extract_curves(df)

    return Instrumented


def candidate_of_end(det: CurveBoundaryDetector, df, curve_end_idx: int, peak_idx: int) -> str:
    """Post-hoc: which candidate would return this end idx?"""
    from src.data.column_helpers import resolve_core_temperature_series
    temps = resolve_core_temperature_series(df).to_numpy(dtype=float)
    ts = df["Timestamp"].to_numpy(dtype=float)
    first_scan = peak_idx + det._post_peak_grace
    # Provide the full arrays (no truncation) and see which candidates match the exact end_idx.
    # Choose highest-probability match.
    upto = len(temps)
    cool_window = det._long_cool_window_samples(ts)
    cands = {}
    cands["drop_rate"] = det._candidate_drop_rate(temps[:upto], ts[:upto], first_scan)
    cands["cool"] = det._candidate_cool_to_ambient(temps[:upto], first_scan, cool_window)
    cands["roomplateau"] = det._candidate_room_temp_plateau(temps[:upto], first_scan, cool_window)
    peak_temp = float(temps[peak_idx])
    cands["dip_rerise"] = det._candidate_dip_with_rerise(temps[:upto], peak_idx, peak_temp)
    cands["corepeak"] = det._candidate_core_peak_plateau(temps[:upto], ts[:upto], peak_idx, first_scan)
    cands["cliff"] = det._candidate_probe_pull_cliff(temps[:upto], ts[:upto], peak_idx)
    # Remove None / and those that don't match the end idx
    matches = {k: v for k, v in cands.items() if v == curve_end_idx}
    return ",".join(sorted(matches.keys())) if matches else "NONE(eof?)"


def main():
    import numpy as np
    cfg = dict(constants.CURVE_DETECTION_CONFIG)
    unlidded = {
        "real_100098DE_1351": 329,
        "real_1000BA3C_0946": 299,
        "real_1000BA3C_1759": 955,  # bake 1
    }
    for sigma in (0.3, 1.0):
        print(f"\n=== σ={sigma} — which candidate wins on spurious end? ===")
        for name, exp in unlidded.items():
            df0 = next(c for c in CASES if c["name"] == name)["df"]
            winners = Counter()
            for seed in range(40):
                rng = np.random.default_rng(seed)
                d = df0.copy()
                noise = rng.normal(0.0, sigma, len(d))
                if "CoreTemperature" in d.columns:
                    d["CoreTemperature"] = d["CoreTemperature"].to_numpy(dtype=float) + noise
                if "VirtualCoreTemperature" in d.columns:
                    d["VirtualCoreTemperature"] = d["VirtualCoreTemperature"].to_numpy(dtype=float) + noise
                det = CurveBoundaryDetector(cfg)
                curves = det.extract_curves(d)
                if not curves:
                    winners["none"] += 1
                    continue
                c0 = curves[0]
                # Find peak idx in noisy data
                from src.data.column_helpers import resolve_core_temperature_series
                temps = resolve_core_temperature_series(d).to_numpy(dtype=float)
                # search for peak within the curve span
                peak_idx = int(np.argmax(temps[: c0["end_idx"] + 1]))
                cand = candidate_of_end(det, d, c0["end_idx"], peak_idx)
                winners[cand] += 1
            print(f"  {name:<40} {dict(winners)}")


if __name__ == "__main__":
    main()
