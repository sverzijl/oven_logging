"""Automatic sensor-role detection and thermodynamic validation.

Owns the logic for deriving which physical sensors (T1..T8) map to
each role (core / surface / ambient) when the user has not supplied a
manual override, and for sanity-checking those assignments against
physical expectations (temperature ordering, early-phase heating rate,
assignment consistency).

Extracted from ``ThermalProfileLoader`` as part of the T5 structural
refactor. The manager reads its state live from the owning loader so
the contract is identical to the pre-extraction in-line methods —
mutations the loader performs after construction (populating
``curve_sensor_assignments``, updating ``sensor_assignments``) are
visible here without any rewiring.
"""

from typing import List

import numpy as np
import pandas as pd


class SensorAssignmentManager:
    """Automatic sensor-role detection and thermodynamic validation.

    Parameters
    ----------
    owner:
        The ``ThermalProfileLoader`` that owns ``curve_sensor_assignments``
        and ``sensor_assignments``. Attributes are read live so the
        loader remains the single source of truth.
    """

    def __init__(self, owner):
        self._owner = owner

    def get_automatic_core_sensors(self, curve_index: int) -> List[str]:
        """Get automatically detected core sensors for a specific curve."""
        owner = self._owner
        if hasattr(owner, 'curve_sensor_assignments') and curve_index in owner.curve_sensor_assignments:
            curve_assignments = owner.curve_sensor_assignments[curve_index]
            core_assignment = curve_assignments.get('core', '')
            # Physics-corrected core wins over firmware VirtualCoreSensor mode —
            # the core_info dict still reflects the raw firmware histogram, so
            # route through the authoritative 'core' key when corrected.
            if curve_assignments.get('core_physics_corrected') and core_assignment and core_assignment != 'Unknown':
                return [core_assignment]
            if 'core_info' in curve_assignments:
                all_sensors = curve_assignments['core_info'].get('all_sensors', {})
                return list(all_sensors.keys())
            elif core_assignment and core_assignment != 'Unknown':
                return [s.strip() for s in core_assignment.split(',')]

        return ['T1', 'T2', 'T3', 'T4']

    def get_automatic_surface_sensors(self, curve_index: int) -> List[str]:
        """Get automatically detected surface sensors for a specific curve."""
        owner = self._owner
        if hasattr(owner, 'curve_sensor_assignments') and curve_index in owner.curve_sensor_assignments:
            curve_assignments = owner.curve_sensor_assignments[curve_index]
            surface_assignment = curve_assignments.get('surface', '')
            if surface_assignment and surface_assignment != 'Unknown':
                return [surface_assignment]

        return ['T7']

    def get_automatic_ambient_sensors(self, curve_index: int) -> List[str]:
        """Get automatically detected ambient sensors for a specific curve."""
        owner = self._owner
        if hasattr(owner, 'curve_sensor_assignments') and curve_index in owner.curve_sensor_assignments:
            curve_assignments = owner.curve_sensor_assignments[curve_index]
            ambient_assignment = curve_assignments.get('ambient', '')
            if ambient_assignment and ambient_assignment != 'Unknown':
                return [ambient_assignment]

        return ['T8']

    def validate_sensor_assignments(self, df: pd.DataFrame) -> None:
        """Validate sensor assignments using thermodynamic principles.

        Prints warnings if assignments seem inconsistent with expected
        physics (core < surface < ambient, plausible heating rates,
        stable per-sample assignment). Returns ``None``.
        """
        owner = self._owner

        temp_cols = [col for col in df.columns if col.startswith('T') and col[1:].isdigit()]
        if len(temp_cols) < 3:
            return

        role_temps = {}
        for role in ['core', 'surface', 'ambient']:
            sensor = owner.sensor_assignments.get(role)
            if sensor and sensor in temp_cols:
                role_temps[role] = {
                    'sensor': sensor,
                    'mean': df[sensor].mean(),
                    'max': df[sensor].max()
                }

        warnings = []

        if 'core' in role_temps and 'surface' in role_temps:
            if role_temps['core']['mean'] > role_temps['surface']['mean']:
                warnings.append(f"⚠️  Core sensor ({role_temps['core']['sensor']}) has higher average temperature than surface sensor ({role_temps['surface']['sensor']})")

        if 'surface' in role_temps and 'ambient' in role_temps:
            if role_temps['surface']['mean'] > role_temps['ambient']['mean']:
                warnings.append(f"⚠️  Surface sensor ({role_temps['surface']['sensor']}) has higher average temperature than ambient sensor ({role_temps['ambient']['sensor']})")

        mask = df['TimeMinutes'] <= 5.0
        if mask.sum() > 2:
            for role, expected_range in [('core', (0.2, 3)), ('surface', (2, 15)), ('ambient', (10, 50))]:
                if role in role_temps:
                    sensor = role_temps[role]['sensor']
                    temps = df.loc[mask, sensor]
                    times = df.loc[mask, 'TimeMinutes']
                    if len(temps) > 2:
                        coeffs = np.polyfit(times, temps, 1)
                        heat_rate = coeffs[0]
                        min_rate, max_rate = expected_range
                        if heat_rate < min_rate or heat_rate > max_rate:
                            warnings.append(f"⚠️  {role.capitalize()} sensor ({sensor}) has unusual heating rate: {heat_rate:.1f}°C/min (expected {min_rate}-{max_rate}°C/min)")

        for role, info in [('core', 'core_info'), ('surface', 'surface_info'), ('ambient', 'ambient_info')]:
            if info in owner.sensor_assignments:
                percentage = owner.sensor_assignments[info].get('percentage', 100)
                if percentage < 80:
                    warnings.append(f"⚠️  {role.capitalize()} sensor assignment changes frequently ({percentage:.1f}% consistency) - probe may not be properly inserted")

        if warnings:
            print("\nSensor Assignment Validation Warnings:")
            for warning in warnings:
                print(f"  {warning}")

            try:
                from ..data.thermodynamic_sensor_classifier import ThermodynamicSensorClassifier
                classifier = ThermodynamicSensorClassifier(df, temp_cols)
                thermo_assignments = classifier.classify_sensors()

                print("\n  Alternative thermodynamic classification suggests:")
                for role, sensors in thermo_assignments.items():
                    print(f"    {role.upper()}: {', '.join(sensors)}")
            except Exception:
                pass
