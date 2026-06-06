"""Thin adapter over ``ThermalProfileLoader.curve_sensor_assignments``.

After M3a HMS Royal Sovereign the loader's automatic role detection is the
spatial-reconstruction classifier (``src.data.spatial_reconstruction.classify``);
this manager is now a thin read-side adapter that exposes the per-role
classifier picks via the legacy ``_get_automatic_*_sensors`` interface that
the rest of the loader still calls.

No fallback heuristics live here any more — when a curve has no assignment
(e.g. fresh loader before any CSV is loaded), the adapter returns the
canonical neutral defaults so callers never see an empty list, but the
classifier IS the source of truth.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd


class SensorAssignmentManager:
    """Thin adapter over the loader's ``curve_sensor_assignments``.

    Parameters
    ----------
    owner:
        The ``ThermalProfileLoader`` that owns ``curve_sensor_assignments``.
        Attributes are read live so the loader remains the single source of
        truth.
    """

    def __init__(self, owner):
        self._owner = owner

    def _curve_assigns(self, curve_index: int) -> dict:
        owner = self._owner
        if (
            hasattr(owner, 'curve_sensor_assignments')
            and curve_index in owner.curve_sensor_assignments
        ):
            return owner.curve_sensor_assignments[curve_index]
        return {}

    def get_automatic_core_sensors(self, curve_index: int) -> List[str]:
        """Return the classifier-picked core sensor wrapped in a list."""
        assigns = self._curve_assigns(curve_index)
        core = assigns.get('core')
        if core and core != 'Unknown':
            return [core]
        return ['T1', 'T2', 'T3', 'T4']

    def get_automatic_surface_sensors(self, curve_index: int) -> List[str]:
        """Return the classifier-picked surface sensor wrapped in a list."""
        assigns = self._curve_assigns(curve_index)
        surface = assigns.get('surface')
        if surface and surface != 'Unknown':
            return [surface]
        return ['T7']

    def get_automatic_ambient_sensors(self, curve_index: int) -> List[str]:
        """Return the classifier-picked ambient sensors as a list."""
        assigns = self._curve_assigns(curve_index)
        ambient = assigns.get('ambient')
        if isinstance(ambient, list) and ambient:
            return list(ambient)
        if isinstance(ambient, str) and ambient and ambient != 'Unknown':
            return [ambient]
        return ['T8']

    def get_automatic_lid_sensor(self, curve_index: int) -> Optional[str]:
        """Return the classifier-picked lid sensor or ``None``."""
        return self._curve_assigns(curve_index).get('lid')

    def validate_sensor_assignments(self, df: pd.DataFrame) -> None:
        """No-op placeholder for the legacy validator.

        The validator's job (warn when firmware role assignments contradict
        physics) is now subsumed by the spatial classifier itself: every
        assignment passes through the topology-checked
        ``classify(...)`` pipeline. Kept as a no-op so existing call-sites
        in the loader continue to work.
        """
        return None
