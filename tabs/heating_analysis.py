"""Heating Analysis tab — extracted from app.py's original tab5 block."""
import plotly.graph_objects as go
import streamlit as st

from src.visualization.plots import ThermalPlotter


def render():
    st.header("Heating Rate Analysis")

    # Add explanation
    with st.expander("📊 Understanding Heating Rates", expanded=False):
        st.markdown("""
        Heating rates show how quickly temperatures change throughout baking:

        **What to look for:**
        • **Consistent rates**: Indicate stable oven conditions
        • **Rapid changes**: May signal oven cycling or zone transitions
        • **Negative rates**: Normal during cooling or when moving between zones

        **Typical values:**
        • Initial heating: 2-6°C/min (aggressive)
        • Mid-bake: 0.5-2°C/min (controlled)
        • Final stage: 0-0.5°C/min (gentle)

        Erratic heating rates often indicate equipment issues or poor heat distribution.
        """)

    # Calculate heating rates
    smooth_data = st.session_state.get('smooth_data', True)
    rates = st.session_state.analyzer.calculate_heating_rates(smooth=smooth_data)

    # Heating rate plots
    plotter = ThermalPlotter()
    fig_rates = plotter.plot_heating_rates(rates)
    st.plotly_chart(fig_rates, width="stretch")

    # Temperature gradients
    st.subheader("Temperature Gradients")
    gradients = st.session_state.analyzer.calculate_temperature_gradients()

    # Create gradient plot
    fig_gradient = go.Figure()
    fig_gradient.add_trace(go.Scatter(
        x=gradients['TimeMinutes'],
        y=gradients['surface_core_gradient'],
        name='Surface-Core Gradient',
        line=dict(color='red', width=2)
    ))
    fig_gradient.add_trace(go.Scatter(
        x=gradients['TimeMinutes'],
        y=gradients['core_uniformity'],
        name='Core Uniformity (Std Dev)',
        yaxis='y2',
        line=dict(color='blue', width=2)
    ))
    fig_gradient.update_layout(
        title="Temperature Gradients Over Time",
        xaxis_title="Time (minutes)",
        yaxis_title="Surface-Core Gradient (°C)",
        yaxis2=dict(
            title="Core Uniformity (°C)",
            overlaying='y',
            side='right'
        ),
        hovermode='x unified'
    )
    st.plotly_chart(fig_gradient, width="stretch")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Avg Surface-Core Gradient",
            f"{gradients['surface_core_gradient'].mean():.1f}°C"
        )
    with col2:
        st.metric(
            "Max Surface-Core Gradient",
            f"{gradients['surface_core_gradient'].max():.1f}°C"
        )
    with col3:
        st.metric(
            "Avg Core Uniformity",
            f"{gradients['core_uniformity'].mean():.2f}°C"
        )
