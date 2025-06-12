"""Centralized configuration for visualizations."""

from typing import Dict, List, Tuple
from config.constants import TEMPERATURE_ZONES


class VisualizationConfig:
    """Centralized configuration for all visualizations."""
    
    # Zone display name to constant key mapping
    ZONE_KEY_MAPPING = {
        'Yeast Kill': 'YEAST_KILL',
        'Starch Gelatinization': 'STARCH_GELATINIZATION',
        'Protein Denaturation': 'PROTEIN_DENATURATION',
        'Maillard Reaction': 'MAILLARD_REACTION',
        'Caramelization': 'CARAMELIZATION',
        'Crust Formation': 'CRUST_FORMATION',
        'Target Core Temperature': 'TARGET_CORE',
        'Protein Coagulation': 'PROTEIN_COAGULATION'  # Not in TEMPERATURE_ZONES
    }
    
    # Default color for zones not in TEMPERATURE_ZONES
    DEFAULT_ZONE_COLOR = '#999999'
    
    # Curve colors for line charts
    CURVE_COLORS = ['blue', 'red', 'green', 'orange', 'purple', 'brown', 'pink', 'gray']
    
    # Heatmap colorscale (white to dark blue)
    HEATMAP_COLORSCALE = [
        [0, 'white'],
        [0.2, '#E6F3FF'],
        [0.4, '#B3D9FF'],
        [0.6, '#66B3FF'],
        [0.8, '#3399FF'],
        [1, '#0066CC']
    ]
    
    # Layout configuration
    DEFAULT_LAYOUT = {
        'template': 'plotly_white',
        'font': {'size': 12},
        'showlegend': True,
        'height': 600,
        'margin': {'l': 60, 'r': 60, 't': 80, 'b': 60}
    }
    
    # Legend configuration for horizontal legends
    HORIZONTAL_LEGEND = {
        'orientation': 'h',
        'yanchor': 'top',
        'y': -0.15,
        'xanchor': 'center',
        'x': 0.5
    }
    
    # Text formatting
    TEXT_FORMAT = {
        'duration': '{:.1f}',
        'temperature': '{:.1f}°C',
        'percentage': '{:.1f}%',
        'rate': '{:.3f}°C/s'
    }
    
    @classmethod
    def get_zone_color(cls, zone_name: str) -> str:
        """
        Get color for a zone by name.
        
        Args:
            zone_name: Display name of the zone
            
        Returns:
            Hex color code
        """
        zone_key = cls.ZONE_KEY_MAPPING.get(zone_name, zone_name.upper().replace(' ', '_'))
        zone_config = TEMPERATURE_ZONES.get(zone_key, {})
        return zone_config.get('color', cls.DEFAULT_ZONE_COLOR)
    
    @classmethod
    def get_curve_color(cls, index: int) -> str:
        """
        Get color for a curve by index.
        
        Args:
            index: Curve index
            
        Returns:
            Color name
        """
        return cls.CURVE_COLORS[index % len(cls.CURVE_COLORS)]
    
    @classmethod
    def format_duration(cls, value: float) -> str:
        """Format duration value."""
        return cls.TEXT_FORMAT['duration'].format(value)
    
    @classmethod
    def format_temperature(cls, value: float) -> str:
        """Format temperature value."""
        return cls.TEXT_FORMAT['temperature'].format(value)
    
    @classmethod
    def format_percentage(cls, value: float) -> str:
        """Format percentage value."""
        return cls.TEXT_FORMAT['percentage'].format(value)
    
    @classmethod
    def format_rate(cls, value: float) -> str:
        """Format heating rate value."""
        return cls.TEXT_FORMAT['rate'].format(value)
    
    @classmethod
    def get_layout_without_height(cls) -> Dict:
        """Get default layout without height parameter."""
        return {k: v for k, v in cls.DEFAULT_LAYOUT.items() if k != 'height'}