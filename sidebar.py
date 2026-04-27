"""Sidebar UI — file upload, curve selection, sensor overrides, analysis settings.

Extracted from app.py's ``with st.sidebar:`` block. ``render()`` mutates
``st.session_state`` in place and returns the small dict of analysis
settings (``show_zones``, ``smooth_data``, ``selected_sensors``,
``product_type``) that the main content area needs. Settings are also
written into ``st.session_state`` so tab modules can read them without
plumbing an args dict through every tab call.
"""
import streamlit as st

from config.constants import BAKEOUT_TARGETS, SENSOR_LIST
from src.analysis.s_curve_analysis import SCurveAnalyzer
from src.analysis.thermal_analysis import ThermalAnalyzer
from src.data.loader import ThermalProfileLoader, validate_thermal_data
# Expected-bake-time helpers moved into the dedicated Curve Boundary
# Review tab (M3 HMS Indomitable, mission 2026-04-24_235134_b68205bd);
# the sidebar widget was removed in M4 HMS Defender (mission
# 2026-04-24_235605_ced2aac9).  Pure helpers in
# ``src/ui/expected_duration_widgets.py`` remain in use by that tab.


def render():
    """Render the sidebar and return the analysis-settings dict."""
    # Default analysis settings
    show_zones = True
    smooth_data = True
    selected_sensors = None
    product_type = 'white_pan'

    with st.sidebar:
        st.header("📊 Data Input")

        uploaded_files = st.file_uploader(
            "Upload CSV files",
            type=['csv'],
            accept_multiple_files=True,
            help="Upload one or more thermal profile CSVs from Combustion Inc. probe"
        )

        if uploaded_files:
            # Process new files that haven't been loaded yet
            new_files_loaded = False
            for uploaded_file in uploaded_files:
                if uploaded_file.name not in st.session_state.files:
                    with st.spinner(f"Loading {uploaded_file.name}..."):
                        try:
                            # Load data directly from uploaded file buffer
                            loader = ThermalProfileLoader()
                            data, metadata = loader.load_csv(file_buffer=uploaded_file)

                            # Validate data
                            is_valid, issues = validate_thermal_data(data)

                            if is_valid:
                                # Store file info
                                st.session_state.files[uploaded_file.name] = {
                                    'loader': loader,
                                    'metadata': metadata,
                                    'curves': loader.get_all_curves()
                                }

                                num_curves = loader.get_curve_count()
                                if num_curves > 1:
                                    st.success(f"✅ {uploaded_file.name}: Found {num_curves} baking curves.")
                                else:
                                    st.success(f"✅ {uploaded_file.name}: Loaded successfully!")

                                new_files_loaded = True
                            else:
                                st.error(f"❌ {uploaded_file.name}: Data validation failed:")
                                for issue in issues:
                                    st.warning(issue)
                        except Exception as e:
                            st.error(f"Error loading {uploaded_file.name}: {str(e)}")

            # Rebuild all curves list when new files are loaded
            if new_files_loaded or not st.session_state.all_curves:
                st.session_state.all_curves = []
                for filename, file_info in st.session_state.files.items():
                    for curve_idx, curve in enumerate(file_info['curves']):
                        st.session_state.all_curves.append({
                            'filename': filename,
                            'file_curve_index': curve_idx,
                            'curve_data': curve,
                            'loader': file_info['loader'],
                            'metadata': file_info['metadata']
                        })

                # Set initial curve if this is the first load
                if st.session_state.data is None and st.session_state.all_curves:
                    first_curve = st.session_state.all_curves[0]
                    st.session_state.current_file = first_curve['filename']
                    st.session_state.loader = first_curve['loader']
                    st.session_state.metadata = first_curve['metadata']
                    st.session_state.data = first_curve['curve_data']['data']
                    st.session_state.analyzer = ThermalAnalyzer(st.session_state.data, st.session_state.metadata, st.session_state.loader)
                    st.session_state.s_curve_analyzer = SCurveAnalyzer(st.session_state.data, st.session_state.metadata, st.session_state.loader)
                    st.session_state.global_curve_index = 0

        # File and curve selection
        if st.session_state.all_curves:
            st.divider()
            st.header("📊 Curve Selection")

            # Display loaded files
            st.subheader("Loaded Files")
            for filename in st.session_state.files.keys():
                num_curves = len(st.session_state.files[filename]['curves'])
                st.text(f"📄 {filename} ({num_curves} curve{'s' if num_curves > 1 else ''})")

            # Create curve options with file names
            curve_options = []
            for i, curve_info in enumerate(st.session_state.all_curves):
                curve_data = curve_info['curve_data']
                file_curve_idx = curve_info['file_curve_index']
                filename = curve_info['filename']

                # Create descriptive label
                if len(st.session_state.files[filename]['curves']) > 1:
                    curve_label = f"{filename} - Curve {file_curve_idx+1}: {curve_data['duration']:.1f} min, Max {curve_data['max_temp']:.0f}°C"
                else:
                    curve_label = f"{filename}: {curve_data['duration']:.1f} min, Max {curve_data['max_temp']:.0f}°C"
                curve_options.append(curve_label)

            # Curve selector
            selected_curve_label = st.selectbox(
                "Select baking curve to analyze",
                options=curve_options,
                index=st.session_state.global_curve_index
            )

            # Update selection if changed
            new_index = curve_options.index(selected_curve_label)
            if new_index != st.session_state.global_curve_index:
                st.session_state.global_curve_index = new_index
                selected_curve = st.session_state.all_curves[new_index]

                # Update session state with selected curve
                st.session_state.current_file = selected_curve['filename']
                st.session_state.loader = selected_curve['loader']
                st.session_state.metadata = selected_curve['metadata']
                st.session_state.data = selected_curve['curve_data']['data']
                st.session_state.current_curve_index = selected_curve['file_curve_index']

                # Set curve in loader
                st.session_state.loader.set_current_curve(selected_curve['file_curve_index'])

                # Recreate analyzers
                st.session_state.analyzer = ThermalAnalyzer(st.session_state.data, st.session_state.metadata, st.session_state.loader)
                st.session_state.s_curve_analyzer = SCurveAnalyzer(st.session_state.data, st.session_state.metadata, st.session_state.loader)

            # Display current curve info
            if st.session_state.global_curve_index < len(st.session_state.all_curves):
                current_curve = st.session_state.all_curves[st.session_state.global_curve_index]
                curve_info = current_curve['curve_data']

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Duration", f"{curve_info['duration']:.1f} min")
                with col2:
                    st.metric("Max Temperature", f"{curve_info['max_temp']:.1f}°C")
                with col3:
                    st.metric("Data Points", curve_info['samples'])

                # Display file metadata
                with st.expander("📋 File Metadata"):
                    metadata = current_curve['metadata']
                    for key, value in metadata.items():
                        if key not in ['sample_period_ms', 'sample_period_s', 'created_datetime']:
                            st.text(f"{key}: {value}")

                # Display sensor assignments
                if st.session_state.loader:
                    with st.expander("🌡️ Sensor Role Assignments"):
                        assignments = st.session_state.loader.get_sensor_assignments()
                        if assignments:
                            if 'core' in assignments:
                                st.text(f"Core: {assignments['core']}")
                            if 'surface' in assignments:
                                st.text(f"Surface: {assignments['surface']}")
                            if 'ambient' in assignments:
                                st.text(f"Ambient: {assignments['ambient']}")
                            if 'method' in assignments:
                                st.text(f"Method: {assignments['method']}")

                            # Show detailed info if available
                            for role in ['core_info', 'surface_info', 'ambient_info']:
                                if role in assignments:
                                    role_name = role.replace('_info', '').title()
                                    info = assignments[role]
                                    if 'all_sensors' in info:
                                        st.text(f"\n{role_name} sensor usage:")
                                        for sensor, count in sorted(info['all_sensors'].items()):
                                            percentage = (count / sum(info['all_sensors'].values())) * 100
                                            st.text(f"  {sensor}: {percentage:.1f}%")
                        else:
                            st.info("Sensor assignments not available for this dataset")

        # Sensor Role Configuration
        if st.session_state.data is not None and st.session_state.loader:
            st.divider()
            st.header("🎯 Sensor Role Configuration")

            # Show current assignments
            assignments = st.session_state.loader.get_sensor_assignments_with_overrides(
                st.session_state.current_curve_index
            )

            # Display automatic vs override status
            if assignments.get('has_overrides'):
                st.info("📝 Using manual sensor assignments for this curve")
                if st.button("Reset to Automatic Detection"):
                    st.session_state.loader.clear_sensor_overrides(st.session_state.current_curve_index)
                    # Recreate analyzers with new assignments
                    st.session_state.analyzer = ThermalAnalyzer(
                        st.session_state.data,
                        st.session_state.metadata,
                        st.session_state.loader
                    )
                    st.session_state.s_curve_analyzer = SCurveAnalyzer(
                        st.session_state.data,
                        st.session_state.metadata,
                        st.session_state.loader
                    )
                    st.rerun()
            else:
                st.info("🤖 Using automatic sensor detection")

            # Manual override controls
            with st.expander("Override Sensor Assignments", expanded=False):
                st.markdown("Select which sensors represent each role for this specific curve:")
                st.markdown("*Topology rule: core < surface ≤ ambient ≤ lid. Through-loaf insertions (ambient on both sides) are accepted.*")

                curve_idx = st.session_state.current_curve_index

                # Core sensor (single selection)
                current_core = st.session_state.loader.get_core_sensor(curve_idx)
                core_sensor = st.selectbox(
                    "Core Sensor (single sensor for core temperature)",
                    options=list(SENSOR_LIST),
                    index=list(SENSOR_LIST).index(current_core) if current_core else 0,
                    key=f"core_override_{curve_idx}",
                    help="Select the sensor that best represents the core temperature"
                )

                # Surface sensor (single selection)
                current_surface = st.session_state.loader.get_surface_sensor(curve_idx)
                surface_sensor = st.selectbox(
                    "Surface/Crust Sensor (interface between core and ambient)",
                    options=list(SENSOR_LIST),
                    index=list(SENSOR_LIST).index(current_surface) if current_surface else 6,
                    key=f"surface_override_{curve_idx}",
                    help="Select the sensor at the bread surface."
                )

                # Ambient sensors (multiselect; default = current automatic ambient list)
                current_ambient = st.session_state.loader.get_ambient_sensors(curve_idx) or []
                ambient_sensors_choice = st.multiselect(
                    "Ambient Sensors (one or more sensors in the oven air)",
                    options=list(SENSOR_LIST),
                    default=[s for s in current_ambient if s in SENSOR_LIST],
                    key=f"ambient_override_{curve_idx}",
                    help=(
                        "Select sensors that read oven-air temperature. Through-loaf "
                        "exception: if the probe pierces the loaf, you may pick sensors "
                        "from BOTH ends with the surface sensor between them."
                    ),
                )

                # Lid sensor (single selection, optional)
                current_lid = st.session_state.loader.get_lid_sensor(curve_idx)
                lid_options = ["None"] + list(SENSOR_LIST)
                lid_default_idx = (
                    lid_options.index(current_lid) if current_lid in lid_options else 0
                )
                lid_choice = st.selectbox(
                    "Lid Sensor (optional; the sensor pressed against an oven lid)",
                    options=lid_options,
                    index=lid_default_idx,
                    key=f"lid_override_{curve_idx}",
                    help=(
                        "Select 'None' for non-lidded bakes. When set, the chosen sensor "
                        "writes a LidTemperature column."
                    ),
                )
                lid_sensor = None if lid_choice == "None" else lid_choice

                # Show inferred internal sensors for context
                st.markdown("### Inferred Sensor Groups")
                if surface_sensor:
                    surface_num = int(surface_sensor[1:])
                    internal_sensors = [f'T{i}' for i in range(1, surface_num)]
                    if internal_sensors:
                        st.info(f"**Internal sensors**: {', '.join(internal_sensors)} (all sensors below surface)")
                    else:
                        st.warning("No internal sensors (surface is T1)")
                    st.info(f"**Surface sensor**: {surface_sensor}")
                    if ambient_sensors_choice:
                        st.info(f"**Ambient sensors**: {', '.join(ambient_sensors_choice)}")
                    if lid_sensor:
                        st.info(f"**Lid sensor**: {lid_sensor}")

                if st.button("Apply Overrides"):
                    # Authoritative validation lives in the loader
                    # (_validate_override_topology). The sidebar mirrors only
                    # presence/uniqueness checks the loader can't infer from
                    # values alone.
                    errors = []
                    if not core_sensor:
                        errors.append("Please select a core sensor")
                    if not surface_sensor:
                        errors.append("Please select a surface sensor")

                    if not errors:
                        # Build the prospective override dict and let the
                        # loader's validator decide; surface ValueError as
                        # st.error rather than letting the exception kill the
                        # render.
                        prospective = {
                            'core': core_sensor,
                            'surface': surface_sensor,
                        }
                        if ambient_sensors_choice:
                            prospective['ambient'] = list(ambient_sensors_choice)
                        prospective['lid'] = lid_sensor  # may be None
                        try:
                            ThermalProfileLoader._validate_override_topology(prospective)
                        except ValueError as ex:
                            errors.append(str(ex))

                    if errors:
                        for error in errors:
                            st.error(error)
                    else:
                        loader = st.session_state.loader
                        loader.set_sensor_override(curve_idx, 'core', core_sensor)
                        loader.set_sensor_override(curve_idx, 'surface', surface_sensor)
                        if ambient_sensors_choice:
                            loader.set_sensor_override(
                                curve_idx, 'ambient', list(ambient_sensors_choice)
                            )
                        # Lid override is always applied; None explicitly
                        # clears any prior lid pick.
                        loader.set_sensor_override(curve_idx, 'lid', lid_sensor)
                        # Recreate analyzers with new assignments
                        st.session_state.analyzer = ThermalAnalyzer(
                            st.session_state.data,
                            st.session_state.metadata,
                            st.session_state.loader
                        )
                        st.session_state.s_curve_analyzer = SCurveAnalyzer(
                            st.session_state.data,
                            st.session_state.metadata,
                            st.session_state.loader
                        )
                        st.rerun()

        # Analysis settings
        if st.session_state.data is not None:
            st.divider()
            st.header("⚙️ Analysis Settings")

            # Move sensor display selection to tabs
            show_zones = st.checkbox("Show temperature zones", value=show_zones)
            smooth_data = st.checkbox("Apply smoothing", value=smooth_data)

            # Product type selection for bake-out analysis
            st.subheader("🍞 Product Type")
            product_type = st.selectbox(
                "Select product type",
                options=list(BAKEOUT_TARGETS.keys()),
                format_func=lambda x: x.replace('_', ' ').title(),
                help="Product type affects bake-out target percentages",
                index=0
            )

            # File management
            if st.session_state.files:
                st.divider()
                st.header("📁 File Management")

                files_to_remove = []
                for filename in st.session_state.files.keys():
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.text(f"📄 {filename}")
                    with col2:
                        if st.button("🗑", key=f"remove_{filename}", help=f"Remove {filename}"):
                            files_to_remove.append(filename)

                # Remove files and rebuild curve list
                if files_to_remove:
                    for filename in files_to_remove:
                        del st.session_state.files[filename]

                    # Rebuild all curves list
                    st.session_state.all_curves = []
                    for fname, file_info in st.session_state.files.items():
                        for curve_idx, curve in enumerate(file_info['curves']):
                            st.session_state.all_curves.append({
                                'filename': fname,
                                'file_curve_index': curve_idx,
                                'curve_data': curve,
                                'loader': file_info['loader'],
                                'metadata': file_info['metadata']
                            })

                    # Reset to first curve if current curve was removed
                    if st.session_state.all_curves:
                        if st.session_state.global_curve_index >= len(st.session_state.all_curves):
                            st.session_state.global_curve_index = 0
                        first_curve = st.session_state.all_curves[0]
                        st.session_state.current_file = first_curve['filename']
                        st.session_state.loader = first_curve['loader']
                        st.session_state.metadata = first_curve['metadata']
                        st.session_state.data = first_curve['curve_data']['data']
                        st.session_state.analyzer = ThermalAnalyzer(st.session_state.data, st.session_state.metadata)
                        st.session_state.s_curve_analyzer = SCurveAnalyzer(st.session_state.data, st.session_state.metadata)
                    else:
                        # No curves left, reset everything
                        st.session_state.data = None
                        st.session_state.metadata = None
                        st.session_state.analyzer = None
                        st.session_state.loader = None
                        st.session_state.current_curve_index = 0
                        st.session_state.global_curve_index = 0
                        st.session_state.current_file = None

                    st.rerun()

    # Expose analysis settings via session state so tab modules can read them
    # without us threading an arg dict through every render() call.
    st.session_state.show_zones = show_zones
    st.session_state.smooth_data = smooth_data
    st.session_state.product_type = product_type

    return {
        'show_zones': show_zones,
        'smooth_data': smooth_data,
        'selected_sensors': selected_sensors,
        'product_type': product_type,
    }


