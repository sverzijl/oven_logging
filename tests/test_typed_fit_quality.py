"""M3 — typed fit_quality pin tests (M28).

``ProfileFit.fit_quality`` is now a frozen, dict-compatible dataclass
(``PiecewiseFitQuality`` / ``StefanFitQuality``) instead of a free-form dict.
The dict-compatible ``.get(key, default)`` surface is preserved so the
model-agnostic classifier / comparison readers work unchanged; a key absent
from one model's dataclass returns the ``.get`` default exactly as before.
"""

from __future__ import annotations

import dataclasses
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.spatial_reconstruction.classifier import classify  # noqa: E402
from src.data.spatial_reconstruction.piecewise import PiecewiseFitQuality  # noqa: E402
from src.data.spatial_reconstruction.profile import _FitQualityMapping  # noqa: E402
from src.data.spatial_reconstruction.stefan import StefanFitQuality  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BA3C_0946_CSV = os.path.join(
    REPO_ROOT, "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"
)


@pytest.fixture(scope="module")
def ba3c_df():
    pytest.importorskip("scipy")
    if not os.path.exists(_BA3C_0946_CSV):
        pytest.skip(f"fixture missing: {_BA3C_0946_CSV}")
    from src.data.loader import ThermalProfileLoader

    loader = ThermalProfileLoader()
    loader.load_csv(file_path=_BA3C_0946_CSV)
    assert loader.all_curves
    df = loader.all_curves[0]["data"]
    period = int(loader.metadata.get("sample_period_ms", 5000))
    return df, period


class TestPiecewiseFitQualityType:

    def test_piecewise_fit_quality_is_typed(self, ba3c_df):
        df, period = ba3c_df
        result = classify(df, sample_period_ms=period, model="piecewise")
        fq = result.profile_fit.fit_quality
        assert isinstance(fq, PiecewiseFitQuality)
        assert isinstance(fq, _FitQualityMapping)

    def test_attribute_and_get_agree(self, ba3c_df):
        df, period = ba3c_df
        fq = classify(df, sample_period_ms=period).profile_fit.fit_quality
        assert fq.get("in_dough_indices") == fq.in_dough_indices
        assert fq.get("core_confidence_label", "x") == fq.core_confidence_label
        assert fq.core_confidence_label in {"high", "medium", "low_extrapolated"}

    def test_missing_key_returns_default(self, ba3c_df):
        df, period = ba3c_df
        fq = classify(df, sample_period_ms=period).profile_fit.fit_quality
        # Stefan-only keys are absent from the piecewise dataclass.
        assert fq.get("alpha_crust") is None
        assert fq.get("alpha_crust", 1.23) == 1.23

    def test_dict_compatible_access(self, ba3c_df):
        df, period = ba3c_df
        fq = classify(df, sample_period_ms=period).profile_fit.fit_quality
        assert "in_dough_indices" in fq
        assert "alpha_crust" not in fq
        assert fq["in_dough_indices"] == fq.in_dough_indices
        with pytest.raises(KeyError):
            _ = fq["alpha_crust"]

    def test_is_frozen(self, ba3c_df):
        df, period = ba3c_df
        fq = classify(df, sample_period_ms=period).profile_fit.fit_quality
        with pytest.raises(dataclasses.FrozenInstanceError):
            fq.residual_sse = 0.0


class TestStefanFitQualityType:

    def test_stefan_fit_quality_is_typed(self, ba3c_df):
        df, period = ba3c_df
        result = classify(df, sample_period_ms=period, model="stefan")
        fq = result.profile_fit.fit_quality
        assert isinstance(fq, StefanFitQuality)
        assert isinstance(fq, _FitQualityMapping)

    def test_stefan_has_crust_fields_and_get_default_for_core_label(self, ba3c_df):
        df, period = ba3c_df
        fq = classify(df, sample_period_ms=period, model="stefan").profile_fit.fit_quality
        # Stefan-specific diagnostics are present...
        assert fq.get("alpha_crust") is not None
        assert "T_cavity" in fq
        assert isinstance(fq.n_crossings_100c, int)
        # ...and the piecewise-only confidence label falls back to "high",
        # exactly as the old free-form dict's .get() did.
        assert fq.get("core_confidence_label", "high") == "high"
        # Shared model-agnostic keys exist for classifier consumption.
        assert "in_dough_indices" in fq
        assert "air_indices" in fq
