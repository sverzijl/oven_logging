"""Quality Metrics tab — extracted from app.py's original tab4 block."""
import math

import streamlit as st

from src.visualization.metric_cards import (
    create_metric_card,
    create_metric_dashboard,
    create_simple_metric,
)
from src.visualization.plots import ThermalPlotter


def compute_time_to_target_fraction(time_to_target, total_time):
    """Return time_to_target as a fraction of total bake time, or None (#38).

    Guards the division: a zero/negative/NaN/None total bake time (degenerate
    single-sample curve) or a None time-to-target yields None instead of a
    ZeroDivisionError or NaN.
    """
    if time_to_target is None or total_time is None:
        return None
    try:
        total = float(total_time)
    except (TypeError, ValueError):
        return None
    if not (total > 0) or math.isnan(total):
        return None
    return float(time_to_target) / total


def render():
    st.header("Quality Metrics Analysis")

    # Calculate quality metrics
    quality_metrics = st.session_state.analyzer.calculate_quality_metrics()

    # Convert time to target to percentage if available (#38: guarded division).
    time_to_target_pct = compute_time_to_target_fraction(
        quality_metrics.get('time_to_target_minutes'),
        st.session_state.data['TimeMinutes'].max(),
    )

    # Create beautiful metric dashboard
    metrics_for_dashboard = {
        'core_uniformity_cv': quality_metrics.get('core_uniformity_cv'),
        'heating_rate_consistency': quality_metrics.get('heating_rate_consistency'),
        'max_core_temp': quality_metrics.get('max_core_temp'),
        'quality_score': quality_metrics.get('quality_score')
    }

    create_metric_dashboard(metrics_for_dashboard)

    # Additional metrics in a cleaner format
    st.markdown("### Additional Measurements")

    col1, col2 = st.columns(2)

    with col1:
        # Time to target with proper percentage
        if time_to_target_pct is not None:
            create_metric_card(
                'time_to_target_minutes',
                time_to_target_pct,
                custom_label=f"Time to 93°C ({quality_metrics['time_to_target_minutes']:.1f} min)"
            )
        else:
            create_simple_metric("Time to 93°C", "Not reached", "#ff4d4f", "⏱️")

        # Final core temperature
        final_temp_color = "#52c41a" if 93 <= quality_metrics['final_core_temp'] <= 98 else "#faad14"
        create_simple_metric(
            "Final Core Temperature",
            f"{quality_metrics['final_core_temp']:.1f}°C",
            final_temp_color,
            "🎯"
        )

    with col2:
        # Uniformity rating
        rating_colors = {
            "Excellent": "#52c41a",
            "Good": "#73d13d",
            "Acceptable": "#faad14",
            "Poor": "#ff4d4f"
        }
        rating_color = rating_colors.get(quality_metrics['core_uniformity_rating'], "#d9d9d9")
        create_simple_metric(
            "Uniformity Rating",
            quality_metrics['core_uniformity_rating'],
            rating_color,
            "📊"
        )

    # Visual charts section
    st.markdown("### Visual Analysis")

    # Quality gauge charts
    plotter = ThermalPlotter()
    fig_quality = plotter.plot_quality_metrics_gauge(quality_metrics)
    st.plotly_chart(fig_quality, width="stretch")

    # Uniformity analysis
    st.subheader("Temperature Uniformity Over Time")
    fig_uniformity = plotter.plot_temperature_uniformity(st.session_state.data)
    st.plotly_chart(fig_uniformity, width="stretch")
