"""Tests for the single-source-of-truth curve registry (fix/boundary-review-propagation).

Root cause the registry closes: the Curve Boundary Review tab mutates the loader
(``set_curve_boundaries`` / ``add_manual_curve`` / ``remove_manual_curve`` /
``clear_curve_boundaries``), each of which REBINDS ``loader.all_curves`` to a fresh
list of fresh per-curve DataFrames. Before the fix, only that tab (which reads
``loader.all_curves`` live) updated; every other tab renders from the session-state
snapshots (``st.session_state.data`` / ``.analyzer`` / ``.all_curves`` /
``files[name]['curves']``) which were captured at load time and never rebuilt, so
they went stale. ``curve_registry.rebuild_registry()`` re-derives the whole view
from the live loaders on every rerun, resolving the selection by STABLE IDENTITY
(never a raw integer index, which a re-sort would silently alias to a different
physical curve).

Design contract locked here:
  * rebuild_registry() rebuilds the flat all_curves from live loaders and re-points
    st.session_state.{data,loader,metadata,current_curve_index,global_curve_index}.
  * Selection is resolved by identity ``(filename, loader._curve_stable_key(idx))``;
    only when that identity has vanished does it clamp to a neighbour.
  * Analyzers are rebuilt only when a content-addressed signature (boundaries +
    sensor picks + bake metadata) changes — no per-frame thrash — and ALWAYS carry
    the loader as the 3rd arg.
  * The _shared derived caches are invalidated when the signature changes.
  * Empty session resets cleanly (welcome-screen state).
  * Other files' loaders are never re-extracted (only read).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
from unittest.mock import MagicMock, patch

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

import streamlit as st  # noqa: E402

from src.data.loader import ThermalProfileLoader  # noqa: E402
from src.ui import curve_registry  # noqa: E402
from tabs import _shared  # noqa: E402


class _DictState(dict):
    """st.session_state stand-in: attribute + item access + .get()/.pop()."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


# ---------------------------------------------------------------------------
# Lightweight-but-real loader fixtures.
#
# We construct a real ThermalProfileLoader (so ``_curve_stable_key`` and
# ``set_current_curve`` are the genuine implementations) but assign ``all_curves``
# directly with small synthetic curve dicts, avoiding the slow spatial classifier.
# A boundary mutation is simulated the exact way ``_reapply_boundary_state`` does
# it: by REBINDING ``loader.all_curves`` to a fresh list.
# ---------------------------------------------------------------------------


def _mk_curve(start: int, n: int, added: int | None = None) -> dict:
    df = pd.DataFrame(
        {
            "Timestamp": [float(i) for i in range(n)],
            "TimeMinutes": [i / 60.0 for i in range(n)],
            "CoreTemperature": [20.0 + i for i in range(n)],
        }
    )
    curve = {
        "data": df,
        "start_idx": int(start),
        "end_idx": int(start + n - 1),
        "samples": int(n),
        "curve_number": 0,
        "duration": float(n) / 12.0,
        "max_temp": 20.0 + n,
        "exit_candidate_kind": "auto",
    }
    if added is not None:
        curve["_user_added_idx"] = int(added)
    return curve


def _mk_loader(curves: list[dict]) -> ThermalProfileLoader:
    ld = ThermalProfileLoader()
    ld.all_curves = list(curves)
    ld.raw_data = pd.concat([c["data"] for c in curves], ignore_index=True)
    ld.current_curve_index = 0
    ld.data = curves[0]["data"] if curves else None
    return ld


def _file_entry(ld: ThermalProfileLoader) -> dict:
    return {
        "loader": ld,
        "metadata": {"sample_period_s": 5.0},
        "curves": ld.all_curves,
        "content_signature": "sig",
    }


def _state(files: dict) -> _DictState:
    ss = _DictState()
    ss["files"] = files
    ss["all_curves"] = []
    ss["data"] = None
    ss["metadata"] = None
    ss["analyzer"] = None
    ss["s_curve_analyzer"] = None
    ss["loader"] = None
    ss["current_file"] = None
    ss["current_curve_index"] = 0
    ss["global_curve_index"] = 0
    ss["selected_curve_key"] = None
    ss["product_type"] = "white_pan"
    return ss


# ---------------------------------------------------------------------------
# 1. End-to-end staleness regression on a REAL single-curve CSV (the actual bug).
# ---------------------------------------------------------------------------


class TestEndToEndStalenessRealCSV:
    _CSV = PROJECT_ROOT / "ProbeData_1000BA3C_2025-05-30 09_46_16.csv"

    def test_boundary_edit_refreshes_session_data_and_analyzer(self):
        ld = ThermalProfileLoader()
        ld.load_csv(file_path=str(self._CSV))
        files = {"probe.csv": _file_entry(ld)}
        ss = _state(files)

        with patch.object(st, "session_state", ss):
            curve_registry.select_curve("probe.csv", 0)
            before = len(ss.data)
            c0 = ld.all_curves[0]
            # Operator drags a box in the detail plot -> loader.set_curve_boundaries.
            ld.set_curve_boundaries(0, int(c0["start_idx"]) + 20, int(c0["end_idx"]) - 20)
            # The boundary tab reruns; app.py's top-of-rerun rebuild picks it up.
            curve_registry.rebuild_registry()

            fresh = len(ld.all_curves[0]["data"])
            assert fresh < before, "sanity: the pinned window is smaller"
            # Session data must now equal the fresh slice, not the stale one.
            assert len(ss.data) == fresh
            assert ss.data is ld.all_curves[0]["data"]
            # Analyzer must be rebuilt from the fresh slice and carry the loader.
            assert len(ss.analyzer.data) == fresh
            assert ss.analyzer.loader is ld
            assert len(ss.s_curve_analyzer.data) == fresh


# ---------------------------------------------------------------------------
# 2. Fixed-index in-place edit (fast, synthetic) — data re-pointed, analyzer rebuilt.
# ---------------------------------------------------------------------------


class TestFixedIndexEdit:
    def test_reassigned_all_curves_repoints_data_and_rebuilds_analyzer(self):
        ld = _mk_loader([_mk_curve(0, 100)])
        ss = _state({"f.csv": _file_entry(ld)})
        with patch.object(st, "session_state", ss):
            curve_registry.select_curve("f.csv", 0)
            first_analyzer = ss.analyzer
            assert len(ss.data) == 100
            # Simulate set_curve_boundaries: rebind all_curves to a fresh list.
            ld.all_curves = [_mk_curve(20, 60)]
            curve_registry.rebuild_registry()
            assert len(ss.data) == 60
            assert ss.data is ld.all_curves[0]["data"]
            assert ss.analyzer is not first_analyzer  # signature changed -> rebuilt
            assert len(ss.analyzer.data) == 60


# ---------------------------------------------------------------------------
# 3. Identity-preserving reorder — the killer case a naive clamp gets WRONG.
# ---------------------------------------------------------------------------


class TestIdentityPreservingReorder:
    def test_insert_before_keeps_global_on_same_physical_curve(self):
        # Two detector curves at start=100 and start=300.
        ld = _mk_loader([_mk_curve(100, 50), _mk_curve(300, 50)])
        ss = _state({"f.csv": _file_entry(ld)})
        with patch.object(st, "session_state", ss):
            curve_registry.select_curve("f.csv", 1)  # viewing the start=300 bake
            assert ss.current_curve_index == 1
            assert ld.all_curves[ss.current_curve_index]["start_idx"] == 300

            # add_manual_curve claims an earlier region that sorts to position 0.
            ld.all_curves = [
                _mk_curve(0, 30, added=0),
                _mk_curve(100, 50),
                _mk_curve(300, 50),
            ]
            curve_registry.rebuild_registry()

            # A naive clamp would keep index 1 (the start=100 bake) — WRONG.
            # Identity resolution must land on the start=300 bake, now at index 2.
            assert ss.current_curve_index == 2
            assert ld.all_curves[ss.current_curve_index]["start_idx"] == 300
            assert ss.global_curve_index == 2


# ---------------------------------------------------------------------------
# 4. Editing a NON-selected curve must not move the global selection.
# ---------------------------------------------------------------------------


class TestNonCurrentEditPreservesGlobal:
    def test_edit_other_curve_keeps_global_identity_but_refreshes_object(self):
        ld = _mk_loader([_mk_curve(0, 100), _mk_curve(300, 100)])
        ss = _state({"f.csv": _file_entry(ld)})
        with patch.object(st, "session_state", ss):
            curve_registry.select_curve("f.csv", 0)  # global on the start=0 bake
            # Operator reviews & edits the OTHER bake (index 1) in the boundary tab.
            ld.all_curves = [_mk_curve(0, 100), _mk_curve(320, 60)]
            curve_registry.rebuild_registry()
            # Global stays on the start=0 bake; its slice is a fresh object.
            assert ss.current_curve_index == 0
            assert ld.all_curves[0]["start_idx"] == 0
            assert ss.data is ld.all_curves[0]["data"]


# ---------------------------------------------------------------------------
# 5. Curve-count visibility flip (drives the Curve Comparison tab gate).
# ---------------------------------------------------------------------------


class TestCountVisibilityFlip:
    def test_add_then_remove_flips_all_curves_length(self):
        ld = _mk_loader([_mk_curve(0, 100)])
        ss = _state({"f.csv": _file_entry(ld)})
        with patch.object(st, "session_state", ss):
            curve_registry.select_curve("f.csv", 0)
            assert len(ss.all_curves) == 1
            ld.all_curves = [_mk_curve(0, 100), _mk_curve(200, 50, added=0)]
            curve_registry.rebuild_registry()
            assert len(ss.all_curves) == 2
            ld.all_curves = [_mk_curve(0, 100)]
            curve_registry.rebuild_registry()
            assert len(ss.all_curves) == 1


# ---------------------------------------------------------------------------
# 6/7. Removing the viewed curve — clamp in range, no crash, analyzer keeps loader.
# ---------------------------------------------------------------------------


class TestRemoveViewedCurve:
    def test_remove_added_curve_clamps_and_keeps_loader(self):
        ld = _mk_loader([_mk_curve(0, 100), _mk_curve(200, 50, added=0)])
        ss = _state({"f.csv": _file_entry(ld)})
        with patch.object(st, "session_state", ss):
            curve_registry.select_curve("f.csv", 1)  # viewing the added curve
            ld.all_curves = [_mk_curve(0, 100)]  # removed
            curve_registry.rebuild_registry()
            assert 0 <= ss.global_curve_index < len(ss.all_curves)
            assert ss.current_curve_index == 0
            assert ss.analyzer.loader is ld
            assert ss.s_curve_analyzer.loader is ld


# ---------------------------------------------------------------------------
# 8. Idempotency — no analyzer thrash across no-op reruns (#20 dedup preserved).
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_repeated_rebuild_without_mutation_keeps_analyzer_identity(self):
        ld = _mk_loader([_mk_curve(0, 100)])
        ss = _state({"f.csv": _file_entry(ld)})
        with patch.object(st, "session_state", ss):
            curve_registry.select_curve("f.csv", 0)
            a1 = ss.analyzer
            s1 = ss.s_curve_analyzer
            curve_registry.rebuild_registry()
            curve_registry.rebuild_registry()
            assert ss.analyzer is a1
            assert ss.s_curve_analyzer is s1


# ---------------------------------------------------------------------------
# 9. Multi-file isolation — editing file B never touches file A's loader/curves.
# ---------------------------------------------------------------------------


class TestMultiFileIsolation:
    def test_editing_one_file_does_not_reextract_others(self):
        ldA = _mk_loader([_mk_curve(0, 100), _mk_curve(300, 100)])
        ldB = _mk_loader([_mk_curve(0, 80)])
        files = {"A.csv": _file_entry(ldA), "B.csv": _file_entry(ldB)}
        ss = _state(files)
        with patch.object(st, "session_state", ss):
            curve_registry.select_curve("B.csv", 0)
            a_curves_obj = ldA.all_curves  # identity must survive
            # Edit file B.
            ldB.all_curves = [_mk_curve(10, 40)]
            curve_registry.rebuild_registry()
            assert ldA.all_curves is a_curves_obj  # A untouched
            assert files["A.csv"]["curves"] is ldA.all_curves
            # Flat list spans both files: A(2) + B(1) = 3.
            assert len(ss.all_curves) == 3


# ---------------------------------------------------------------------------
# 10. Empty session resets to the welcome-screen state.
# ---------------------------------------------------------------------------


class TestEmptyReset:
    def test_no_files_resets_everything(self):
        ss = _state({})
        with patch.object(st, "session_state", ss):
            curve_registry.rebuild_registry()
            assert ss.data is None
            assert ss.analyzer is None
            assert ss.s_curve_analyzer is None
            assert ss.loader is None
            assert ss.current_file is None
            assert ss.current_curve_index == 0
            assert ss.global_curve_index == 0
            assert ss.all_curves == []


# ---------------------------------------------------------------------------
# 11. _shared._selection_key() hardened with a per-curve data signature.
# ---------------------------------------------------------------------------


class TestSelectionKeySignature:
    def test_key_changes_when_boundaries_change_at_fixed_index(self):
        ld = _mk_loader([_mk_curve(0, 100)])
        ss = _state({"f.csv": _file_entry(ld)})
        ss["current_file"] = "f.csv"
        ss["loader"] = ld
        ss["current_curve_index"] = 0
        with patch.object(st, "session_state", ss):
            k1 = _shared._selection_key()
            # Same index, but the boundary/sample count changed.
            ld.all_curves = [_mk_curve(20, 60)]
            k2 = _shared._selection_key()
        assert k1 != k2, "fixed-index boundary edit must bust the derived caches"

    def test_key_degrades_gracefully_with_mock_loader(self):
        # Backward-compat: a MagicMock loader (as older tab tests use) must not
        # crash and must reduce to the legacy (file, index, product) tuple.
        ss = _DictState()
        ss["current_file"] = "f.csv"
        ss["current_curve_index"] = 0
        ss["product_type"] = "white_pan"
        ss["loader"] = MagicMock()
        with patch.object(st, "session_state", ss):
            key = _shared._selection_key()
        assert key[:3] == ("f.csv", 0, "white_pan")


# ---------------------------------------------------------------------------
# 12. Structural DRY lock — analyzer construction lives in ONE place.
# ---------------------------------------------------------------------------


class TestDryStructuralLock:
    def test_sidebar_does_not_construct_analyzers_directly(self):
        """The sidebar must route all analyzer construction through the registry.

        This is what structurally erased the old file-removal bug that built
        ThermalAnalyzer(data, metadata) WITHOUT the loader arg. If a future edit
        re-introduces a direct constructor call in the sidebar, this fails.
        """
        src = (PROJECT_ROOT / "sidebar.py").read_text(encoding="utf-8")
        assert "ThermalAnalyzer(" not in src
        assert "SCurveAnalyzer(" not in src

    def test_registry_always_passes_loader_to_analyzers(self):
        """Every analyzer the registry builds carries the loader (guards the
        loader=None degradation of sensor-role resolution)."""
        ld = _mk_loader([_mk_curve(0, 100)])
        ss = _state({"f.csv": _file_entry(ld)})
        with patch.object(st, "session_state", ss):
            curve_registry.select_curve("f.csv", 0)
            assert ss.analyzer.loader is ld
            assert ss.s_curve_analyzer.loader is ld


# ---------------------------------------------------------------------------
# 13. Import hygiene — curve_registry must NOT reach up into the tabs layer.
# ---------------------------------------------------------------------------


class TestImportHygiene:
    """Regressions for the Streamlit Cloud cold-start ImportError.

    curve_registry lives in src/ui and is imported during app startup (via
    sidebar). Importing the tabs layer from here forces tabs (+ its heavy
    transitive imports) to initialise mid-startup — which failed on Cloud with
    `ImportError: cannot import name 'invalidate_derived_caches' from
    'tabs._shared'`. These lock the dependency direction and the cold start.
    """

    def test_curve_registry_source_does_not_import_tabs(self):
        src = (PROJECT_ROOT / "src" / "ui" / "curve_registry.py").read_text(
            encoding="utf-8"
        )
        # Ignore prose in docstrings/comments; only guard real import statements.
        import_lines = [
            ln.strip()
            for ln in src.splitlines()
            if ln.strip().startswith(("import ", "from "))
        ]
        offenders = [ln for ln in import_lines if "tabs" in ln]
        assert not offenders, f"curve_registry must not import tabs: {offenders}"

    def test_importing_curve_registry_does_not_load_tabs(self):
        # Fresh interpreter: importing curve_registry must not pull in the tabs
        # package (the exact cold-start failure path on Streamlit Cloud).
        code = (
            "import sys; from src.ui import curve_registry; "
            "print(any(m == 'tabs' or m.startswith('tabs.') for m in sys.modules))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        assert result.stdout.strip() == "False", result.stdout

    def test_shared_cache_keys_stay_in_sync(self):
        # curve_registry duplicates the _shared cache key strings (to avoid the
        # import); this locks them together so they cannot silently drift.
        assert curve_registry._SHARED_DERIVED_CACHE_KEYS == (
            _shared._S_CURVE_REPORT_CACHE,
            _shared._ZONE_ANALYZER_CACHE,
        )

    def test_invalidate_pops_both_shared_caches(self):
        ss = _DictState()
        ss[_shared._S_CURVE_REPORT_CACHE] = ("k", "stale-report")
        ss[_shared._ZONE_ANALYZER_CACHE] = ("k", "stale-zone")
        with patch.object(st, "session_state", ss):
            curve_registry._invalidate_derived_caches()
        assert _shared._S_CURVE_REPORT_CACHE not in ss
        assert _shared._ZONE_ANALYZER_CACHE not in ss

    def test_app_module_imports_clean_in_fresh_interpreter(self):
        # The definitive cold-start regression: a fresh `import app` (as Streamlit
        # Cloud does on first page load) must not raise. app.py runs module-level
        # Streamlit calls in bare mode (warnings only), so a clean import exits 0.
        result = subprocess.run(
            [sys.executable, "-c", "import app"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, result.stderr[-3000:]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
