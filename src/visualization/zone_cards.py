"""Zone analysis cards with explanations for critical baking zones."""

import streamlit as st
from typing import Dict, Optional

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
    
    # Determine if timing is good
    status_color = zone_config.get('color', '#1f77b4')
    status_icon = "✅"
    status_text = "Normal"
    
    # Check timing based on zone type
    if zone_key == "YEAST_KILL" and percentage > 0:
        if 45 <= percentage <= 55:
            status_icon = "✅"
            status_text = "Optimal timing"
        elif percentage < 45:
            status_icon = "⚡"
            status_text = "Too early"
            status_color = "#ff4d4f"
        else:
            status_icon = "🐌"
            status_text = "Too late"
            status_color = "#faad14"
    
    # Check duration
    if duration == 0:
        status_icon = "❌"
        status_text = "Not detected"
        status_color = "#ff4d4f"
    
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


def create_zone_summary_dashboard(zone_analysis: Dict) -> None:
    """Create a comprehensive zone analysis dashboard."""
    
    st.markdown("### Critical Temperature Zones")
    
    # Info box
    with st.expander("📚 Understanding Temperature Zones", expanded=False):
        st.markdown("""
        Bread baking involves several critical temperature zones where important chemical and physical changes occur:
        
        **Core Zones** (Internal Temperature):
        • 🔥 **Yeast Kill (55-57°C)**: Final fermentation and volume expansion
        • 🌾 **Starch Gelatinization (65-82°C)**: Crumb structure formation
        • 🥚 **Protein Denaturation (71-85°C)**: Gluten sets permanently
        • 🎯 **Target Core (93-98°C)**: Ensures complete baking
        
        **Surface Zones** (Crust Temperature):
        • 🍞 **Crust Formation (110-180°C)**: Surface dehydration and structure
        • 🎨 **Maillard Reaction (105-150°C)**: Browning and flavor development
        • 🍮 **Caramelization (150-200°C)**: Deep color and complex flavors
        
        Click on any zone for detailed information about its importance and optimal performance.
        """)
    
    # Import constants here to avoid circular imports
    from config.constants import TEMPERATURE_ZONES
    
    # Create zone cards in logical order
    # Core zones first
    st.markdown("#### 🎯 Core Temperature Zones")
    st.markdown("---")
    
    core_zones = ['YEAST_KILL', 'STARCH_GELATINIZATION', 'PROTEIN_DENATURATION', 'TARGET_CORE']
    for zone_key in core_zones:
        if zone_key in zone_analysis:
            with st.container():
                # Add some spacing and a subtle border
                st.markdown("""<style>
                .stContainer > div {
                    background-color: #f8f9fa;
                    padding: 1rem;
                    border-radius: 0.5rem;
                    margin-bottom: 1rem;
                }
                </style>""", unsafe_allow_html=True)
                
                create_zone_card(
                    zone_key,
                    zone_analysis[zone_key],
                    TEMPERATURE_ZONES[zone_key]
                )
                st.markdown("---")
    
    # Surface zones
    st.markdown("#### 🌡️ Surface Temperature Zones")
    st.markdown("---")
    
    surface_zones = ['CRUST_FORMATION', 'MAILLARD_REACTION', 'CARAMELIZATION']
    for zone_key in surface_zones:
        if zone_key in zone_analysis:
            with st.container():
                create_zone_card(
                    zone_key,
                    zone_analysis[zone_key],
                    TEMPERATURE_ZONES[zone_key]
                )
                st.markdown("---")