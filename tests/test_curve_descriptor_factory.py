"""Tests for the shared ``build_curve_descriptor`` factory (S1).

The canonical curve-descriptor dict was previously constructed three times
(detector ``extract_curves``; loader ``_apply_boundary_overrides``; loader
``_build_user_added_curve_dict``).  The two loader copies computed ``max_temp``
from a ``CoreTemperature``-first channel while the detector used
``resolve_core_temperature_series`` (``VirtualCoreTemperature``-first), so an
override/user-added curve's peak could come from a *different* sensor channel
than detection used.  ``build_curve_descriptor`` is the single source of truth;
all three producers route through it and share the detector's VCT-first channel.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.column_helpers import resolve_core_temperature_series  # noqa: E402
from src.data.curve_boundary_detector import build_curve_descriptor  # noqa: E402
from src.data.loader import ThermalProfileLoader  # noqa: E402


def _df_with_divergent_core(n: int = 20) -> pd.DataFrame:
    """DataFrame whose VirtualCoreTemperature peak (100) differs from its
    CoreTemperature peak (90), so a VCT-first vs CoreTemperature-first choice
    is observable in ``max_temp``.
    """
    ts = np.arange(n, dtype=float) * 5.0
    vct = np.linspace(20.0, 100.0, n)
    core = np.linspace(20.0, 90.0, n)
    return pd.DataFrame(
        {
            "Timestamp": ts,
            "VirtualCoreTemperature": vct,
            "CoreTemperature": core,
        }
    )


class TestBuildCurveDescriptor:

    def test_returns_canonical_shape(self):
        df = _df_with_divergent_core(30)
        d = build_curve_descriptor(
            df, 4, 25, curve_number=2, exit_candidate_kind="drop_rate",
            truncated=False,
        )
        assert set(d) == {
            "data", "start_idx", "end_idx", "start_time", "end_time",
            "duration", "max_temp", "curve_number", "samples", "truncated",
            "exit_candidate_kind",
        }
        assert d["start_idx"] == 4 and d["end_idx"] == 25
        assert d["samples"] == 25 - 4 + 1
        assert len(d["data"]) == 25 - 4 + 1
        assert d["curve_number"] == 2
        assert d["exit_candidate_kind"] == "drop_rate"
        assert d["truncated"] is False
        # start/end times come from the ORIGINAL (pre-rezero) timestamps
        assert d["start_time"] == pytest.approx(df["Timestamp"].iloc[4])
        assert d["end_time"] == pytest.approx(df["Timestamp"].iloc[25])
        # slice Timestamp is re-zeroed and TimeMinutes added
        assert d["data"]["Timestamp"].iloc[0] == 0.0
        assert "TimeMinutes" in d["data"].columns
        assert d["duration"] == pytest.approx(d["data"]["TimeMinutes"].max())

    def test_max_temp_uses_resolve_core_chain_vct_first(self):
        df = _df_with_divergent_core(20)
        d = build_curve_descriptor(
            df, 0, 19, curve_number=1, exit_candidate_kind="x", truncated=False,
        )
        # VCT-first: peak is 100 (VCT), NOT 90 (CoreTemperature).
        assert d["max_temp"] == pytest.approx(100.0)
        assert d["max_temp"] == pytest.approx(
            float(resolve_core_temperature_series(df.iloc[0:20]).max())
        )

    def test_reversed_slice_raises_valueerror(self):
        df = _df_with_divergent_core(10)
        with pytest.raises(ValueError):
            build_curve_descriptor(
                df, 5, 2, curve_number=1, exit_candidate_kind="x", truncated=False,
            )


class TestLoaderBuildersUseResolveCoreChain:
    """The loader's override + user-added builders must share the factory's
    VCT-first channel (previously CoreTemperature-first, diverging from the
    detector)."""

    def test_override_max_temp_uses_vct_not_core_temperature(self):
        df = _df_with_divergent_core(20)
        loader = ThermalProfileLoader()
        loader._boundary_overrides = {0: (0, 19)}
        out = loader._apply_boundary_overrides(df, [None])
        # Fails under the old CoreTemperature-first code (would be 90.0).
        assert out[0]["max_temp"] == pytest.approx(100.0)
        assert out[0]["exit_candidate_kind"] == "manual_override"

    def test_user_added_max_temp_uses_vct_not_core_temperature(self):
        df = _df_with_divergent_core(20)
        loader = ThermalProfileLoader()
        d = loader._build_user_added_curve_dict(df, 0, 19, added_idx=0)
        assert d["max_temp"] == pytest.approx(100.0)
        assert d["exit_candidate_kind"] == "user_added"
        assert d["_user_added_idx"] == 0
