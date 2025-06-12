"""
Centralized transformation manager for temperature columns.

This module ensures that data transformations are applied consistently
and in the correct order, preventing accidental overwrites.
"""

import pandas as pd
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum


class TransformationType(Enum):
    """Types of transformations that can be applied."""
    VIRTUAL_COLUMNS = "virtual_columns"
    PHYSICS_CORRECTION = "physics_correction"
    MANUAL_OVERRIDE = "manual_override"
    BACKWARD_COMPATIBILITY = "backward_compatibility"


@dataclass
class TransformationState:
    """Tracks the state of transformations for a curve."""
    applied_transformations: Set[TransformationType] = field(default_factory=set)
    sensor_assignments: Dict[str, str] = field(default_factory=dict)
    physics_corrected_sensor: Optional[str] = None
    manual_overrides: Dict[str, str] = field(default_factory=dict)
    
    def has_transformation(self, transformation: TransformationType) -> bool:
        """Check if a transformation has been applied."""
        return transformation in self.applied_transformations
    
    def add_transformation(self, transformation: TransformationType):
        """Mark a transformation as applied."""
        self.applied_transformations.add(transformation)
    
    def clear_transformation(self, transformation: TransformationType):
        """Remove a transformation from the applied set."""
        self.applied_transformations.discard(transformation)


class TransformationManager:
    """
    Manages all temperature column transformations.
    
    Ensures transformations are applied in the correct order and
    prevents accidental overwrites of previous transformations.
    """
    
    def __init__(self):
        # Track state per curve
        self._states: Dict[int, TransformationState] = {}
        
    def get_state(self, curve_index: int) -> TransformationState:
        """Get or create state for a curve."""
        if curve_index not in self._states:
            self._states[curve_index] = TransformationState()
        return self._states[curve_index]
    
    def apply_transformations(
        self,
        df: pd.DataFrame,
        curve_index: int,
        virtual_assignments: Dict[str, str],
        physics_correction: Optional[Tuple[str, str]] = None,
        manual_overrides: Optional[Dict[str, str]] = None
    ) -> pd.DataFrame:
        """
        Apply all transformations in the correct order.
        
        Args:
            df: DataFrame to transform
            curve_index: Which curve this is for
            virtual_assignments: Base sensor assignments from CSV
            physics_correction: Optional (from_sensor, to_sensor) for surface
            manual_overrides: Optional manual sensor overrides
            
        Returns:
            Transformed DataFrame with standardized columns
        """
        # Work on a copy to ensure immutability
        result_df = df.copy()
        state = self.get_state(curve_index)
        
        # Update base assignments if changed
        if not state.sensor_assignments or state.sensor_assignments != virtual_assignments:
            state.sensor_assignments = virtual_assignments.copy()
        
        # Always regenerate columns based on current state
        # This ensures columns are always present even if transformations were already applied
        
        # Step 1: Apply base virtual columns
        result_df = self._apply_virtual_columns(result_df, virtual_assignments)
        state.add_transformation(TransformationType.VIRTUAL_COLUMNS)
        
        # Step 2: Track physics correction if provided
        if physics_correction and not state.has_transformation(TransformationType.PHYSICS_CORRECTION):
            from_sensor, to_sensor = physics_correction
            state.physics_corrected_sensor = to_sensor
            state.add_transformation(TransformationType.PHYSICS_CORRECTION)
        
        # Step 3: Apply physics correction if it exists
        if state.has_transformation(TransformationType.PHYSICS_CORRECTION) and state.physics_corrected_sensor:
            result_df = self._apply_physics_correction(result_df, None, state.physics_corrected_sensor)
        
        # Step 4: Handle manual overrides
        if manual_overrides:
            result_df = self._apply_manual_overrides(result_df, manual_overrides, state)
            state.manual_overrides = manual_overrides.copy()
            state.add_transformation(TransformationType.MANUAL_OVERRIDE)
        elif state.has_transformation(TransformationType.MANUAL_OVERRIDE) and manual_overrides is None:
            # Explicitly clear manual overrides
            state.clear_transformation(TransformationType.MANUAL_OVERRIDE)
            state.manual_overrides.clear()
            # Re-apply base + physics only
            result_df = self._regenerate_columns(result_df, state)
        elif state.has_transformation(TransformationType.MANUAL_OVERRIDE):
            # Apply existing manual overrides
            result_df = self._apply_manual_overrides(result_df, state.manual_overrides, state)
        
        # Step 5: Ensure backward compatibility columns
        result_df = self._apply_backward_compatibility(result_df)
        state.add_transformation(TransformationType.BACKWARD_COMPATIBILITY)
        
        return result_df
    
    def _apply_virtual_columns(self, df: pd.DataFrame, assignments: Dict[str, str]) -> pd.DataFrame:
        """Apply base virtual column transformation."""
        # Create standardized columns from virtual columns
        if 'VirtualCoreTemperature' in df.columns:
            df['CoreTemperature'] = df['VirtualCoreTemperature']
        
        if 'VirtualSurfaceTemperature' in df.columns:
            df['SurfaceTemperature'] = df['VirtualSurfaceTemperature']
        
        if 'VirtualAmbientTemperature' in df.columns:
            df['AmbientTemperature'] = df['VirtualAmbientTemperature']
        
        return df
    
    def _apply_physics_correction(self, df: pd.DataFrame, from_sensor: str, to_sensor: str) -> pd.DataFrame:
        """Apply physics-based surface sensor correction."""
        if to_sensor in df.columns:
            df['SurfaceTemperature'] = df[to_sensor]
        return df
    
    def _apply_manual_overrides(
        self, 
        df: pd.DataFrame, 
        overrides: Dict[str, str],
        state: TransformationState
    ) -> pd.DataFrame:
        """Apply manual sensor overrides."""
        # Apply overrides for each role
        if 'core' in overrides and overrides['core'] in df.columns:
            df['CoreTemperature'] = df[overrides['core']]
        
        if 'surface' in overrides and overrides['surface'] in df.columns:
            df['SurfaceTemperature'] = df[overrides['surface']]
        elif state.has_transformation(TransformationType.PHYSICS_CORRECTION):
            # Preserve physics correction if no manual surface override
            if state.physics_corrected_sensor and state.physics_corrected_sensor in df.columns:
                df['SurfaceTemperature'] = df[state.physics_corrected_sensor]
        
        if 'ambient' in overrides and overrides['ambient'] in df.columns:
            df['AmbientTemperature'] = df[overrides['ambient']]
        
        return df
    
    def _regenerate_columns(self, df: pd.DataFrame, state: TransformationState) -> pd.DataFrame:
        """Regenerate columns based on current state."""
        # Start with virtual columns
        if 'VirtualCoreTemperature' in df.columns:
            df['CoreTemperature'] = df['VirtualCoreTemperature']
        
        # Apply physics correction if it was applied
        if state.has_transformation(TransformationType.PHYSICS_CORRECTION):
            if state.physics_corrected_sensor and state.physics_corrected_sensor in df.columns:
                df['SurfaceTemperature'] = df[state.physics_corrected_sensor]
        elif 'VirtualSurfaceTemperature' in df.columns:
            df['SurfaceTemperature'] = df['VirtualSurfaceTemperature']
        
        if 'VirtualAmbientTemperature' in df.columns:
            df['AmbientTemperature'] = df['VirtualAmbientTemperature']
        
        return df
    
    def _apply_backward_compatibility(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add backward compatibility columns."""
        # Create CoreAverage and SurfaceAverage for backward compatibility
        core_sensors = ['T1', 'T2', 'T3', 'T4']
        surface_sensors = ['T5', 'T6', 'T7', 'T8']
        
        available_core = [col for col in core_sensors if col in df.columns]
        available_surface = [col for col in surface_sensors if col in df.columns]
        
        if available_core:
            df['CoreAverage'] = df[available_core].mean(axis=1)
        
        if available_surface:
            df['SurfaceAverage'] = df[available_surface].mean(axis=1)
        
        return df
    
    def get_effective_sensor(self, curve_index: int, role: str) -> Optional[str]:
        """
        Get the effective sensor for a role considering all transformations.
        
        Args:
            curve_index: Which curve
            role: 'core', 'surface', or 'ambient'
            
        Returns:
            The sensor name that should be used for this role
        """
        state = self.get_state(curve_index)
        
        # Check manual overrides first
        if state.has_transformation(TransformationType.MANUAL_OVERRIDE):
            if role in state.manual_overrides:
                return state.manual_overrides[role]
        
        # Check physics correction for surface
        if role == 'surface' and state.has_transformation(TransformationType.PHYSICS_CORRECTION):
            return state.physics_corrected_sensor
        
        # Fall back to base assignments
        return state.sensor_assignments.get(role)
    
    def clear_curve_state(self, curve_index: int):
        """Clear all transformation state for a curve."""
        if curve_index in self._states:
            del self._states[curve_index]