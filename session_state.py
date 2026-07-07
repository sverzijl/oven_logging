"""Session-state initialisation for the Thermal Profile Analyzer.

`initialize_session_state()` idempotently seeds every `st.session_state` key
the rest of the app reads. Key names are contract with Streamlit's state
machine and must not be renamed.
"""
import streamlit as st


def initialize_session_state():
    """Seed all session-state keys used by the app. Safe to call repeatedly."""
    if 'data' not in st.session_state:
        st.session_state.data = None
    if 'metadata' not in st.session_state:
        st.session_state.metadata = None
    if 'analyzer' not in st.session_state:
        st.session_state.analyzer = None
    # Seeded alongside ``analyzer`` for a symmetric contract: both are (re)built by
    # src/ui/curve_registry when a curve is selected, but seeding here means a read
    # before the first selection yields None rather than an AttributeError.
    if 's_curve_analyzer' not in st.session_state:
        st.session_state.s_curve_analyzer = None
    if 'loader' not in st.session_state:
        st.session_state.loader = None
    if 'current_curve_index' not in st.session_state:
        st.session_state.current_curve_index = 0
    # Multi-file support
    if 'files' not in st.session_state:
        st.session_state.files = {}  # {filename: {'loader': loader, 'metadata': metadata, 'curves': curves}}
    if 'all_curves' not in st.session_state:
        st.session_state.all_curves = []  # List of all curves from all files
    if 'current_file' not in st.session_state:
        st.session_state.current_file = None
    if 'global_curve_index' not in st.session_state:
        st.session_state.global_curve_index = 0
    # Persisted selection IDENTITY (filename, loader stable curve key) resolved by
    # src/ui/curve_registry. Stored as an identity rather than a raw index so a
    # boundary-edit re-sort cannot silently alias a different physical curve.
    if 'selected_curve_key' not in st.session_state:
        st.session_state.selected_curve_key = None
