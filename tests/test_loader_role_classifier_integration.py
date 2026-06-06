"""End-to-end loader integration of the spatial-reconstruction classifier.

After M3a HMS Royal Sovereign the loader's per-curve role identification is
a single call to ``spatial_reconstruction.classify``. This test exercises the
full path: load a real CSV, segment curves, classify per curve, and verify
the loader-level getters return the expected sensors and interpolated series.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import ThermalProfileLoader


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNLIDDED_FIXTURE = os.path.join(
    REPO_ROOT, 'ProbeData_100098DE_2025-05-30 13_51_07.csv'
)
LIDDED_FIXTURE = os.path.join(REPO_ROOT, 'wonder white 10k 13.01.2026.csv')


@pytest.fixture
def unlidded_loader():
    assert os.path.exists(UNLIDDED_FIXTURE), f"fixture missing: {UNLIDDED_FIXTURE}"
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=UNLIDDED_FIXTURE)
    return loader


@pytest.fixture
def lidded_loader():
    assert os.path.exists(LIDDED_FIXTURE), f"fixture missing: {LIDDED_FIXTURE}"
    loader = ThermalProfileLoader()
    loader.load_csv(file_path=LIDDED_FIXTURE)
    return loader


class TestLoaderRoleAssignments:
    """Real-CSV loader path returns the same answers as direct classify()."""

    def test_unlidded_core_is_T4(self, unlidded_loader):
        assert unlidded_loader.get_core_sensor(0) == 'T4'

    def test_unlidded_surface_is_T7(self, unlidded_loader):
        assert unlidded_loader.get_surface_sensor(0) == 'T7'

    def test_unlidded_ambient_is_T8(self, unlidded_loader):
        assert sorted(unlidded_loader.get_ambient_sensors(0)) == ['T8']

    def test_unlidded_no_lid(self, unlidded_loader):
        assert unlidded_loader.get_lid_sensor(0) is None

    def test_lidded_no_lid_contact(self, lidded_loader):
        # The lidded fixture's annotation is None — the lid is present but does
        # not touch any sensor.
        assert lidded_loader.get_lid_sensor(0) is None


class TestLoaderInterpolatedSeries:
    """``get_*_temperature_series`` getters return aligned pandas Series."""

    def test_core_series_length_matches_curve(self, unlidded_loader):
        s = unlidded_loader.get_core_temperature_series(0)
        assert isinstance(s, pd.Series)
        assert len(s) == len(unlidded_loader.all_curves[0]['data'])

    def test_surface_series_present(self, unlidded_loader):
        s = unlidded_loader.get_surface_temperature_series(0)
        assert isinstance(s, pd.Series)

    def test_ambient_series_present(self, unlidded_loader):
        s = unlidded_loader.get_ambient_temperature_series(0)
        assert isinstance(s, pd.Series)

    def test_lid_series_none_when_no_lid(self, unlidded_loader):
        assert unlidded_loader.get_lid_temperature_series(0) is None


class TestLidColumnLifecycle:
    """LidTemperature column lifecycle under classifier control.

    The unlidded fixture must NOT add a LidTemperature column to the curve
    DataFrame; the lidded fixture, even when annotated as None, must also
    not add one (assignment.lid is None for that fixture).
    """

    def test_unlidded_no_lid_column(self, unlidded_loader):
        df = unlidded_loader.data
        assert 'LidTemperature' not in df.columns, (
            "Unlidded fixture must not have LidTemperature column"
        )

    def test_lidded_fixture_no_lid_column_when_assignment_lid_is_none(
        self, lidded_loader
    ):
        # Annotation says no lid contact for this fixture; classifier
        # should agree, so no LidTemperature column.
        df = lidded_loader.data
        assert 'LidTemperature' not in df.columns


class TestStandardColumnsMatchClassifier:
    """The standardised columns track the classifier's continuous-position
    interpolation. With M6 hot-fix HMS Penelope, the columns are NO LONGER
    byte-identical to the nearest-sensor series; they are the per-timestep
    spatial interpolation at the inferred continuous position. The
    nearest-sensor-anchor contract still holds for override targeting."""

    def test_core_temperature_tracks_classifier_nearest_sensor(self, unlidded_loader):
        loader = unlidded_loader
        df = loader.data
        core_sensor = loader.get_core_sensor(0)
        assert core_sensor in df.columns
        # The interpolated CoreTemperature must track the nearest sensor
        # closely (same sign, same overall magnitude), but is not
        # byte-identical when interpolation engages.
        core = df['CoreTemperature'].values
        anchor = df[core_sensor].values
        max_diff = float(np.max(np.abs(core - anchor)))
        assert max_diff < 50.0, (
            f"CoreTemperature deviates wildly from nearest sensor "
            f"{core_sensor!r} (max diff {max_diff:.2f} °C)"
        )

    def test_surface_temperature_tracks_classifier_nearest_sensor(self, unlidded_loader):
        loader = unlidded_loader
        df = loader.data
        surface_sensor = loader.get_surface_sensor(0)
        assert surface_sensor in df.columns
        surface = df['SurfaceTemperature'].values
        anchor = df[surface_sensor].values
        max_diff = float(np.max(np.abs(surface - anchor)))
        assert max_diff < 50.0, (
            f"SurfaceTemperature deviates wildly from nearest sensor "
            f"{surface_sensor!r} (max diff {max_diff:.2f} °C)"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
