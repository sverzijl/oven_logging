"""Smoke tests pinning the deletion of legacy classifier modules (M3b HMS Bellerophon).

After M3a wired ``spatial_reconstruction.classify`` into ``ThermalProfileLoader``,
the old physics-only sensor classifiers became dead weight.  M3b removes:

  - ``src/data/surface_sensor_detector.py`` (entire file)
  - ``ThermodynamicSensorClassifier`` class from
    ``src/data/thermodynamic_sensor_classifier.py``  (the
    ``identify_core_sensor_combined_rank`` function survives — it's still used
    by ``tests/test_curve_boundary_detection.py``)

These tests guard against accidental resurrection.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def test_surface_sensor_detector_module_deleted():
    """The whole module must be gone — importing it must fail."""
    with pytest.raises((ImportError, ModuleNotFoundError)):
        import src.data.surface_sensor_detector  # noqa: F401


def test_thermodynamic_sensor_classifier_class_deleted():
    """The class is gone but the module remains for identify_core_sensor_combined_rank."""
    from src.data import thermodynamic_sensor_classifier as mod
    assert not hasattr(mod, 'ThermodynamicSensorClassifier'), (
        "ThermodynamicSensorClassifier class must be removed; "
        "spatial_reconstruction.classify is the canonical classifier."
    )


def test_identify_core_sensor_combined_rank_still_callable():
    """The detector helper is still imported by curve-boundary tests; preserve it."""
    from src.data.thermodynamic_sensor_classifier import (
        identify_core_sensor_combined_rank,
    )
    assert callable(identify_core_sensor_combined_rank)
