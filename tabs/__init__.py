"""Per-tab render modules for the Thermal Profile Analyzer Streamlit app.

Each module exposes a zero-argument ``render()`` that draws its tab's
content into the current Streamlit container, reading from
``st.session_state`` for shared state.
"""
