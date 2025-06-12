"""Zone analysis cards with explanations for critical baking zones."""

import streamlit as st
import re
from typing import Dict, Optional, Tuple

# Zone explanations
ZONE_EXPLANATIONS = {
    "YEAST_KILL": {
        "process": "Final yeast fermentation followed by thermal inactivation",
        "importance": "Controls final volume and crumb structure. Too early kills yeast before optimal rise.",
        "ideal_duration": "1-2 minutes",
        "ideal_timing": "45-55% of bake time",
        "issues_if_short": "Insufficient oven spring, dense crumb",
        "issues_if_long": "Over-fermentation, coarse texture"
    },
    "STARCH_GELATINIZATION": {
        "process": "Starch granules absorb water and swell, forming crumb structure",
        "importance": "Creates the bread's texture and locks in moisture. Critical for shelf life.",
        "ideal_duration": "5-8 minutes",
        "ideal_timing": "55-65% of bake time",
        "issues_if_short": "Gummy texture, poor slicing",
        "issues_if_long": "Dry crumb, rapid staling"
    },
    "PROTEIN_DENATURATION": {
        "process": "Gluten proteins unfold and set, creating final structure",
        "importance": "Forms the permanent crumb structure and texture.",
        "ideal_duration": "4-7 minutes",
        "ideal_timing": "Overlaps with starch gelatinization",
        "issues_if_short": "Weak structure, collapse risk",
        "issues_if_long": "Tough, chewy texture"
    },
    "CRUST_FORMATION": {
        "process": "Surface dehydration and browning reactions",
        "importance": "Creates flavor, color, and protective barrier. Critical for appearance.",
        "ideal_duration": "3-10 minutes (product dependent)",
        "ideal_timing": "Throughout baking",
        "issues_if_short": "Pale color, soft crust, poor flavor",
        "issues_if_long": "Burnt crust, bitter flavor"
    },
    "MAILLARD_REACTION": {
        "process": "Amino acids and sugars react to create browning and flavor",
        "importance": "Develops characteristic bread aroma and golden-brown color.",
        "ideal_duration": "5-15 minutes",
        "ideal_timing": "Middle to end of bake",
        "issues_if_short": "Bland flavor, pale appearance",
        "issues_if_long": "Bitter notes, excessive browning"
    },
    "CARAMELIZATION": {
        "process": "Sugar breakdown at high temperatures",
        "importance": "Deep crust color and complex flavors for artisan breads.",
        "ideal_duration": "0-5 minutes (artisan only)",
        "ideal_timing": "Final stage if needed",
        "issues_if_short": "Missing complexity in artisan products",
        "issues_if_long": "Burnt, acrid flavors"
    },
    "TARGET_CORE": {
        "process": "Maintaining optimal internal temperature",
        "importance": "Ensures complete starch gelatinization and food safety.",
        "ideal_duration": "10-20% of total bake time",
        "ideal_timing": "80-100% of bake time",
        "issues_if_short": "Underbaked center, food safety risk",
        "issues_if_long": "Excessive moisture loss, dry product"
    }
}


def parse_duration_range(duration_str: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Parse duration string like "1-2 minutes" or "5-8 minutes" into min/max values.
    
    Args:
        duration_str: String containing duration range
        
    Returns:
        Tuple of (min_duration, max_duration) in minutes, or (None, None) if unparseable
    """
    if not duration_str:
        return None, None
    
    # Handle special cases
    if "artisan only" in duration_str.lower():
        # Parse the numeric part
        match = re.search(r'(\d+)-(\d+)', duration_str)
        if match:
            return float(match.group(1)), float(match.group(2))
    
    # Standard pattern: "X-Y minutes"
    match = re.search(r'(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)', duration_str)
    if match:
        return float(match.group(1)), float(match.group(2))
    
    # Single value pattern: "X minutes"
    match = re.search(r'(\d+(?:\.\d+)?)', duration_str)
    if match:
        val = float(match.group(1))
        return val, val
    
    # Percentage pattern for zones that use percentage of bake time
    if "%" in duration_str and "bake time" in duration_str.lower():
        # For percentage-based durations, return None to skip duration check
        return None, None
    
    return None, None


def create_zone_card(
    zone_key: str,
    zone_data: Dict,
    zone_config: Dict,
    show_explanation: bool = True
) -> None:
    """
    Create a detailed zone analysis card.
    
    Args:
        zone_key: Key from TEMPERATURE_ZONES
        zone_data: Analysis data for the zone
        zone_config: Configuration from TEMPERATURE_ZONES
        show_explanation: Whether to show detailed explanation
    """
    # Determine zone status
    duration = zone_data.get('duration', 0)
    percentage = zone_data.get('percentage', 0)
    
    # Get ideal targets
    explanation = ZONE_EXPLANATIONS.get(zone_key, {})
    ideal_duration_str = explanation.get('ideal_duration', '')
    ideal_timing_str = explanation.get('ideal_timing', '')
    
    # Initialize status
    status_color = zone_config.get('color', '#1f77b4')
    status_icon = "✅"
    status_text = "Normal"
    
    # Check if zone was not detected
    if duration == 0:
        status_icon = "❌"
        status_text = "Not detected"
        status_color = "#ff4d4f"
    else:
        # Parse ideal duration range
        ideal_min, ideal_max = parse_duration_range(ideal_duration_str)
        
        # Check duration against ideal
        if ideal_min is not None and ideal_max is not None:
            if duration < ideal_min:
                status_icon = "⚡"
                status_text = f"Too short ({duration:.1f} < {ideal_min} min)"
                status_color = "#ff4d4f"
            elif duration > ideal_max:
                status_icon = "🐌"
                status_text = f"Too long ({duration:.1f} > {ideal_max} min)"
                status_color = "#faad14"
            else:
                status_icon = "✅"
                status_text = f"Optimal ({ideal_min}-{ideal_max} min)"
                status_color = "#52c41a"
        
        # Special timing checks for specific zones
        if zone_key == "YEAST_KILL" and percentage > 0 and ideal_timing_str:
            # Parse timing percentage range
            timing_match = re.search(r'(\d+)-(\d+)%', ideal_timing_str)
            if timing_match:
                timing_min = int(timing_match.group(1))
                timing_max = int(timing_match.group(2))
                if timing_min <= percentage <= timing_max:
                    if status_icon == "✅":  # Only update if duration was also good
                        status_text = f"Optimal timing & duration"
                elif percentage < timing_min:
                    status_icon = "⚡"
                    status_text = f"Too early ({percentage:.0f}% < {timing_min}%)"
                    status_color = "#ff4d4f"
                else:
                    status_icon = "🐌"
                    status_text = f"Too late ({percentage:.0f}% > {timing_max}%)"
                    status_color = "#faad14"
    
    # Create the card using Streamlit components
    with st.container():
        # Zone header
        st.markdown(f"### {status_icon} {zone_config['name']}")
        st.caption(f"Temperature range: {zone_data.get('min', 0)}-{zone_data.get('max', 0)}°C")
        
        # Metrics in columns
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Duration", f"{duration:.1f} min")
        with col2:
            st.metric("% of Bake", f"{percentage:.1f}%")
        
        # Status
        if status_text == "Optimal timing":
            st.success(status_text)
        elif status_text == "Not detected":
            st.error(status_text)
        elif status_text in ["Too early", "Too late"]:
            st.warning(status_text)
        else:
            st.info(status_text)
    
    # Expandable explanation
    if show_explanation and zone_key in ZONE_EXPLANATIONS:
        with st.expander(f"ℹ️ About {zone_config['name']}", expanded=False):
            exp = ZONE_EXPLANATIONS[zone_key]
            
            st.markdown(f"**What happens:** {exp['process']}")
            st.markdown(f"**Why it matters:** {exp['importance']}")
            st.markdown(f"**Ideal duration:** {exp['ideal_duration']}")
            st.markdown(f"**Ideal timing:** {exp['ideal_timing']}")
            
            # Issues based on actual performance
            if duration == 0:
                st.warning(f"**Not detected:** This zone was not reached. Check oven temperatures.")
            elif duration < 1 and "1-" in exp['ideal_duration']:
                st.warning(f"**Too short:** {exp['issues_if_short']}")
            elif duration > 10 and zone_key not in ['TARGET_CORE', 'MAILLARD_REACTION']:
                st.warning(f"**Too long:** {exp['issues_if_long']}")
            
            # Temperature source indicator
            temp_type = zone_data.get('temperature_type', 'core')
            temp_source = zone_data.get('temperature_source', 'Unknown')
            st.info(f"📡 Measured using {temp_type} temperature ({temp_source})")


def create_compact_zone_card(
    zone_key: str,
    zone_data: Dict,
    zone_config: Dict
) -> None:
    """Create a compact zone card for grid layout."""
    # Determine zone status
    duration = zone_data.get('duration', 0)
    percentage = zone_data.get('percentage', 0)
    
    # Get ideal targets
    explanation = ZONE_EXPLANATIONS.get(zone_key, {})
    ideal_duration_str = explanation.get('ideal_duration', '')
    
    # Parse ideal duration range
    ideal_min, ideal_max = parse_duration_range(ideal_duration_str)
    
    # Determine status
    if duration == 0:
        status_icon = "❌"
        status_color = "#ff4d4f"
        status_text = "Not detected"
    elif ideal_min is not None and ideal_max is not None:
        if duration < ideal_min:
            status_icon = "⚡"
            status_color = "#ff4d4f"
            status_text = "Too short"
        elif duration > ideal_max:
            status_icon = "🐌"
            status_color = "#faad14"
            status_text = "Too long"
        else:
            status_icon = "✅"
            status_color = "#52c41a"
            status_text = "Optimal"
    else:
        status_icon = "✅"
        status_color = "#52c41a"
        status_text = "Normal"
    
    # Create compact card
    with st.container():
        st.markdown(f"""
        <div style='border: 1px solid {status_color}; border-radius: 8px; padding: 10px; margin-bottom: 10px;'>
            <div style='display: flex; justify-content: space-between; align-items: center;'>
                <div>
                    <b>{status_icon} {zone_config['name']}</b><br/>
                    <small style='color: gray;'>{zone_data.get('min', 0)}-{zone_data.get('max', 0)}°C</small>
                </div>
                <div style='text-align: right;'>
                    <b>{duration:.1f} min</b><br/>
                    <small style='color: {status_color};'>{status_text}</small>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Expandable details
        with st.expander(f"Details", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Duration", f"{duration:.1f} min")
                st.metric("% of Bake", f"{percentage:.1f}%")
            with col2:
                st.metric("Ideal", ideal_duration_str)
                temp_type = zone_data.get('temperature_type', 'core')
                st.metric("Sensor Type", temp_type.title())
            
            # Process explanation
            st.markdown(f"**Process:** {explanation.get('process', 'N/A')}")
            st.markdown(f"**Importance:** {explanation.get('importance', 'N/A')}")


def create_zone_summary_dashboard(zone_analysis: Dict) -> None:
    """Create a comprehensive zone analysis dashboard."""
    
    st.markdown("### Critical Temperature Zones")
    
    # Info box (more compact)
    with st.expander("📚 Understanding Temperature Zones", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            **Core Zones** (Internal Temperature):
            • 🔥 **Yeast Kill (55-57°C)**: Final fermentation
            • 🌾 **Starch Gelat. (65-82°C)**: Crumb structure
            • 🥚 **Protein Denat. (71-85°C)**: Gluten sets
            • 🎯 **Target Core (93-98°C)**: Complete baking
            """)
        with col2:
            st.markdown("""
            **Surface Zones** (Crust Temperature):
            • 🍞 **Crust Form. (110-180°C)**: Surface structure
            • 🎨 **Maillard (105-150°C)**: Browning & flavor
            • 🍮 **Caramelization (150-200°C)**: Deep color
            """)
    
    # Import constants here to avoid circular imports
    from config.constants import TEMPERATURE_ZONES
    
    # Create compact grid layout
    st.markdown("#### Zone Analysis Summary")
    
    # Core zones in 2 columns
    st.markdown("**Core Temperature Zones**")
    core_zones = ['YEAST_KILL', 'STARCH_GELATINIZATION', 'PROTEIN_DENATURATION', 'TARGET_CORE']
    col1, col2 = st.columns(2)
    
    for i, zone_key in enumerate(core_zones):
        if zone_key in zone_analysis:
            with col1 if i % 2 == 0 else col2:
                create_compact_zone_card(
                    zone_key,
                    zone_analysis[zone_key],
                    TEMPERATURE_ZONES[zone_key]
                )
    
    # Surface zones in 2 columns
    st.markdown("**Surface Temperature Zones**")
    surface_zones = ['CRUST_FORMATION', 'MAILLARD_REACTION', 'CARAMELIZATION']
    col1, col2 = st.columns(2)
    
    for i, zone_key in enumerate(surface_zones):
        if zone_key in zone_analysis:
            with col1 if i % 2 == 0 else col2:
                create_compact_zone_card(
                    zone_key,
                    zone_analysis[zone_key],
                    TEMPERATURE_ZONES[zone_key]
                )