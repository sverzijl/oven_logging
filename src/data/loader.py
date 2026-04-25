"""Data loading and parsing utilities for thermal profile CSV files."""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, Union, List
import re
from datetime import datetime
import io

_log = logging.getLogger(__name__)
from config.constants import (
    CORE_DETECTION_CONFIG,
    CURVE_DETECTION_CONFIG,
    INTERNAL_SENSOR_CONFIG,
)
from src.data.sensor_assignment_manager import SensorAssignmentManager
from src.data.column_helpers import (
    get_core_temperature_column,
    resolve_core_temperature_series,
)
from src.data.curve_boundary_detector import CurveBoundaryDetector


class ThermalProfileLoader:
    """Load and parse thermal profile CSV files from Combustion Inc. probes."""

    def __init__(self):
        self.metadata = {}
        self.data = None
        self.sensor_assignments = {}  # Deprecated - kept for backward compatibility
        self.curve_sensor_assignments = {}  # New: per-curve sensor assignments
        self.all_curves = []  # Store all detected curves
        self.current_curve_index = 0  # Track which curve is currently selected
        self._sensor_overrides = {}  # Store sensor overrides per curve {curve_index: {'core': [...], 'surface': [...], 'ambient': [...]}}
        self._sensor_manager = SensorAssignmentManager(self)
        # Optional per-curve expected-duration hint (M5 HMS Dauntless).
        # None = no hint; list[float | None] = positional per-curve hints,
        # matched to detected curves by order.  Consumed by
        # ``_extract_all_baking_curves`` which forwards to
        # ``CurveBoundaryDetector.extract_curves(expected_durations_s=...)``.
        # UI layer (M6 Spartan) sets this via ``set_expected_durations``
        # to get cache-invalidation for free.
        self.expected_durations_s: list[float | None] | None = None
        # Full pre-curve-extraction DataFrame (M1 HMS Ardent, mission
        # 2026-04-24_233307_c5744e63).  Today ``self.data`` is overwritten
        # with the first curve's slice immediately after extraction;
        # ``raw_data`` keeps the full log so the Curve Boundary Review
        # tab (M3) can plot it with detected windows overlaid.
        # Also fixes a latent bug: ``set_expected_durations`` previously
        # re-ran detection on ``self.data`` (the first curve only),
        # silently dropping bakes 2+ on multi-bake CSVs.  Re-detection
        # now uses ``self.raw_data``.
        self.raw_data: pd.DataFrame | None = None
        # Manual per-curve boundary overrides (M1 HMS Ardent).
        # Keyed by curve_index; value is ``(start_idx, end_idx)`` in the
        # raw_data index space.  When present, the override takes
        # precedence over the detector AND the hint refinement.
        self._boundary_overrides: dict[int, tuple[int, int]] = {}
        # User-claimed regions that the detector missed (M11 HMS
        # Endeavour, mission 2026-04-25_111859_56ebe5ee).  Each tuple
        # is ``(start_idx, end_idx)`` in the raw_data index space.
        # The Boundary Review tab populates this via
        # ``add_manual_curve``; the boundaries are auto-refined on
        # the sub-slice and the resulting curve appears in
        # ``all_curves`` tagged with ``_user_added_idx`` (its position
        # in this list).  ``set_curve_boundaries`` on a user-added
        # curve updates THIS list rather than ``_boundary_overrides``.
        self._added_curves: list[tuple[int, int]] = []
        # Snapshot of the detector's no-hint, no-override decision
        # taken at ``load_csv`` time (M7 HMS Inspector, mission
        # 2026-04-25_092326_ec2fbd6e).  The Boundary Review tab uses
        # this to show the operator what the auto-optimisation moved.
        # Subsequent set_expected_durations / set_curve_boundaries
        # calls leave it untouched.
        self.baseline_curves: list = []

    def load_csv(self, file_path: str = None, file_buffer=None) -> Tuple[pd.DataFrame, Dict]:
        """
        Load a thermal profile CSV file.
        
        Args:
            file_path: Path to the CSV file (optional)
            file_buffer: File buffer object (optional)
            
        Returns:
            Tuple of (data DataFrame, metadata dict)
        """
        # Read the metadata from header lines
        if file_buffer is not None:
            # Convert to string buffer if needed
            if hasattr(file_buffer, 'read'):
                # Read all content
                content = file_buffer.read()
                if isinstance(content, bytes):
                    content = content.decode('utf-8')
                
                # Parse metadata from content
                self.metadata = self._parse_metadata_from_content(content)
                
                # Create StringIO for pandas
                content_buffer = io.StringIO(content)
                self.data = pd.read_csv(content_buffer, skiprows=10)
            else:
                raise ValueError("Invalid file buffer provided")
        else:
            self.metadata = self._parse_metadata(file_path)
            # Read the actual data
            self.data = pd.read_csv(file_path, skiprows=10)
        
        # Clean and validate the data
        self.data = self._clean_data(self.data)

        # Preserve the full pre-curve-extraction DataFrame for the
        # Curve Boundary Review tab (M1 HMS Ardent).  ``copy()`` so
        # downstream tab code mutating ``self.data`` cannot leak back.
        self.raw_data = self.data.copy()

        # Extract all baking curves
        self.all_curves = self._extract_all_baking_curves(self.data)

        # Snapshot the detector's no-hint, no-override decision so the
        # Boundary Review tab can show what auto-optimisation moved
        # later (M7 HMS Inspector).  At this point neither
        # expected_durations_s nor _boundary_overrides are populated,
        # so all_curves IS the baseline by definition.
        self.baseline_curves = [self._copy_curve_dict(c) for c in self.all_curves]

        # Set the first curve as default if any curves found
        if self.all_curves:
            self.data = self.all_curves[0]['data']
            self.current_curve_index = 0

        return self.data, self.metadata

    @staticmethod
    def _copy_curve_dict(curve: dict) -> dict:
        """Return an independent copy of a curve descriptor for the
        baseline snapshot.  The ``data`` slice is duplicated so a tab
        mutating it cannot bleed into ``all_curves``; other fields are
        primitives (int/float/bool/str) and copy by value.
        """
        out = dict(curve)
        if "data" in out and out["data"] is not None:
            out["data"] = out["data"].copy()
        return out
    
    def _parse_metadata(self, file_path: str) -> Dict:
        """Parse metadata from the CSV header."""
        metadata = {}
        
        with open(file_path, 'r') as f:
            lines = f.readlines()[:10]
            
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                metadata[key.strip()] = value.strip()
                
        # Parse specific fields
        if 'Sample Period' in metadata:
            # Strip trailing commas from the value
            sample_period_str = metadata['Sample Period'].rstrip(',')
            metadata['sample_period_ms'] = int(sample_period_str)
            metadata['sample_period_s'] = metadata['sample_period_ms'] / 1000.0
            
        if 'Created' in metadata:
            try:
                metadata['created_datetime'] = datetime.strptime(
                    metadata['Created'], 
                    '%Y-%m-%d %H:%M:%S'
                )
            except:
                metadata['created_datetime'] = None
                
        return metadata
    
    def _parse_metadata_from_content(self, content: str) -> Dict:
        """Parse metadata from file content string."""
        metadata = {}
        
        # Split into lines and get first 10
        lines = content.split('\n')[:10]
        
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                metadata[key.strip()] = value.strip()
                
        # Parse specific fields
        if 'Sample Period' in metadata:
            # Strip trailing commas from the value
            sample_period_str = metadata['Sample Period'].rstrip(',')
            metadata['sample_period_ms'] = int(sample_period_str)
            metadata['sample_period_s'] = metadata['sample_period_ms'] / 1000.0
            
        if 'Created' in metadata:
            try:
                metadata['created_datetime'] = datetime.strptime(
                    metadata['Created'], 
                    '%Y-%m-%d %H:%M:%S'
                )
            except:
                metadata['created_datetime'] = None
                
        return metadata
    
    def _parse_metadata_from_buffer(self, file_buffer) -> Dict:
        """Parse metadata from a file buffer."""
        metadata = {}
        
        # Read the file content as string
        content = file_buffer.read()
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        
        # Split into lines and get first 10
        lines = content.split('\n')[:10]
        
        # Reset buffer position for later use
        file_buffer.seek(0)
        
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                metadata[key.strip()] = value.strip()
                
        # Parse specific fields
        if 'Sample Period' in metadata:
            # Strip trailing commas from the value
            sample_period_str = metadata['Sample Period'].rstrip(',')
            metadata['sample_period_ms'] = int(sample_period_str)
            metadata['sample_period_s'] = metadata['sample_period_ms'] / 1000.0
            
        if 'Created' in metadata:
            try:
                metadata['created_datetime'] = datetime.strptime(
                    metadata['Created'], 
                    '%Y-%m-%d %H:%M:%S'
                )
            except:
                metadata['created_datetime'] = None
                
        return metadata
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and validate the data."""
        # Ensure numeric columns are float
        numeric_columns = ['Timestamp', 'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8',
                          'VirtualCoreTemperature', 'VirtualSurfaceTemperature', 
                          'VirtualAmbientTemperature', 'EstimatedCoreTemperature']
        
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Add time in minutes
        df['TimeMinutes'] = df['Timestamp'] / 60.0
        
        # Note: Sensor identification is now done per-curve in _extract_all_baking_curves
        # This ensures each curve gets its own sensor assignments
        
        # However, we need basic temperature columns for curve extraction
        # These will be overwritten with proper sensor identification per curve
        if 'CoreTemperature' not in df.columns:
            try:
                df['CoreTemperature'] = resolve_core_temperature_series(df)
            except KeyError:
                if 'T1' in df.columns:
                    df['CoreTemperature'] = df['T1']
        
        return df
    
    def _validate_and_fix_sensor_assignments(self, core_sensors: List[str], 
                                               surface_sensors: List[str], 
                                               ambient_sensors: List[str]) -> Tuple[List[str], List[str], List[str]]:
        """Validate and fix sensor assignments to ensure they follow probe physics.
        
        Returns:
            Tuple of (core_sensors, surface_sensors, ambient_sensors) after validation
        """
        # Convert to sensor numbers for easier processing
        def to_nums(sensors):
            return sorted([int(s[1]) for s in sensors if s.startswith('T')])
        
        def to_sensors(nums):
            return [f'T{n}' for n in nums]
        
        core_nums = to_nums(core_sensors)
        surface_nums = to_nums(surface_sensors)
        ambient_nums = to_nums(ambient_sensors)
        
        # Fix overlaps - surface gets priority as it's the interface
        if surface_nums:
            surface_num = surface_nums[0]  # Should only be one
            core_nums = [n for n in core_nums if n < surface_num]
            ambient_nums = [n for n in ambient_nums if n > surface_num]
        
        # Ensure consecutive sensors
        if core_nums:
            min_core = min(core_nums)
            max_core = max(core_nums)
            core_nums = list(range(min_core, max_core + 1))
        
        if ambient_nums:
            min_ambient = min(ambient_nums)
            max_ambient = max(ambient_nums)
            ambient_nums = list(range(min_ambient, max_ambient + 1))
        
        # If no surface sensor but we have core and ambient, place surface between them
        if not surface_nums and core_nums and ambient_nums:
            max_core = max(core_nums)
            min_ambient = min(ambient_nums)
            if max_core + 1 < min_ambient:
                surface_nums = [max_core + 1]
        
        # Ensure surface is single sensor
        if len(surface_nums) > 1:
            # Take the sensor closest to ambient
            surface_nums = [max(surface_nums)]
        
        return (to_sensors(core_nums), 
                to_sensors(surface_nums), 
                to_sensors(ambient_nums))
    
    def _identify_sensor_roles_for_curve(self, df: pd.DataFrame, curve_index: int) -> pd.DataFrame:
        """
        Identify which sensors represent core, surface, and ambient temperatures.
        
        Uses the probe's built-in virtual sensor assignments when available,
        or falls back to dynamic classification based on temperature patterns.
        """
        # Method 1: Use virtual sensor assignments from CSV (preferred)
        virtual_cols = ['VirtualCoreTemperature', 'VirtualSurfaceTemperature', 
                       'VirtualAmbientTemperature']
        assignment_cols = ['VirtualCoreSensor', 'VirtualSurfaceSensor', 
                          'VirtualAmbientSensor']
        
        used_virtual_path = all(col in df.columns for col in virtual_cols + assignment_cols)
        if used_virtual_path:
            # Track most common sensor assignments for each role
            if len(df) > 0:
                curve_assignments = {
                    'core': df['VirtualCoreSensor'].mode().iloc[0] if not df['VirtualCoreSensor'].mode().empty else 'Unknown',
                    'surface': df['VirtualSurfaceSensor'].mode().iloc[0] if not df['VirtualSurfaceSensor'].mode().empty else 'Unknown',
                    'ambient': df['VirtualAmbientSensor'].mode().iloc[0] if not df['VirtualAmbientSensor'].mode().empty else 'Unknown'
                }
                
                # Add assignment frequency info
                for role, col in zip(['core', 'surface', 'ambient'], assignment_cols):
                    if col in df.columns:
                        counts = df[col].value_counts()
                        if len(counts) > 0:
                            primary = counts.index[0]
                            percentage = (counts.iloc[0] / len(df)) * 100
                            curve_assignments[f'{role}_info'] = {
                                'primary': primary,
                                'percentage': percentage,
                                'all_sensors': counts.to_dict()
                            }
                
                # Store per-curve
                self.curve_sensor_assignments[curve_index] = curve_assignments
                
                # Also update deprecated sensor_assignments for backward compatibility
                self.sensor_assignments = curve_assignments
            
            print(f"Curve {curve_index + 1}: Using virtual sensor assignments from CSV:")
            print(f"  Core: {curve_assignments.get('core', 'Unknown')} ({curve_assignments.get('core_info', {}).get('percentage', 0):.1f}% of readings)")
            print(f"  Surface: {curve_assignments.get('surface', 'Unknown')} ({curve_assignments.get('surface_info', {}).get('percentage', 0):.1f}% of readings)")
            print(f"  Ambient: {curve_assignments.get('ambient', 'Unknown')} ({curve_assignments.get('ambient_info', {}).get('percentage', 0):.1f}% of readings)")
            
            # Validate assignments using thermodynamic principles
            self._validate_sensor_assignments(df)
            
            # Apply physics-based surface sensor correction if enabled
            from config.constants import SURFACE_DETECTION_CONFIG
            if SURFACE_DETECTION_CONFIG['USE_PHYSICS_BASED_DETECTION']:
                df = self._apply_physics_based_surface_correction(df, curve_index)

            # Apply physics-based core sensor correction AFTER surface correction
            # so role-order matches the surface pattern (physics > firmware).
            if CORE_DETECTION_CONFIG['ENABLED']:
                df = self._apply_physics_based_core_correction(df, curve_index)

        else:
            # Method 2: Enhanced dynamic classification using thermodynamic principles
            print(f"Curve {curve_index + 1}: Virtual sensor data not available, using thermodynamic classification")
            df = self._classify_sensors_dynamically(df, curve_index)
        
        # For backward compatibility, also create the old average columns
        # but mark them as deprecated
        if all(col in df.columns for col in ['T1', 'T2', 'T3', 'T4']):
            df['CoreAverage'] = df[['T1', 'T2', 'T3', 'T4']].mean(axis=1)
        if all(col in df.columns for col in ['T7', 'T8']):
            df['SurfaceAverage'] = df[['T7', 'T8']].mean(axis=1)
        
        # Generate standardized columns via the single canonical writer.
        # Only run on the virtual-path branch: the dynamic-classification branch
        # below already wrote Core/Surface/Ambient from thermodynamically-chosen
        # sensors and has no Virtual* columns to fall back on, so re-running the
        # helper there would wipe its assignment.
        if used_virtual_path:
            self._apply_standard_columns(df, curve_index)

        return df
    
    def _apply_physics_based_surface_correction(self, df: pd.DataFrame, curve_index: int) -> pd.DataFrame:
        """Apply physics-based surface sensor correction to fix firmware misidentification."""
        from ..data.surface_sensor_detector import identify_surface_sensor_advanced
        from config.constants import SURFACE_DETECTION_CONFIG
        
        # Get sample period from metadata
        sample_period_ms = self.metadata.get('sample_period_ms', 5000)
        
        # Run detection algorithm
        result = identify_surface_sensor_advanced(df, sample_period_ms)
        
        if result and result['confidence'] >= SURFACE_DETECTION_CONFIG['CONFIDENCE_THRESHOLD']:
            # Store original firmware selection for comparison
            curve_assignments = self.curve_sensor_assignments.get(curve_index, {})
            firmware_surface_sensor = curve_assignments.get('surface', 'Unknown')
            firmware_surface_max_temp = df['VirtualSurfaceTemperature'].max() if 'VirtualSurfaceTemperature' in df.columns else 0
            
            # Apply correction
            surface_sensor = result['sensor']
            df['SurfaceTemperature'] = df[surface_sensor]
            df['PhysicsBasedSurfaceDetection'] = True
            
            # Update sensor assignments for this curve
            curve_assignments['surface'] = surface_sensor
            curve_assignments['surface_detection'] = result
            curve_assignments['physics_corrected'] = True
            curve_assignments['firmware_surface_sensor'] = firmware_surface_sensor
            curve_assignments['firmware_surface_max_temp'] = firmware_surface_max_temp
            self.curve_sensor_assignments[curve_index] = curve_assignments
            
            # Update deprecated sensor_assignments for backward compatibility
            self.sensor_assignments = curve_assignments
            
            # Log the correction if enabled
            if SURFACE_DETECTION_CONFIG['LOG_CORRECTIONS']:
                print(f"\n✅ Curve {curve_index + 1}: Physics-based surface sensor correction applied:")
                print(f"   Firmware selected: {firmware_surface_sensor} (max {firmware_surface_max_temp:.1f}°C)")
                print(f"   Corrected to: {surface_sensor} (max {result['max_temp']:.1f}°C)")
                print(f"   Confidence: {result['confidence']}%")
                print(f"   Reasoning: {result['reasoning']}")
                print(f"   Browning time: {result['browning_time']:.1f} minutes")
        else:
            # Mark that physics detection was attempted but not applied
            df['PhysicsBasedSurfaceDetection'] = False
            curve_assignments = self.curve_sensor_assignments.get(curve_index, {})
            curve_assignments['physics_corrected'] = False
            self.curve_sensor_assignments[curve_index] = curve_assignments
            
            # Update deprecated sensor_assignments
            self.sensor_assignments = curve_assignments
            
            if result:
                print(f"\n⚠️  Curve {curve_index + 1}: Physics-based detection confidence too low ({result.get('confidence', 0)}%)")
            else:
                print(f"\n⚠️  Curve {curve_index + 1}: Physics-based surface detection failed - using firmware selection")

        return df

    def _apply_physics_based_core_correction(
        self, df: pd.DataFrame, curve_index: int
    ) -> pd.DataFrame:
        """Override firmware VirtualCoreSensor pick when combined-rank physics disagrees.

        Gate: CORE_DETECTION_CONFIG['ENABLED'].
        Override triggers only when the physics winner beats firmware by
        CONFIDENCE_GAP_MIN combined-rank points — firmware stays otherwise.
        Manual overrides (_sensor_overrides) are respected downstream by
        _apply_standard_columns; this method only changes the curve
        assignment and sets core_physics_corrected=True.
        """
        from src.data.thermodynamic_sensor_classifier import (
            identify_core_sensor_combined_rank,
        )

        sensor_columns = [f"T{i}" for i in range(1, 9) if f"T{i}" in df.columns]
        if len(sensor_columns) < 2:
            return df

        candidate_core, diagnostics = identify_core_sensor_combined_rank(
            df, sensor_columns
        )

        curve_assignments = self.curve_sensor_assignments.get(curve_index, {})
        firmware_core = curve_assignments.get("core")

        # Initialise flag (false until override confirmed).
        curve_assignments["core_physics_corrected"] = False
        curve_assignments["core_detection_diagnostics"] = diagnostics
        self.curve_sensor_assignments[curve_index] = curve_assignments

        if candidate_core is None or not diagnostics:
            return df

        if firmware_core not in diagnostics:
            # Firmware pick not in the ranked set (e.g. 'Unknown'); cannot
            # measure a confidence gap — leave firmware alone.
            return df

        firmware_score = diagnostics[firmware_core]["combined_score"]
        candidate_score = diagnostics[candidate_core]["combined_score"]
        gap = firmware_score - candidate_score

        if gap < CORE_DETECTION_CONFIG["CONFIDENCE_GAP_MIN"]:
            return df

        curve_assignments["core"] = candidate_core
        curve_assignments["core_physics_corrected"] = True
        curve_assignments["firmware_core_sensor"] = firmware_core
        curve_assignments["firmware_core_combined_score"] = firmware_score
        curve_assignments["candidate_core_combined_score"] = candidate_score
        self.curve_sensor_assignments[curve_index] = curve_assignments
        self.sensor_assignments = curve_assignments

        print(
            f"\n✅ Curve {curve_index + 1}: Physics-based core sensor correction applied:"
        )
        print(f"   Firmware selected: {firmware_core} (combined score {firmware_score})")
        print(f"   Corrected to: {candidate_core} (combined score {candidate_score})")
        print(f"   Confidence gap: {gap}")
        return df

    def get_sensor_assignments(self) -> dict:
        """
        Get the sensor role assignments for the current curve.
        
        Returns:
            dict: Dictionary with 'core', 'surface', 'ambient' keys containing sensor identifiers
        """
        # Return assignments for current curve
        if hasattr(self, 'curve_sensor_assignments') and self.current_curve_index in self.curve_sensor_assignments:
            return self.curve_sensor_assignments[self.current_curve_index]
        # Fallback to deprecated sensor_assignments
        return getattr(self, 'sensor_assignments', {})
    
    def set_expected_durations(
        self, durations_s: list[float | None] | None
    ) -> None:
        """Set the per-curve expected-duration hint and re-run detection.

        Introduced by flotilla mission M5 HMS Dauntless.  Mirrors the
        cache-invalidation semantics of :meth:`set_sensor_override`: when
        cached data is present, running this method triggers a fresh
        ``_extract_all_baking_curves`` pass so analytics downstream see
        the refined curves.

        Args:
            durations_s: ``None`` clears the hint.  A list of seconds (or
                ``None`` entries for per-curve skips, e.g. truncated
                bakes) is matched positionally to detected curves.
        """
        self.expected_durations_s = durations_s
        # Re-run detection on the full raw log, NOT on self.data which
        # has been overwritten with the first curve's slice (M1 HMS
        # Ardent fixed this latent bug — pre-fix, multi-bake CSVs lost
        # bakes 2+ on every set_expected_durations call).
        source = self.raw_data if self.raw_data is not None else self.data
        if source is not None and len(source) > 0:
            self.all_curves = self._extract_all_baking_curves(source.copy())
            if self.all_curves:
                # Preserve current_curve_index when valid; otherwise reset.
                if self.current_curve_index >= len(self.all_curves):
                    self.current_curve_index = 0

    def set_curve_boundaries(
        self, curve_index: int, start_idx: int, end_idx: int
    ) -> None:
        """Pin curve ``curve_index`` to ``[start_idx, end_idx]`` in the
        raw-log index space, regardless of detector decision or hint.

        Introduced by flotilla mission M1 HMS Ardent (branch
        ``refactor/curve-boundary-review``).  Used by the Curve Boundary
        Review tab (M3) so the operator can pin a boundary when the
        detector + hint can't reach the desired window.

        Validation:
        - ``curve_index`` must be a current detected-curve index.
        - ``start_idx`` and ``end_idx`` must lie inside ``raw_data``.
        - ``start_idx < end_idx``.

        Re-applies overrides via a fresh re-detection so all derived
        fields (``samples``, ``duration``, ``max_temp``, etc.) reflect
        the pinned slice.  ``exit_candidate_kind`` becomes
        ``"manual_override"`` for the pinned curve.
        """
        if not self.all_curves or curve_index < 0 or curve_index >= len(self.all_curves):
            raise IndexError(
                f"curve_index {curve_index} outside detected range "
                f"[0, {len(self.all_curves) - 1}]"
            )
        n = len(self.raw_data) if self.raw_data is not None else 0
        if not (0 <= start_idx < n) or not (0 <= end_idx < n):
            raise ValueError(
                f"start_idx={start_idx} and end_idx={end_idx} must lie in "
                f"[0, {n - 1}]"
            )
        if start_idx >= end_idx:
            raise ValueError(
                f"start_idx={start_idx} must be less than end_idx={end_idx}"
            )

        # M11 HMS Endeavour: dispatch by curve type.
        target = self.all_curves[curve_index]
        added_idx = target.get("_user_added_idx")
        if added_idx is not None and 0 <= added_idx < len(self._added_curves):
            # User-added curve — update its entry in ``_added_curves``
            # so the same curve (identified by its position in that
            # list) gets re-refined with the new range on next extract.
            self._added_curves[added_idx] = (int(start_idx), int(end_idx))
        else:
            # Detector curve — translate the all_curves position back
            # to the detector position (the position before any
            # user-added curves were appended) so the override key
            # stays stable as user-added curves come and go.
            detector_pos = sum(
                1
                for c in self.all_curves[: curve_index + 1]
                if c.get("_user_added_idx") is None
            ) - 1
            self._boundary_overrides[detector_pos] = (
                int(start_idx),
                int(end_idx),
            )
        self._reapply_boundary_state()

    def clear_curve_boundaries(self, curve_index: int) -> None:
        """Remove the manual override for ``curve_index`` (no-op if absent)."""
        if curve_index in self._boundary_overrides:
            del self._boundary_overrides[curve_index]
            self._reapply_boundary_state()

    def _reapply_boundary_state(self) -> None:
        """Re-run detection on raw_data and apply manual overrides on top."""
        if self.raw_data is None or len(self.raw_data) == 0:
            return
        self.all_curves = self._extract_all_baking_curves(self.raw_data.copy())
        if self.all_curves and self.current_curve_index >= len(self.all_curves):
            self.current_curve_index = 0

    def set_sensor_override(self, curve_index: int, role: str, sensor: str):
        """
        Allow user to override sensor assignments for a specific curve.
        
        Args:
            curve_index: Index of the curve
            role: 'core', 'surface', or 'ambient'
            sensor: Single sensor name (e.g., 'T2')
        """
        if curve_index not in self._sensor_overrides:
            self._sensor_overrides[curve_index] = {}
        self._sensor_overrides[curve_index][role] = sensor
        
        # Regenerate standard columns for this curve if it's the current one
        if curve_index == self.current_curve_index:
            self._regenerate_standard_columns()
    
    def clear_sensor_overrides(self, curve_index: int):
        """Clear all user overrides for a curve, reverting to automatic detection."""
        if curve_index in self._sensor_overrides:
            del self._sensor_overrides[curve_index]
            
        # Regenerate columns if this is the current curve
        if curve_index == self.current_curve_index:
            self._regenerate_standard_columns()
    
    def get_core_sensors(self, curve_index: Optional[int] = None) -> List[str]:
        """Get list of physical sensors identified as core (with override support)."""
        if curve_index is None:
            curve_index = self.current_curve_index
            
        # Check for user override first
        if curve_index in self._sensor_overrides and 'core' in self._sensor_overrides[curve_index]:
            return self._sensor_overrides[curve_index]['core']
            
        # Otherwise return automatic detection
        return self._get_automatic_core_sensors(curve_index)
    
    def get_surface_sensors(self, curve_index: Optional[int] = None) -> List[str]:
        """Get list of physical sensors identified as surface (with override support)."""
        if curve_index is None:
            curve_index = self.current_curve_index
            
        # Check for user override first
        if curve_index in self._sensor_overrides and 'surface' in self._sensor_overrides[curve_index]:
            return self._sensor_overrides[curve_index]['surface']
            
        # Otherwise return automatic detection
        return self._get_automatic_surface_sensors(curve_index)
    
    def get_ambient_sensors(self, curve_index: Optional[int] = None) -> List[str]:
        """Get list of physical sensors identified as ambient (with override support)."""
        if curve_index is None:
            curve_index = self.current_curve_index
            
        # If we have overrides, infer ambient sensors based on surface position
        if curve_index in self._sensor_overrides and 'surface' in self._sensor_overrides[curve_index]:
            surface_sensor = self._sensor_overrides[curve_index]['surface']
            if surface_sensor and len(surface_sensor) >= 2:
                surface_num = int(surface_sensor[1])
                # Return all sensors with numbers greater than surface
                ambient_sensors = []
                for i in range(surface_num + 1, 9):  # T1-T8, so max is 8
                    sensor = f'T{i}'
                    if sensor in self.data.columns:
                        ambient_sensors.append(sensor)
                return ambient_sensors
            
        # Otherwise return automatic detection
        return self._get_automatic_ambient_sensors(curve_index)
    
    def get_core_sensor(self, curve_index: Optional[int] = None) -> Optional[str]:
        """Get the single core sensor (with override support)."""
        if curve_index is None:
            curve_index = self.current_curve_index
            
        # Check for user override first
        if curve_index in self._sensor_overrides and 'core' in self._sensor_overrides[curve_index]:
            return self._sensor_overrides[curve_index]['core']
            
        # Otherwise return primary sensor from automatic detection
        auto_sensors = self._get_automatic_core_sensors(curve_index)
        return auto_sensors[0] if auto_sensors else None
    
    def get_surface_sensor(self, curve_index: Optional[int] = None) -> Optional[str]:
        """Get the single surface sensor (with override support)."""
        if curve_index is None:
            curve_index = self.current_curve_index
            
        # Check for user override first
        if curve_index in self._sensor_overrides and 'surface' in self._sensor_overrides[curve_index]:
            return self._sensor_overrides[curve_index]['surface']
            
        # Otherwise return primary sensor from automatic detection
        auto_sensors = self._get_automatic_surface_sensors(curve_index)
        return auto_sensors[0] if auto_sensors else None
    
    def get_internal_sensors(self, curve_index: Optional[int] = None, data: Optional[pd.DataFrame] = None) -> List[str]:
        """
        Get all sensors below the surface sensor that represent internal crumb temperature.
        
        Sensors are filtered based on maximum temperature to exclude those that are
        likely in the crust (>100°C + margin).
        
        Args:
            curve_index: Which curve to analyze (default: current curve)
            data: Optional data frame to use for temperature analysis. If not provided,
                  uses the current curve data from self.data
                  
        Returns:
            List of sensor names that represent internal crumb
        """
        surface_sensor = self.get_surface_sensor(curve_index)
        if not surface_sensor or len(surface_sensor) < 2:
            return []
            
        surface_num = int(surface_sensor[1])
        
        # Step 1: Get all sensors below surface (current logic)
        candidate_sensors = []
        for i in range(1, surface_num):
            sensor = f'T{i}'
            if sensor in self.data.columns:
                candidate_sensors.append(sensor)
        
        # If no data provided for filtering, return all candidates (backward compatibility)
        if data is None:
            # Try to get data for the current curve
            if hasattr(self, 'all_curves') and 0 <= (curve_index or self.current_curve_index) < len(self.all_curves):
                data = self.all_curves[curve_index or self.current_curve_index]['data']
            else:
                # No data available for temperature filtering, return all candidates
                return candidate_sensors
        
        # Step 2: Filter by temperature criteria
        internal_sensors = []
        temp_threshold = INTERNAL_SENSOR_CONFIG['TEMP_THRESHOLD']
        use_time_filter = INTERNAL_SENSOR_CONFIG['USE_TIME_BASED_FILTERING']
        time_threshold = INTERNAL_SENSOR_CONFIG['TIME_THRESHOLD']
        
        for sensor in candidate_sensors:
            if sensor not in data.columns:
                continue
                
            sensor_data = data[sensor]
            max_temp = sensor_data.max()
            
            # Check maximum temperature criterion
            if max_temp <= temp_threshold:
                internal_sensors.append(sensor)
            elif use_time_filter:
                # Additional time-based criterion
                time_above_100 = (sensor_data > 100).sum() / len(sensor_data)
                if time_above_100 <= time_threshold:
                    internal_sensors.append(sensor)
        
        # Step 3: Ensure core sensor is always included
        if INTERNAL_SENSOR_CONFIG['ALWAYS_INCLUDE_CORE']:
            core_sensor = self.get_core_sensor(curve_index)
            if core_sensor and core_sensor not in internal_sensors and core_sensor in candidate_sensors:
                internal_sensors.append(core_sensor)
                # Sort to maintain order
                internal_sensors.sort(key=lambda s: int(s[1]))
        
        return internal_sensors
    
    def get_core_column(self, curve_index: Optional[int] = None) -> str:
        """Get the column name to use for core temperature analysis."""
        # Always use standardized column name
        return 'CoreTemperature'
    
    def get_surface_column(self, curve_index: Optional[int] = None) -> str:
        """Get the column name to use for surface temperature analysis."""
        # Always use standardized column name
        return 'SurfaceTemperature'
    
    def get_ambient_column(self, curve_index: Optional[int] = None) -> Optional[str]:
        """Get the column name to use for ambient temperature analysis."""
        # Check if we have ambient sensors
        ambient_sensors = self.get_ambient_sensors(curve_index)
        if ambient_sensors:
            return 'AmbientTemperature'
        return None
    
    def get_sensor_assignments_with_overrides(self, curve_index: Optional[int] = None) -> Dict:
        """Get sensor assignments including override status."""
        if curve_index is None:
            curve_index = self.current_curve_index
            
        assignments = self.get_sensor_assignments().copy()
        
        # Add current sensor assignments
        assignments['core_sensor'] = self.get_core_sensor(curve_index)
        assignments['surface_sensor'] = self.get_surface_sensor(curve_index)
        assignments['internal_sensors'] = self.get_internal_sensors(curve_index)
        assignments['ambient_sensors'] = self.get_ambient_sensors(curve_index)
        
        # For backward compatibility with UI
        assignments['core_sensors'] = [assignments['core_sensor']] if assignments['core_sensor'] else []
        assignments['surface_sensors'] = [assignments['surface_sensor']] if assignments['surface_sensor'] else []
        
        # Check for overrides
        if curve_index in self._sensor_overrides:
            assignments['has_overrides'] = True
            assignments['overrides'] = self._sensor_overrides[curve_index]
        else:
            assignments['has_overrides'] = False
            
        return assignments
    
    def _classify_sensors_dynamically(self, df: pd.DataFrame, curve_index: int) -> pd.DataFrame:
        """
        Dynamically classify sensors using thermodynamic principles.
        
        This is a fallback method when virtual sensor data is not available.
        """
        sensor_cols = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
        available_sensors = [col for col in sensor_cols if col in df.columns]
        
        if len(available_sensors) < 3:
            print("Warning: Not enough sensors for dynamic classification")
            # Fall back to old hardcoded method
            try:
                df['CoreTemperature'] = resolve_core_temperature_series(df)
            except KeyError:
                pass
            if all(col in df.columns for col in ['T7', 'T8']):
                df['SurfaceTemperature'] = df[['T7', 'T8']].mean(axis=1)
            df['AmbientTemperature'] = df[available_sensors].max(axis=1) if available_sensors else 0
            return df
        
        # Try thermodynamic classification first
        try:
            from ..data.thermodynamic_sensor_classifier import ThermodynamicSensorClassifier
            classifier = ThermodynamicSensorClassifier(df, available_sensors)
            assignments = classifier.classify_sensors()
            
            # Use thermodynamic assignments
            core_sensors = assignments.get('core', [])
            surface_sensors = assignments.get('surface', [])
            ambient_sensors = assignments.get('ambient', [])
            
            # Calculate temperatures based on classification
            df['CoreTemperature'] = df[core_sensors].mean(axis=1) if core_sensors else df[available_sensors[:2]].mean(axis=1)
            df['SurfaceTemperature'] = df[surface_sensors].mean(axis=1) if surface_sensors else df[available_sensors[2:4]].mean(axis=1)
            df['AmbientTemperature'] = df[ambient_sensors].mean(axis=1) if ambient_sensors else df[available_sensors[-2:]].mean(axis=1)
            
            # Store assignments per curve
            curve_assignments = {
                'core': core_sensors[0] if core_sensors else 'Unknown',
                'surface': surface_sensors[0] if surface_sensors else 'Unknown', 
                'ambient': ambient_sensors[0] if ambient_sensors else 'Unknown',
                'method': 'thermodynamic_classification'
            }
            self.curve_sensor_assignments[curve_index] = curve_assignments
            
            # Update deprecated sensor_assignments
            self.sensor_assignments = curve_assignments
            
            print(f"Thermodynamic sensor classification:")
            for role, sensors in assignments.items():
                print(f"  {role.upper()}: {', '.join(sensors)}")
            
            return df
            
        except Exception as e:
            print(f"Thermodynamic classification failed: {e}")
            print("Falling back to simple temperature-based classification")
        
        # Calculate statistics for each sensor
        sensor_stats = {}
        for sensor in available_sensors:
            sensor_stats[sensor] = {
                'mean': df[sensor].mean(),
                'max': df[sensor].max(),
                'range': df[sensor].max() - df[sensor].min(),
                'std': df[sensor].std()
            }
        
        # Sort sensors by maximum temperature (core < surface < ambient)
        sorted_sensors = sorted(sensor_stats.items(), key=lambda x: x[1]['max'])
        
        # Assign roles based on temperature characteristics
        # Lowest max temp sensors are likely core
        core_sensors = [s[0] for s in sorted_sensors[:2]]  # 2 coolest sensors
        # Highest max temp sensors are likely ambient
        ambient_sensors = [s[0] for s in sorted_sensors[-2:]]  # 2 hottest sensors
        # Middle sensors are likely surface
        surface_sensors = [s[0] for s in sorted_sensors[2:-2]]  # Middle sensors
        
        # If we don't have enough surface sensors, use some from the edges
        if len(surface_sensors) < 2:
            surface_sensors = [s[0] for s in sorted_sensors[2:4]]
        
        print(f"Dynamic sensor classification based on temperature patterns:")
        print(f"  Core sensors: {core_sensors} (coolest)")
        print(f"  Surface sensors: {surface_sensors} (intermediate)")
        print(f"  Ambient sensors: {ambient_sensors} (hottest)")
        
        # Calculate temperatures based on classification
        df['CoreTemperature'] = df[core_sensors].mean(axis=1)
        df['SurfaceTemperature'] = df[surface_sensors].mean(axis=1) if surface_sensors else df[core_sensors].mean(axis=1) * 1.1
        df['AmbientTemperature'] = df[ambient_sensors].mean(axis=1)
        
        # Store assignments per curve
        curve_assignments = {
            'core': ', '.join(core_sensors),
            'surface': ', '.join(surface_sensors),
            'ambient': ', '.join(ambient_sensors),
            'method': 'dynamic_classification'
        }
        self.curve_sensor_assignments[curve_index] = curve_assignments
        
        # Update deprecated sensor_assignments
        self.sensor_assignments = curve_assignments
        
        return df
    
    def _extract_all_baking_curves(self, df: pd.DataFrame) -> list:
        """Extract baking curves via :class:`CurveBoundaryDetector`.

        Thin adapter: boundary detection is delegated to the pure detector; this
        method layers per-curve sensor-role identification on top of each curve
        returned (the detector is domain-agnostic and does not know about role
        assignment).  The input DataFrame is not mutated.

        When ``self.expected_durations_s`` is set (M5 HMS Dauntless), the
        hint list is forwarded to the detector's ``expected_durations_s``
        kwarg.  A list whose length mismatches the detected curve count
        is accepted — the detector consumes hints positionally and
        ignores entries beyond ``len(detected_curves)`` — but a warning
        is logged so operators can diagnose a mis-entered hint.
        """
        detector = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
        curves = detector.extract_curves(
            df, expected_durations_s=self.expected_durations_s
        )

        if (
            self.expected_durations_s is not None
            and len(self.expected_durations_s) != len(curves)
        ):
            _log.warning(
                "expected_durations_s length mismatch: %d hint(s) supplied "
                "but %d curve(s) detected; extra hints are ignored, missing "
                "hints fall through to no-hint refinement.",
                len(self.expected_durations_s),
                len(curves),
            )

        # Apply per-curve manual boundary overrides (M1 HMS Ardent).
        # ``_boundary_overrides`` is keyed by DETECTOR position (the
        # index in ``curves`` returned by the detector, before any
        # user-added curves are appended).  This stays stable across
        # M11 HMS Endeavour user-claim insertions which only append.
        if self._boundary_overrides:
            curves = self._apply_boundary_overrides(df, curves)

        # Append user-claimed curves (M11 HMS Endeavour).  Each
        # ``_added_curves`` entry is a ``(start, end)`` operator-drawn
        # range; we auto-refine via the detector on the sub-slice and
        # tag the result with ``_user_added_idx`` so downstream code
        # can distinguish user-added from detector output.
        for added_idx, (added_start, added_end) in enumerate(self._added_curves):
            refined_start, refined_end = self._refine_user_added_region(
                df, added_start, added_end
            )
            curves.append(
                self._build_user_added_curve_dict(
                    df, refined_start, refined_end, added_idx
                )
            )

        # Sort by start_idx so chronological order is preserved across
        # detector + user-added curves; renumber curve_number to match.
        curves.sort(key=lambda c: c["start_idx"])
        for i, c in enumerate(curves):
            c["curve_number"] = i + 1

        # Note: sensor-role identification runs AFTER boundary overrides
        # AND user-added insertion so role detection uses the final
        # post-sort slice.
        for curve_index, curve in enumerate(curves):
            curve["data"] = self._identify_sensor_roles_for_curve(
                curve["data"], curve_index
            )
            _log.debug(
                "Curve %d: duration=%.1f min  samples=%d  max_temp=%.1f°C  "
                "ts_range=%.1fs-%.1fs",
                curve_index + 1,
                curve["duration"],
                curve["samples"],
                curve["max_temp"],
                curve["start_time"],
                curve["end_time"],
            )

        if not curves:
            _log.warning("No valid baking curves found in data")
        else:
            _log.debug("Total curves found: %d", len(curves))
        return curves

    def _apply_boundary_overrides(
        self, df: pd.DataFrame, curves: list
    ) -> list:
        """Replace each overridden curve's slice + derived fields with
        the manually-pinned ``(start_idx, end_idx)`` from
        ``self._boundary_overrides``.  Curves without an override are
        returned unchanged.  Introduced by M1 HMS Ardent.
        """
        timestamps_full = df["Timestamp"].to_numpy(dtype=float)
        for curve_index, (start_idx, end_idx) in self._boundary_overrides.items():
            if curve_index < 0 or curve_index >= len(curves):
                # Stale override (curve count changed since override was set).
                continue
            curve_data = df.iloc[start_idx : end_idx + 1].copy()
            curve_data["Timestamp"] = (
                curve_data["Timestamp"] - curve_data["Timestamp"].iloc[0]
            )
            curve_data["TimeMinutes"] = curve_data["Timestamp"] / 60.0
            curve_data = curve_data.reset_index(drop=True)
            # Rebuild every derived field from the pinned slice so
            # downstream analytics see a consistent view.
            core_col = "CoreTemperature" if "CoreTemperature" in curve_data.columns else "VirtualCoreTemperature"
            peak_temp = float(curve_data[core_col].max()) if core_col in curve_data.columns else 0.0
            curves[curve_index] = {
                "data": curve_data,
                "start_idx": int(start_idx),
                "end_idx": int(end_idx),
                "start_time": float(timestamps_full[start_idx]),
                "end_time": float(timestamps_full[end_idx]),
                "duration": float(curve_data["TimeMinutes"].max()),
                "max_temp": peak_temp,
                "curve_number": curve_index + 1,
                "samples": len(curve_data),
                "truncated": False,
                "exit_candidate_kind": "manual_override",
            }
        return curves

    def _build_user_added_curve_dict(
        self, df: pd.DataFrame, start_idx: int, end_idx: int, added_idx: int
    ) -> dict:
        """Build a curve descriptor dict for a user-claimed region
        (M11 HMS Endeavour).  Mirrors :meth:`_apply_boundary_overrides`'s
        dict shape but tags the curve with ``_user_added_idx`` and
        ``exit_candidate_kind="user_added"`` so the UI can render it
        distinctly and ``set_curve_boundaries`` can dispatch updates
        back into ``self._added_curves``.
        """
        timestamps_full = df["Timestamp"].to_numpy(dtype=float)
        curve_data = df.iloc[start_idx : end_idx + 1].copy()
        curve_data["Timestamp"] = (
            curve_data["Timestamp"] - curve_data["Timestamp"].iloc[0]
        )
        curve_data["TimeMinutes"] = curve_data["Timestamp"] / 60.0
        curve_data = curve_data.reset_index(drop=True)
        core_col = (
            "CoreTemperature"
            if "CoreTemperature" in curve_data.columns
            else "VirtualCoreTemperature"
        )
        peak_temp = (
            float(curve_data[core_col].max())
            if core_col in curve_data.columns
            else 0.0
        )
        return {
            "data": curve_data,
            "start_idx": int(start_idx),
            "end_idx": int(end_idx),
            "start_time": float(timestamps_full[start_idx]),
            "end_time": float(timestamps_full[end_idx]),
            "duration": float(curve_data["TimeMinutes"].max()),
            "max_temp": peak_temp,
            "curve_number": -1,  # filled in by the sort + renumber loop
            "samples": len(curve_data),
            "truncated": False,
            "exit_candidate_kind": "user_added",
            "_user_added_idx": int(added_idx),
        }

    def _refine_user_added_region(
        self, df: pd.DataFrame, start_idx: int, end_idx: int
    ) -> tuple[int, int]:
        """Auto-refine a user-claimed (start, end) region by running
        the detector on the sub-slice.  Falls back to a BAKE_ACTIVE_C
        trim if the detector finds no curve, and finally to the
        operator's range as-is.

        Translates the detector's sub-slice positional indices back
        into raw_data positional indices by adding ``start_idx``.
        Introduced by M11 HMS Endeavour.
        """
        n_raw = len(df)
        if start_idx < 0 or end_idx >= n_raw or start_idx >= end_idx:
            return (start_idx, end_idx)

        sub = df.iloc[start_idx : end_idx + 1].reset_index(drop=True)

        # First try: run the detector on the sub-slice.  If it finds a
        # curve (passes MIN_PEAK_TEMP + MIN_CURVE_DURATION_SECONDS
        # gates), use those refined boundaries.
        try:
            detector = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
            sub_curves = detector.extract_curves(sub)
        except Exception:  # pragma: no cover  (defensive)
            sub_curves = []
        if sub_curves:
            sub_start = int(sub_curves[0]["start_idx"]) + start_idx
            sub_end = int(sub_curves[0]["end_idx"]) + start_idx
            if sub_start < sub_end:
                return (sub_start, sub_end)

        # Fallback: trim leading and trailing samples below
        # BAKE_ACTIVE_C so a coarse user drag still snaps to roughly
        # the bake's active region.
        bake_active = float(
            CURVE_DETECTION_CONFIG.get("BAKE_ACTIVE_THRESHOLD_C", 40.0)
        )
        core_col = (
            "CoreTemperature"
            if "CoreTemperature" in sub.columns
            else "VirtualCoreTemperature"
        )
        if core_col in sub.columns:
            temps = sub[core_col].to_numpy(dtype=float)
            s_local = 0
            while s_local < len(temps) and temps[s_local] < bake_active:
                s_local += 1
            e_local = len(temps) - 1
            while e_local > s_local and temps[e_local] < bake_active:
                e_local -= 1
            if s_local < e_local:
                return (start_idx + s_local, start_idx + e_local)

        # Final fallback: accept the operator's range verbatim.
        return (start_idx, end_idx)

    def add_manual_curve(self, start_idx: int, end_idx: int) -> int:
        """Claim a region the detector missed as a curve, refining the
        boundaries against the detector / BAKE_ACTIVE_C threshold.

        Returns the new curve's position in ``self.all_curves`` after
        the sort.  Introduced by M11 HMS Endeavour.

        Raises:
          ValueError — if the range is inverted or out of bounds.
        """
        if self.raw_data is None or len(self.raw_data) == 0:
            raise RuntimeError(
                "raw_data is empty; load a CSV before claiming a curve."
            )
        n = len(self.raw_data)
        if not (0 <= start_idx < n) or not (0 <= end_idx < n):
            raise ValueError(
                f"start_idx={start_idx} and end_idx={end_idx} must lie in "
                f"[0, {n - 1}]."
            )
        if start_idx >= end_idx:
            raise ValueError(
                f"start_idx={start_idx} must be less than end_idx={end_idx}."
            )

        added_idx = len(self._added_curves)
        self._added_curves.append((int(start_idx), int(end_idx)))
        self._reapply_boundary_state()

        # Find the user-added curve in the post-sort all_curves list
        # via its ``_user_added_idx`` tag.
        for i, c in enumerate(self.all_curves):
            if c.get("_user_added_idx") == added_idx:
                return i
        return -1

    def remove_manual_curve(self, curve_index: int) -> None:
        """Remove a user-added curve.  No-op if ``curve_index`` points
        at a detector curve.  Introduced by M11 HMS Endeavour.
        """
        if not (0 <= curve_index < len(self.all_curves)):
            return
        target = self.all_curves[curve_index]
        added_idx = target.get("_user_added_idx")
        if added_idx is None:
            return
        # Drop the entry; subsequent _user_added_idx values shift
        # down on the next re-extract because the list index changes.
        if 0 <= added_idx < len(self._added_curves):
            del self._added_curves[added_idx]
            self._reapply_boundary_state()

    def get_sensor_data(self) -> pd.DataFrame:
        """Get only the temperature sensor columns."""
        sensor_cols = ['Timestamp', 'TimeMinutes', 'T1', 'T2', 'T3', 'T4', 
                      'T5', 'T6', 'T7', 'T8']
        return self.data[sensor_cols]
    
    def get_analysis_data(self) -> pd.DataFrame:
        """Get data formatted for analysis."""
        return self.data
    
    def get_all_curves(self) -> list:
        """Get all detected baking curves."""
        return self.all_curves
    
    def get_curve_count(self) -> int:
        """Get the number of detected curves."""
        return len(self.all_curves)
    
    def set_current_curve(self, curve_index: int) -> pd.DataFrame:
        """Set the current curve for analysis."""
        if 0 <= curve_index < len(self.all_curves):
            self.current_curve_index = curve_index
            self.data = self.all_curves[curve_index]['data']
            
            # Load curve-specific sensor assignments into deprecated sensor_assignments
            # for backward compatibility
            if curve_index in self.curve_sensor_assignments:
                self.sensor_assignments = self.curve_sensor_assignments[curve_index]
        return self.data
    
    def get_current_curve_info(self) -> dict:
        """Get metadata about the current curve."""
        if self.all_curves and 0 <= self.current_curve_index < len(self.all_curves):
            return self.all_curves[self.current_curve_index]
        return None
    
    def _validate_sensor_assignments(self, df: pd.DataFrame) -> None:
        return self._sensor_manager.validate_sensor_assignments(df)

    def _get_automatic_core_sensors(self, curve_index: int) -> List[str]:
        return self._sensor_manager.get_automatic_core_sensors(curve_index)

    def _get_automatic_surface_sensors(self, curve_index: int) -> List[str]:
        return self._sensor_manager.get_automatic_surface_sensors(curve_index)

    def _get_automatic_ambient_sensors(self, curve_index: int) -> List[str]:
        return self._sensor_manager.get_automatic_ambient_sensors(curve_index)
    
    def _apply_standard_columns(self, df: pd.DataFrame, curve_index: int) -> None:
        """Single canonical writer of CoreTemperature / SurfaceTemperature / AmbientTemperature.

        Layering (matches CLAUDE.md):
          1. Virtual* firmware channels (or *Average / raw-T fallbacks).
          2. Physics-based surface correction — preserved when
             curve_sensor_assignments[curve_index]['physics_corrected'] is True.
          3. Manual overrides from self._sensor_overrides[curve_index] — win
             over physics correction (the UI rule: user > physics > firmware).
        """
        if df is None:
            return

        curve_assignments = self.curve_sensor_assignments.get(curve_index, {})
        overrides = self._sensor_overrides.get(curve_index, {})

        # --- CoreTemperature ---
        # Layering: manual override > physics correction > firmware virtual.
        # Mirrors the SurfaceTemperature path: core_physics_corrected=True
        # means the sensor in curve_assignments['core'] is the physics winner,
        # NOT the firmware VirtualCoreSensor mode, so honour it here or a
        # later regeneration will silently revert to VirtualCoreTemperature.
        core_override = overrides.get('core')
        physics_core = (
            curve_assignments.get('core')
            if curve_assignments.get('core_physics_corrected')
            else None
        )
        if core_override and core_override in df.columns:
            df['CoreTemperature'] = df[core_override]
        elif physics_core and physics_core in df.columns:
            df['CoreTemperature'] = df[physics_core]
        else:
            try:
                df['CoreTemperature'] = resolve_core_temperature_series(df)
            except KeyError:
                pass

        # --- SurfaceTemperature ---
        # Override wins; else physics-corrected sensor wins; else firmware virtual.
        surface_override = overrides.get('surface')
        physics_surface = (
            curve_assignments.get('surface')
            if curve_assignments.get('physics_corrected')
            else None
        )
        if surface_override and surface_override in df.columns:
            df['SurfaceTemperature'] = df[surface_override]
        elif physics_surface and physics_surface in df.columns:
            df['SurfaceTemperature'] = df[physics_surface]
        elif 'VirtualSurfaceTemperature' in df.columns:
            df['SurfaceTemperature'] = df['VirtualSurfaceTemperature']
        elif 'SurfaceAverage' in df.columns:
            df['SurfaceTemperature'] = df['SurfaceAverage']
        elif all(col in df.columns for col in ['T7', 'T8']):
            df['SurfaceTemperature'] = df[['T7', 'T8']].mean(axis=1)

        # --- AmbientTemperature ---
        # A surface override implies the probe geometry changed, so recompute
        # ambient from the inferred ambient sensors rather than the firmware pick.
        if surface_override:
            ambient_sensors = self.get_ambient_sensors(curve_index)
            available_ambient = [s for s in ambient_sensors if s in df.columns]
            if available_ambient:
                df['AmbientTemperature'] = df[available_ambient].max(axis=1)
            elif 'VirtualAmbientTemperature' in df.columns:
                df['AmbientTemperature'] = df['VirtualAmbientTemperature']
            elif 'T8' in df.columns:
                df['AmbientTemperature'] = df['T8']
        elif 'VirtualAmbientTemperature' in df.columns:
            df['AmbientTemperature'] = df['VirtualAmbientTemperature']
        elif 'T8' in df.columns:
            df['AmbientTemperature'] = df['T8']

    def _regenerate_standard_columns(self):
        """Regenerate standardized temperature columns based on current sensor assignments."""
        if self.data is None:
            return
        self._apply_standard_columns(self.data, self.current_curve_index)

    def _generate_standard_columns_for_df(self, df: pd.DataFrame):
        """Generate standardized temperature columns for a dataframe during initial load."""
        # Resolve curve_index by identity against all_curves so a freshly
        # extracted curve's physics flag is honoured.
        curve_index = self.current_curve_index
        for idx, info in enumerate(getattr(self, 'all_curves', []) or []):
            if info.get('data') is df:
                curve_index = idx
                break
        self._apply_standard_columns(df, curve_index)
    

def validate_thermal_data(df: pd.DataFrame) -> Tuple[bool, list]:
    """
    Validate thermal profile data.
    
    Returns:
        Tuple of (is_valid, list of issues)
    """
    issues = []
    
    # Check required columns
    required_cols = ['Timestamp', 'T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        issues.append(f"Missing required columns: {missing_cols}")
    
    # Check for NaN values only in existing columns
    existing_cols = [col for col in required_cols if col in df.columns]
    if existing_cols:
        nan_counts = df[existing_cols].isna().sum()
        if nan_counts.any():
            issues.append(f"Found NaN values: {nan_counts[nan_counts > 0].to_dict()}")
    
    # Check temperature ranges
    temp_cols = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8']
    for col in temp_cols:
        if col in df.columns:
            min_temp = df[col].min()
            max_temp = df[col].max()
            if min_temp < -50 or max_temp > 300:
                issues.append(f"{col} has unrealistic temperatures: {min_temp:.1f}°C to {max_temp:.1f}°C")
    
    # Check time monotonicity
    if not df['Timestamp'].is_monotonic_increasing:
        issues.append("Timestamp is not monotonically increasing")
    
    return len(issues) == 0, issues