"""Lid + ambient override flow exercised at the loader level (M3b HMS Bellerophon).

The sidebar UI (sidebar.py) calls ``loader.set_sensor_override(curve_index,
role, value)`` once for each role the operator changes.  These tests pin the
data-flow behaviour for the new ``'ambient'`` (list) and ``'lid'`` (str|None)
roles by driving the loader directly — same pattern as
``tests/test_sensor_role_helpers.py`` (we don't mock streamlit).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pathlib

import numpy as np
import pytest

from src.data.loader import ThermalProfileLoader

REPO = pathlib.Path(__file__).resolve().parents[1]
SINGLE_CURVE_CSV = REPO / 'ProbeData_1000F3C1_2025-05-23 09_11_59.csv'


def make_loader() -> ThermalProfileLoader:
    loader = ThermalProfileLoader()
    loader.load_csv(str(SINGLE_CURVE_CSV))
    return loader


class TestLidOverride:
    def test_lid_override_writes_lid_temperature_column(self):
        """set_sensor_override(0, 'lid', 'T8') must set LidTemperature = df['T8']."""
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T5')
        loader.set_sensor_override(0, 'lid', 'T8')

        df = loader.all_curves[0]['data']
        assert 'LidTemperature' in df.columns, (
            "Lid override must add LidTemperature column"
        )
        np.testing.assert_array_equal(
            df['LidTemperature'].values, df['T8'].values
        )

    def test_lid_override_none_drops_column(self):
        """Setting lid=None when previously set must remove LidTemperature column."""
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T5')
        loader.set_sensor_override(0, 'lid', 'T8')
        df = loader.all_curves[0]['data']
        assert 'LidTemperature' in df.columns

        loader.set_sensor_override(0, 'lid', None)
        df = loader.all_curves[0]['data']
        assert 'LidTemperature' not in df.columns, (
            "lid=None override must drop LidTemperature column"
        )

    def test_get_lid_sensor_returns_override(self):
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T5')
        loader.set_sensor_override(0, 'lid', 'T7')
        assert loader.get_lid_sensor(0) == 'T7'


class TestAmbientOverride:
    def test_ambient_list_override_means_columns(self):
        """ambient=['T7','T8'] override must set AmbientTemperature = mean(T7,T8)."""
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T5')
        loader.set_sensor_override(0, 'ambient', ['T7', 'T8'])

        df = loader.all_curves[0]['data']
        expected = df[['T7', 'T8']].mean(axis=1)
        np.testing.assert_allclose(
            df['AmbientTemperature'].values, expected.values, rtol=1e-9
        )

    def test_ambient_single_string_override_works(self):
        """Backward compat: a string scalar should also be honoured."""
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T5')
        loader.set_sensor_override(0, 'ambient', 'T8')

        df = loader.all_curves[0]['data']
        np.testing.assert_array_equal(
            df['AmbientTemperature'].values, df['T8'].values
        )

    def test_get_ambient_sensors_returns_override_list(self):
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T5')
        loader.set_sensor_override(0, 'ambient', ['T6', 'T7', 'T8'])
        assert loader.get_ambient_sensors(0) == ['T6', 'T7', 'T8']
