"""Sidebar UI — file upload, curve selection, sensor overrides, analysis settings.

Extracted from app.py's ``with st.sidebar:`` block. ``render()`` mutates
``st.session_state`` in place and returns the small dict of analysis
settings (``show_zones``, ``smooth_data``, ``selected_sensors``,
``product_type``) that the main content area needs. Settings are also
written into ``st.session_state`` so tab modules can read them without
plumbing an args dict through every tab call.
"""
import hashlib

import streamlit as st

from config.constants import BAKEOUT_TARGETS, SENSOR_LIST
from src.data.loader import ThermalProfileLoader, validate_thermal_data
from src.ui import curve_registry
from src.ui.core_confidence_banner import (
    STATUS_RENDER_KIND,
    bake_metadata_status_line,
)
# Expected-bake-time helpers moved into the dedicated Curve Boundary
# Review tab (M3 HMS Indomitable, mission 2026-04-24_235134_b68205bd);
# the sidebar widget was removed in M4 HMS Defender (mission
# 2026-04-24_235605_ced2aac9).  Pure helpers in
# ``src/ui/expected_duration_widgets.py`` remain in use by that tab.


def classify_load_outcome(
    filename: str,
    num_curves: int,
    existing_signature: str | None = None,
    new_signature: str | None = None,
) -> dict:
    """Decide how a freshly-loaded file should be reported (#13, #28).

    Pure decision logic keyed only on hashable values so it is unit-testable
    without the Streamlit runtime. Returns a dict:

    * ``status`` — one of ``"success"`` / ``"warning"`` / ``"skip"``.
    * ``store``  — whether the file should be stored as a successful load.
    * ``message`` — the human-facing line for st.success / st.warning.

    Branches:
      - A name-collision with *identical* content -> ``skip`` (already loaded,
        nothing to do; not stored again).
      - A name-collision with *different* content (#28) -> ``warning``, not
        stored: silently ignoring it would hide a genuinely new file.
      - 0 detected curves (#13) -> ``warning``, not stored: the welcome screen
        stays and the operator can re-upload a corrected file.
      - >=1 curve -> ``success``, stored.
    """
    if existing_signature is not None:
        if new_signature is not None and new_signature == existing_signature:
            return {
                "status": "skip",
                "store": False,
                "message": f"{filename} is already loaded.",
            }
        return {
            "status": "warning",
            "store": False,
            "message": (
                f"A different file named '{filename}' is already loaded "
                "(same name, different content). Rename one of the files and "
                "re-upload to load both."
            ),
        }

    if num_curves <= 0:
        return {
            "status": "warning",
            "store": False,
            "message": f"No baking curves detected in {filename}.",
        }

    if num_curves > 1:
        message = f"✅ {filename}: Found {num_curves} baking curves."
    else:
        message = f"✅ {filename}: Loaded successfully!"
    return {"status": "success", "store": True, "message": message}


def _content_signature(file_buffer) -> str | None:
    """SHA-256 of the uploaded file's bytes, used to detect same-name /
    different-content collisions (#28). Best-effort: returns ``None`` if the
    buffer can't be read/seeked, in which case dedup falls back to name only.
    """
    try:
        pos = file_buffer.tell()
        data = file_buffer.getvalue() if hasattr(file_buffer, "getvalue") else file_buffer.read()
        file_buffer.seek(pos)
    except Exception:
        return None
    if isinstance(data, str):
        data = data.encode("utf-8", "replace")
    return hashlib.sha256(data).hexdigest()


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
                name = uploaded_file.name
                existing = st.session_state.files.get(name)
                if existing is not None:
                    # #28: a re-upload of an already-known NAME. Distinguish a
                    # genuine re-pick of the same file (skip silently) from a
                    # different file that happens to share the name (warn).
                    new_sig = _content_signature(uploaded_file)
                    outcome = classify_load_outcome(
                        filename=name,
                        num_curves=len(existing.get('curves', [])),
                        existing_signature=existing.get('content_signature', ''),
                        new_signature=new_sig if new_sig is not None
                        else existing.get('content_signature', ''),
                    )
                    if outcome['status'] == 'warning':
                        st.warning(outcome['message'])
                    continue

                with st.spinner(f"Loading {name}..."):
                    try:
                        # Compute the content signature BEFORE the loader
                        # consumes the buffer (#28 dedup key).
                        content_signature = _content_signature(uploaded_file)

                        # Load data directly from uploaded file buffer
                        loader = ThermalProfileLoader()
                        data, metadata = loader.load_csv(file_buffer=uploaded_file)

                        # Validate data
                        is_valid, issues = validate_thermal_data(data)

                        if not is_valid:
                            st.error(f"❌ {name}: Data validation failed:")
                            for issue in issues:
                                st.warning(issue)
                            continue

                        # #13: branch on the detected curve count. A 0-curve
                        # file must NOT be stored as a successful load (else the
                        # welcome screen is left and the name-keyed dedup makes
                        # it un-reloadable).
                        outcome = classify_load_outcome(
                            filename=name,
                            num_curves=loader.get_curve_count(),
                        )
                        if not outcome['store']:
                            st.warning(outcome['message'])
                            continue

                        st.session_state.files[name] = {
                            'loader': loader,
                            'metadata': metadata,
                            'curves': loader.get_all_curves(),
                            'content_signature': content_signature,
                        }
                        st.success(outcome['message'])
                        new_files_loaded = True
                    except Exception as e:
                        st.error(f"Error loading {name}: {str(e)}")

            # Rebuild the flat curve list + derived view from the live loaders when
            # new files arrive. On the very first load, target the first curve; on
            # subsequent loads the registry preserves the existing selection while
            # picking up the newly-appended curves. (DRY: the curve registry owns
            # all_curves / analyzer construction — see src/ui/curve_registry.py.)
            if new_files_loaded or not st.session_state.all_curves:
                if st.session_state.data is None and st.session_state.files:
                    first_filename = next(iter(st.session_state.files))
                    curve_registry.select_curve(first_filename, 0)
                else:
                    curve_registry.rebuild_registry()

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

            # Update selection if changed. The registry re-targets the analysis by
            # stable identity and rebuilds data/analyzers/caches in one place.
            new_index = curve_options.index(selected_curve_label)
            if new_index != st.session_state.global_curve_index:
                selected_curve = st.session_state.all_curves[new_index]
                curve_registry.select_curve(
                    selected_curve['filename'], selected_curve['file_curve_index']
                )

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
                    # The rerun re-derives the view; the registry's content signature
                    # (which folds the sensor picks) detects the change and rebuilds
                    # analyzers + derived caches.
                    st.rerun()
            else:
                st.info("🤖 Using automatic sensor detection")

            # Manual override controls
            with st.expander("Override Sensor Assignments", expanded=False):
                st.markdown("Select which sensors represent each role for this specific curve:")
                st.markdown("*Topology rule: core < surface ≤ ambient ≤ lid. Through-loaf insertions (ambient on both sides) are accepted.*")

                curve_idx = st.session_state.current_curve_index
                # Widget keys must be unique per (filename, curve_idx) so a
                # selection on one CSV doesn't carry over when the user
                # switches to another file. Streamlit persists widget state
                # under the `key=` argument; without the filename component,
                # a previously-touched ambient multiselect on one CSV ghosts
                # into the same widget on the next CSV. Same fix pattern as
                # mission 2026-04-24_102020 for the temperature_profile tab.
                file_key = (st.session_state.get('current_file') or 'nofile').replace(' ', '_')

                # Core sensor (single selection)
                current_core = st.session_state.loader.get_core_sensor(curve_idx)
                core_sensor = st.selectbox(
                    "Core Sensor (single sensor for core temperature)",
                    options=list(SENSOR_LIST),
                    index=list(SENSOR_LIST).index(current_core) if current_core else 0,
                    key=f"core_override_{file_key}_{curve_idx}",
                    help="Select the sensor that best represents the core temperature"
                )

                # Surface sensor (single selection)
                current_surface = st.session_state.loader.get_surface_sensor(curve_idx)
                surface_sensor = st.selectbox(
                    "Surface/Crust Sensor (interface between core and ambient)",
                    options=list(SENSOR_LIST),
                    index=list(SENSOR_LIST).index(current_surface) if current_surface else 6,
                    key=f"surface_override_{file_key}_{curve_idx}",
                    help="Select the sensor at the bread surface."
                )

                # Ambient sensors (multiselect; default = current automatic ambient list)
                current_ambient = st.session_state.loader.get_ambient_sensors(curve_idx) or []
                ambient_sensors_choice = st.multiselect(
                    "Ambient Sensors (one or more sensors in the oven air)",
                    options=list(SENSOR_LIST),
                    default=[s for s in current_ambient if s in SENSOR_LIST],
                    key=f"ambient_override_{file_key}_{curve_idx}",
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
                    key=f"lid_override_{file_key}_{curve_idx}",
                    help=(
                        "Select 'None' for non-lidded bakes. When set, the chosen sensor "
                        "writes a LidTemperature column."
                    ),
                )
                lid_sensor = None if lid_choice == "None" else lid_choice

                # ----------------------------------------------------
                # Inferred Continuous Positions (read-only)
                # ----------------------------------------------------
                # M6 hot-fix HMS Penelope: surface up the substantive
                # continuous-position result so the user can verify that
                # interpolation has engaged. ``nearest_sensor`` (above) is
                # still the override anchor; the values here are diagnostic.
                cs = st.session_state.loader.curve_sensor_assignments.get(
                    curve_idx, {}
                )
                core_x = cs.get("core_position_normalised")
                surface_x = cs.get("surface_position_normalised")
                lid_x = cs.get("lid_position_normalised")

                def _fmt_inferred(label: str, x_val, nearest_name) -> str:
                    if x_val is None:
                        return f"**Inferred {label}**: not detected"
                    if nearest_name:
                        try:
                            n_int = int(nearest_name[1:])
                            nearest_pos = (n_int - 1) / 7.0
                        except (ValueError, IndexError):
                            nearest_pos = None
                    else:
                        nearest_pos = None
                    if nearest_pos is not None and abs(x_val - nearest_pos) > 0.005:
                        return (
                            f"**Inferred {label}**: x={x_val:.3f} "
                            f"(interpolated; nearest sensor {nearest_name})"
                        )
                    if nearest_name:
                        return (
                            f"**Inferred {label}**: x={x_val:.3f} "
                            f"(at sensor {nearest_name})"
                        )
                    return f"**Inferred {label}**: x={x_val:.3f}"

                st.markdown("### Inferred Continuous Positions (read-only)")
                st.info(_fmt_inferred("core", core_x, cs.get("core")))
                st.info(_fmt_inferred("surface", surface_x, cs.get("surface")))
                if lid_x is not None or cs.get("lid"):
                    st.info(_fmt_inferred("lid", lid_x, cs.get("lid")))

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
                        # The rerun re-derives the view; the registry rebuilds the
                        # analyzers when the sensor-pick signature changes.
                        st.rerun()

            # ----------------------------------------------------------
            # Bake Metadata expander (M18 HMS Vigilant — Method 4 stub).
            # ----------------------------------------------------------
            # When the operator supplies loaf_thickness AND insertion_depth
            # the loader computes a *geometric* core position from physical
            # geometry alone — bypassing Method 1's thermal extrapolation.
            # When metadata is absent, Method 1 (relaxed parabolic clamp
            # with low-confidence labelling) engages naturally inside the
            # classifier. Same widget-key scoping pattern as M3b: keys must
            # include both filename and curve_idx so values entered for one
            # CSV/curve do not ghost into another.
            with st.expander(
                "Bake Metadata (optional — provide for high-accuracy core position)",
                expanded=False,
            ):
                st.markdown(
                    "When you supply loaf thickness *and* probe insertion "
                    "depth, the core position is computed from geometry "
                    "(`loaf_thickness/2 - insertion_depth_below_top`) and "
                    "interpolated between the bracketing sensors. Without "
                    "metadata, the classifier falls back to Method 1's "
                    "relaxed parabolic clamp with a `low_extrapolated` "
                    "confidence label."
                )

                curve_idx = st.session_state.current_curve_index
                file_key = (st.session_state.get('current_file') or 'nofile').replace(' ', '_')
                loader = st.session_state.loader
                current_meta = loader.get_bake_metadata(curve_idx) or {}

                # Active-model status line (M29): declare which model feeds the
                # current core trace, so the operator doesn't have to infer it
                # from the presence/absence of the Temperature Profile banner.
                _active_model, _detail = bake_metadata_status_line(loader, curve_idx)
                _label = {
                    "manual_override": "Manual sensor override active",
                    "method_4": "✅ Method 4 active (geometric core)",
                    "method_4_degraded": "⚠️ Method 4 active — geometric core past probe tip",
                    "method_1_high": "Method 1 active (classifier)",
                    "method_1_medium": "Method 1 active (classifier)",
                    "method_1_low": "⚠️ Method 1 active — low confidence",
                    "fallback": "Core model",
                }.get(_active_model, "Core model")
                _line = f"{_label}: {_detail}" if _detail else _label
                _kind = STATUS_RENDER_KIND.get(_active_model, "caption")
                if _kind == "success":
                    st.success(_line)
                elif _kind == "warning":
                    st.warning(_line)
                elif _kind == "info":
                    st.info(_line)
                else:
                    st.caption(_line)

                loaf_thickness = st.number_input(
                    "Loaf thickness (mm)",
                    min_value=0.0,
                    max_value=300.0,
                    value=float(current_meta.get('loaf_thickness_mm', 0.0)),
                    step=5.0,
                    help=(
                        "Total loaf height from tin bottom to top crust. "
                        "Leave at 0 if unknown."
                    ),
                    key=f"loaf_thickness_{file_key}_{curve_idx}",
                )
                insertion_depth = st.number_input(
                    "Probe insertion depth from loaf top (mm)",
                    min_value=0.0,
                    max_value=200.0,
                    value=float(current_meta.get('insertion_depth_mm', 0.0)),
                    step=5.0,
                    help=(
                        "Depth of probe tip (T1) below the loaf top surface. "
                        "Leave at 0 if unknown."
                    ),
                    key=f"insertion_depth_{file_key}_{curve_idx}",
                )
                oven_setpoint = st.number_input(
                    "Oven setpoint (°C)",
                    min_value=0.0,
                    max_value=400.0,
                    value=float(current_meta.get('oven_setpoint_C', 0.0)),
                    step=10.0,
                    help="Oven control setpoint. Leave at 0 if unknown.",
                    key=f"oven_setpoint_{file_key}_{curve_idx}",
                )
                lid_options = ["unknown", "open", "lidded", "tin"]
                lid_state_default = current_meta.get('lid_state', 'unknown')
                if lid_state_default not in lid_options:
                    lid_state_default = "unknown"
                lid_state_choice = st.selectbox(
                    "Lid / tin state",
                    options=lid_options,
                    index=lid_options.index(lid_state_default),
                    key=f"lid_state_{file_key}_{curve_idx}",
                    help=(
                        "Open = uncovered loaf; Lidded = baking lid pressed "
                        "down; Tin = baked in a tin (no lid contact)."
                    ),
                )
                steam_minutes = st.number_input(
                    "Steam phase duration (min)",
                    min_value=0.0,
                    max_value=20.0,
                    value=float(current_meta.get('steam_phase_minutes', 0.0)),
                    step=1.0,
                    help="Duration of steam injection at the start of the bake.",
                    key=f"steam_minutes_{file_key}_{curve_idx}",
                )

                col_apply, col_clear = st.columns(2)
                with col_apply:
                    if st.button(
                        "Apply Bake Metadata",
                        key=f"apply_metadata_{file_key}_{curve_idx}",
                    ):
                        new_meta = {}
                        if loaf_thickness > 0:
                            new_meta['loaf_thickness_mm'] = float(loaf_thickness)
                        if insertion_depth > 0:
                            new_meta['insertion_depth_mm'] = float(insertion_depth)
                        if oven_setpoint > 0:
                            new_meta['oven_setpoint_C'] = float(oven_setpoint)
                        if lid_state_choice != 'unknown':
                            new_meta['lid_state'] = lid_state_choice
                        if steam_minutes > 0:
                            new_meta['steam_phase_minutes'] = float(steam_minutes)
                        loader.set_bake_metadata(curve_idx, new_meta)
                        # The rerun re-derives the view; the registry's signature
                        # folds bake metadata, so the geometric core series
                        # propagates into downstream analytics automatically.
                        st.rerun()
                with col_clear:
                    if st.button(
                        "Clear Bake Metadata",
                        key=f"clear_metadata_{file_key}_{curve_idx}",
                    ):
                        loader.clear_bake_metadata(curve_idx)
                        # The rerun re-derives the view; the registry rebuilds
                        # analyzers when the bake-metadata signature changes.
                        st.rerun()

                # Show inferred geometric core when metadata is sufficient.
                geom_pos_mm = loader.get_geometric_core_position_mm_from_tip(
                    curve_idx
                )
                if geom_pos_mm is not None:
                    if geom_pos_mm > 0:
                        st.success(
                            f"**Geometric core**: {geom_pos_mm:.1f} mm above "
                            "probe tip (interpolated between T-sensors)."
                        )
                    elif geom_pos_mm < 0:
                        st.warning(
                            f"**Geometric core**: {-geom_pos_mm:.1f} mm BELOW "
                            "probe tip (probe inserted too shallow; series "
                            "degrades to T1)."
                        )
                    else:
                        st.success(
                            "**Geometric core**: at probe tip (T1)."
                        )
                else:
                    st.info(
                        "Metadata incomplete — provide both loaf thickness "
                        "and insertion depth to engage geometric core. "
                        "Method 1 fallback is active."
                    )

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

                # Remove files, then let the registry re-derive the view. It
                # rebuilds the flat curve list, resolves the surviving selection by
                # identity (or clamps to a neighbour / resets to the welcome screen
                # when nothing remains), and rebuilds analyzers WITH the loader —
                # which also closes the old file-removal bug that constructed the
                # analyzers without the loader arg and silently dropped sensor-role
                # resolution for the surviving curve.
                if files_to_remove:
                    for filename in files_to_remove:
                        del st.session_state.files[filename]
                    curve_registry.rebuild_registry()
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


