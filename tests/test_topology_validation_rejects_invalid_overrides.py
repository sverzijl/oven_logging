"""Topology validation for sensor-role overrides (M3b HMS Bellerophon).

The probe is a 1D rod with sensors T1..T8 ordered along its length. Physically
valid role topology, with the convention that lower sensor numbers are deeper
inside the loaf:

    core_idx < surface_idx <= min(ambient_idx) <= max(ambient_idx) <= lid_idx

Through-loaf exception: the operator may insert the probe so it pierces the
loaf and emerges out the far side. In that case ambient sensors split into TWO
contiguous groups (e.g. T1 inside the oven air below, T8 above) and the
surface sensor sits between them. The validator must accept that geometry.

These tests pin the validator behaviour BEFORE it exists (TDD failing-first).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pathlib

import pytest

from src.data.loader import ThermalProfileLoader

REPO = pathlib.Path(__file__).resolve().parents[1]
SINGLE_CURVE_CSV = REPO / 'ProbeData_1000F3C1_2025-05-23 09_11_59.csv'


def make_loader() -> ThermalProfileLoader:
    loader = ThermalProfileLoader()
    loader.load_csv(str(SINGLE_CURVE_CSV))
    return loader


class TestCoreSurfaceTopology:
    """core_idx < surface_idx is the most basic constraint."""

    def test_core_above_surface_raises(self):
        """core='T5' with surface='T2' must raise — core (5) > surface (2)."""
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')  # establish a valid base
        loader.set_sensor_override(0, 'surface', 'T7')
        with pytest.raises(ValueError, match=r"(?i)core.*surface"):
            loader.set_sensor_override(0, 'core', 'T5')
            loader.set_sensor_override(0, 'surface', 'T2')

    def test_core_equals_surface_raises(self):
        """core and surface may not be the same sensor."""
        loader = make_loader()
        with pytest.raises(ValueError):
            loader.set_sensor_override(0, 'core', 'T3')
            loader.set_sensor_override(0, 'surface', 'T3')


class TestAmbientPositionConstraint:
    """All ambient sensors must be at or above the surface sensor (or split through-loaf)."""

    def test_ambient_below_surface_raises(self):
        """surface=T5, ambient=[T2] must raise — ambient (2) < surface (5)."""
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T5')
        with pytest.raises(ValueError, match=r"(?i)ambient"):
            loader.set_sensor_override(0, 'ambient', ['T2'])

    def test_ambient_above_surface_passes(self):
        """surface=T5, ambient=[T6,T7,T8] should be accepted."""
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T5')
        loader.set_sensor_override(0, 'ambient', ['T6', 'T7', 'T8'])  # no raise

    def test_through_loaf_ambient_split_passes(self):
        """surface=T4, ambient=[T1,T8] (split each side of loaf) must pass."""
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T2')  # core deeper than surface (4)
        # Hmm — core must be < surface, so set core=T2 first, surface=T3 first to
        # establish, THEN set surface to T4 alongside through-loaf ambients.
        loader.set_sensor_override(0, 'surface', 'T3')
        # Through-loaf: ambient on BOTH sides of the surface, contiguous groups.
        # surface=T4, ambient=[T1, T8] — T1 is the only "lower" group; T8 is "upper".
        # We need the validator to detect this pattern and accept it.
        loader.set_sensor_override(0, 'core', 'T2')
        loader.set_sensor_override(0, 'surface', 'T4')
        # T1 (single-element group below surface) + T8 (single-element group above):
        # surface (4) sits between the two groups. Through-loaf accept.
        loader.set_sensor_override(0, 'ambient', ['T1', 'T8'])

    def test_through_loaf_with_internal_ambient_below_surface_raises(self):
        """Ambient that extends INTO the loaf (not split with surface between) must fail.

        Example: surface=T6, ambient=[T2, T3, T7, T8] — the lower group [T2,T3] is
        not at the probe-end (T1 missing) AND surface=T6 doesn't sit *between* the
        groups in the through-loaf sense.  Reject.
        """
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T6')
        with pytest.raises(ValueError):
            loader.set_sensor_override(0, 'ambient', ['T2', 'T3', 'T7', 'T8'])

    def test_through_loaf_core_inside_lower_ambient_group_raises(self):
        """Finding 5: in a through-loaf split, the core must sit ABOVE the
        lower (air-below) ambient group. A core at/within that group is in the
        oven air, not the loaf, and must be rejected.

        Geometry: ambient=[T1, T2, T8] (lower air-below group T1-T2, upper
        air-above T8), surface=T4. core=T2 lies inside the lower-ambient
        group — invalid. Valid core would be T3 (between max(lower)=T2 and
        surface=T4).
        """
        loader = make_loader()
        # Establish a valid through-loaf base with core=T3.
        loader.set_sensor_override(0, 'core', 'T3')
        loader.set_sensor_override(0, 'surface', 'T4')
        loader.set_sensor_override(0, 'ambient', ['T1', 'T2', 'T8'])  # accepted
        # Now lower core into the lower-ambient group — must raise.
        with pytest.raises(ValueError, match=r"(?i)core.*ambient|ambient.*core"):
            loader.set_sensor_override(0, 'core', 'T2')

    def test_through_loaf_core_above_lower_ambient_group_passes(self):
        """Companion to the above: core strictly above the lower-ambient
        group (and below surface) is the valid through-loaf core."""
        loader = make_loader()
        loader.set_sensor_override(0, 'surface', 'T4')
        loader.set_sensor_override(0, 'ambient', ['T1', 'T2', 'T8'])
        loader.set_sensor_override(0, 'core', 'T3')  # must NOT raise


class TestLidPositionConstraint:
    """lid_idx >= max(ambient_idx) when both are present."""

    def test_lid_below_ambient_raises(self):
        """ambient=[T6,T7], lid=T5 must raise — lid (5) < max(ambient)=7."""
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T5')
        loader.set_sensor_override(0, 'ambient', ['T6', 'T7'])
        with pytest.raises(ValueError, match=r"(?i)lid"):
            loader.set_sensor_override(0, 'lid', 'T5')

    def test_lid_above_max_ambient_passes(self):
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T5')
        loader.set_sensor_override(0, 'ambient', ['T6', 'T7'])
        loader.set_sensor_override(0, 'lid', 'T8')  # 8 >= 7

    def test_lid_equal_max_ambient_passes(self):
        """lid_idx == max(ambient_idx) is permitted (lid IS the topmost ambient)."""
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T5')
        loader.set_sensor_override(0, 'ambient', ['T6', 'T7'])
        loader.set_sensor_override(0, 'lid', 'T7')

    def test_lid_none_clears(self):
        """Setting lid=None must be accepted and remove any prior lid pick."""
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T1')
        loader.set_sensor_override(0, 'surface', 'T5')
        loader.set_sensor_override(0, 'lid', 'T8')
        loader.set_sensor_override(0, 'lid', None)
        # No assertion needed: the call must not raise. Confirm it's honoured.
        df = loader.all_curves[0]['data']
        assert 'LidTemperature' not in df.columns, (
            "Setting lid=None should drop LidTemperature column"
        )


class TestPartialOverrides:
    """Constraints that don't apply to the supplied subset must not be enforced."""

    def test_core_only_no_surface_passes(self):
        """User sets only core; surface comes from automatic detection — accept."""
        loader = make_loader()
        loader.set_sensor_override(0, 'core', 'T2')

    def test_ambient_only_no_surface_passes(self):
        """Ambient set but neither core nor surface override — accept (uses automatic surface).

        Topology against the AUTOMATIC surface assignment is informational, not a
        hard constraint, because the user may be in mid-edit.
        """
        loader = make_loader()
        loader.set_sensor_override(0, 'ambient', ['T7', 'T8'])
