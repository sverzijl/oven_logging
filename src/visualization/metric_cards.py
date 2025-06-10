"""Beautiful metric cards with explanations for Streamlit UI."""

import streamlit as st
from typing import Dict, Tuple, Optional

# Quality metric definitions with detailed explanations
METRIC_DEFINITIONS = {
    "core_uniformity_cv": {
        "name": "Core Uniformity",
        "unit": "CV",
        "format": ".3f",
        "icon": "🎯",
        "ranges": [
            (0.0, 0.02, "Excellent", "#52c41a", "Very even heating throughout product"),
            (0.02, 0.05, "Good", "#73d13d", "Acceptable for most products"),
            (0.05, 0.10, "Acceptable", "#faad14", "May have quality variations"),
            (0.10, float('inf'), "Poor", "#ff4d4f", "Expect inconsistent product quality")
        ],
        "description": "Measures temperature consistency across multiple core sensors",
        "why_it_matters": "Uneven core temperatures lead to some parts being over/under-baked, affecting texture and shelf life.",
        "interpretation": "Lower values indicate more uniform heating. The coefficient of variation (CV) is the standard deviation divided by the mean."
    },
    
    "heating_rate_consistency": {
        "name": "Heating Consistency",
        "unit": "%",
        "format": ".1%",
        "icon": "📈",
        "ranges": [
            (0.9, 1.0, "Excellent", "#52c41a", "Very stable oven conditions"),
            (0.7, 0.9, "Good", "#73d13d", "Normal variation"),
            (0.5, 0.7, "Acceptable", "#faad14", "Some oven cycling evident"),
            (0.0, 0.5, "Poor", "#ff4d4f", "Unstable conditions, check equipment")
        ],
        "description": "Measures how steady the heating rate is throughout baking",
        "why_it_matters": "Consistent heating ensures predictable results and optimal texture development. Erratic heating can cause quality issues.",
        "interpretation": "Percentage indicates stability of temperature rise. 100% means perfectly steady heating."
    },
    
    "max_core_temp": {
        "name": "Maximum Core Temperature",
        "unit": "°C",
        "format": ".1f",
        "icon": "🌡️",
        "ranges": [
            (93, 98, "Optimal", "#52c41a", "Perfect for most breads"),
            (90, 93, "Low", "#faad14", "May be slightly underbaked"),
            (98, 102, "High", "#faad14", "Risk of dry crumb"),
            (0, 90, "Under", "#ff4d4f", "Underbaked - food safety risk"),
            (102, float('inf'), "Over", "#ff4d4f", "Overbaked - very dry")
        ],
        "description": "Highest internal temperature reached during baking",
        "why_it_matters": "Ensures food safety and proper starch gelatinization. Too low risks gummy texture and spoilage. Too high causes dryness.",
        "interpretation": "93-98°C is ideal for most bread products. Adjust based on specific product requirements."
    },
    
    "time_to_target_minutes": {
        "name": "Time to Target (93°C)",
        "unit": "min",
        "format": ".1f",
        "icon": "⏱️",
        "ranges": [
            (0.8, 0.9, "Optimal", "#52c41a", "Balanced baking"),
            (0.7, 0.8, "Fast", "#faad14", "May burn exterior"),
            (0.9, 0.95, "Slow", "#faad14", "Slight energy waste"),
            (0.0, 0.7, "Too Fast", "#ff4d4f", "Exterior burns before interior done"),
            (0.95, 1.0, "Too Slow", "#ff4d4f", "Excessive moisture loss")
        ],
        "description": "When core reaches 93°C as percentage of total bake time",
        "why_it_matters": "Indicates if oven zones are properly balanced. Too early means aggressive heating that may burn crust. Too late wastes energy and dries product.",
        "interpretation": "Should occur at 80-90% of total bake time for optimal results."
    },
    
    "quality_score": {
        "name": "Overall Quality Score",
        "unit": "/100",
        "format": ".0f",
        "icon": "⭐",
        "ranges": [
            (90, 100, "Excellent", "#52c41a", "Premium quality expected"),
            (75, 90, "Good", "#73d13d", "Standard quality achieved"),
            (60, 75, "Acceptable", "#faad14", "Some improvements needed"),
            (0, 60, "Poor", "#ff4d4f", "Significant issues present")
        ],
        "description": "Composite score combining all quality factors",
        "why_it_matters": "Quick overall assessment of baking quality. Combines uniformity, consistency, and target achievement.",
        "interpretation": "Deductions: Poor uniformity (-30), Inconsistent heating (-20), Missing target temp (-25)"
    }
}


def get_metric_color_and_rating(value: float, ranges: list) -> Tuple[str, str, str]:
    """Get color and rating for a metric value based on defined ranges."""
    for min_val, max_val, rating, color, description in ranges:
        if min_val <= value < max_val:
            return color, rating, description
    return "#d9d9d9", "Unknown", "Value out of expected range"


def create_metric_card(
    metric_key: str,
    value: Optional[float],
    show_details: bool = True,
    custom_label: Optional[str] = None
) -> None:
    """
    Create a beautiful metric card with explanation.
    
    Args:
        metric_key: Key from METRIC_DEFINITIONS
        value: The metric value to display
        show_details: Whether to show expandable details
        custom_label: Optional custom label instead of default
    """
    if metric_key not in METRIC_DEFINITIONS:
        st.error(f"Unknown metric: {metric_key}")
        return
    
    metric_def = METRIC_DEFINITIONS[metric_key]
    
    # Handle None values
    if value is None:
        value_str = "N/A"
        color = "#d9d9d9"
        rating = "Not Available"
        rating_desc = "Metric could not be calculated"
    else:
        # Format value based on metric type
        if metric_def["format"] == ".1%":
            value_str = f"{value:.1%}"
        elif metric_def["format"] == ".3f":
            value_str = f"{value:.3f}"
        elif metric_def["format"] == ".1f":
            value_str = f"{value:.1f}"
        elif metric_def["format"] == ".0f":
            value_str = f"{value:.0f}"
        else:
            value_str = str(value)
        
        # Handle time to target percentage conversion
        if metric_key == "time_to_target_minutes" and value is not None:
            # This should be passed as a percentage already
            color, rating, rating_desc = get_metric_color_and_rating(value, metric_def["ranges"])
        else:
            color, rating, rating_desc = get_metric_color_and_rating(value, metric_def["ranges"])
    
    # Create the card
    label = custom_label or metric_def["name"]
    
    # Main metric display
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, {color}10 0%, {color}05 100%);
        border-left: 4px solid {color};
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
    ">
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <div>
                <span style="font-size: 24px; margin-right: 10px;">{metric_def['icon']}</span>
                <span style="font-size: 16px; font-weight: 600; color: #333;">{label}</span>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 28px; font-weight: bold; color: {color};">
                    {value_str}{metric_def['unit'] if metric_def['unit'] != '%' else ''}
                </div>
                <div style="font-size: 14px; color: #666; margin-top: -5px;">
                    {rating}
                </div>
            </div>
        </div>
        <div style="font-size: 13px; color: #666; margin-top: 8px; font-style: italic;">
            {rating_desc}
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Expandable details
    if show_details:
        with st.expander(f"ℹ️ About {metric_def['name']}", expanded=False):
            st.markdown(f"**What it measures:** {metric_def['description']}")
            st.markdown(f"**Why it matters:** {metric_def['why_it_matters']}")
            st.markdown(f"**How to interpret:** {metric_def['interpretation']}")
            
            # Show ranges
            st.markdown("**Quality ranges:**")
            for min_val, max_val, rating, color, desc in metric_def["ranges"]:
                if max_val == float('inf'):
                    range_str = f"> {min_val}"
                else:
                    range_str = f"{min_val} - {max_val}"
                
                st.markdown(f"""
                <div style="
                    display: flex; 
                    align-items: center; 
                    margin: 5px 0;
                    padding: 5px 10px;
                    background: {color}10;
                    border-radius: 5px;
                ">
                    <div style="
                        width: 12px; 
                        height: 12px; 
                        background: {color}; 
                        border-radius: 50%; 
                        margin-right: 10px;
                    "></div>
                    <span style="font-weight: 500; margin-right: 10px;">{rating}:</span>
                    <span style="color: #666;">{range_str} {metric_def['unit']}</span>
                </div>
                """, unsafe_allow_html=True)


def create_metric_dashboard(metrics: Dict[str, float], title: str = "Quality Metrics Dashboard") -> None:
    """
    Create a comprehensive dashboard of metric cards.
    
    Args:
        metrics: Dictionary of metric values
        title: Dashboard title
    """
    st.markdown(f"### {title}")
    
    # Info box about metrics
    with st.expander("📊 Understanding Quality Metrics", expanded=False):
        st.markdown("""
        These metrics provide a comprehensive assessment of your baking process quality:
        
        • **🎯 Uniformity**: How evenly heat distributes through the product
        • **📈 Consistency**: How stable the heating rate remains
        • **🌡️ Temperature**: Whether critical temperatures are achieved
        • **⏱️ Timing**: If heating progresses at optimal pace
        • **⭐ Overall**: Combined quality assessment
        
        Click on any metric's ℹ️ button for detailed explanation.
        """)
    
    # Create metric cards in a grid
    col1, col2 = st.columns(2)
    
    with col1:
        if 'core_uniformity_cv' in metrics:
            create_metric_card('core_uniformity_cv', metrics.get('core_uniformity_cv'))
        
        if 'max_core_temp' in metrics:
            create_metric_card('max_core_temp', metrics.get('max_core_temp'))
        
        if 'quality_score' in metrics:
            create_metric_card('quality_score', metrics.get('quality_score'))
    
    with col2:
        if 'heating_rate_consistency' in metrics:
            create_metric_card('heating_rate_consistency', metrics.get('heating_rate_consistency'))
        
        # Convert time to target to percentage if available
        if 'time_to_target_minutes' in metrics and metrics.get('time_to_target_minutes') is not None:
            # Need total bake time to calculate percentage
            # This should be passed from the app
            create_metric_card('time_to_target_minutes', metrics.get('time_to_target_minutes'))


def create_simple_metric(label: str, value: str, color: str = "#1f77b4", icon: str = "📊") -> None:
    """Create a simple metric display without detailed explanations."""
    st.markdown(f"""
    <div style="
        background: {color}10;
        border-left: 3px solid {color};
        padding: 10px 15px;
        border-radius: 5px;
        margin: 5px 0;
    ">
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <span style="font-size: 14px; color: #666;">
                {icon} {label}
            </span>
            <span style="font-size: 18px; font-weight: bold; color: {color};">
                {value}
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)