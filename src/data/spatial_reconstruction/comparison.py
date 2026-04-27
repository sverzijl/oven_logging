"""Empirical comparison harness for piecewise vs Stefan spatial models.

This module powers the empirical default-model decision — which model goes
into ``ROLE_CLASSIFIER_CONFIG['DEFAULT_MODEL']`` is determined by the
:func:`benchmark_fixture` results aggregated across all 9 contract fixtures
plus per-role agreement with the M1a/M1b annotations.

Public API:
- :class:`ModelComparison` — per-fixture scoreboard.
- :func:`benchmark_fixture` — run both models on one fixture.
- :func:`benchmark_all_cases` — sweep over all role-classification fixtures.
- :func:`write_comparison_report` — emit the Markdown report at
  ``tests/baselines/spatial_model_comparison.md``.

The report is committed and reviewed during M2b stand-down; it is also the
artefact that justifies any future change to the default model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# ModelComparison dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelComparison:
    """Side-by-side comparison of piecewise and Stefan fits on one fixture.

    All ``*_position_error`` fields are absolute differences in normalised
    [0, 1] coordinates; ``None`` when the fixture has no ground-truth
    position annotation (real CSVs that lack ``expected_x_dough_air_normalised``).
    """

    fixture_name: str
    piecewise_residual_sse: float
    stefan_residual_sse: float
    piecewise_x_dough_air: Any  # float | tuple | None
    stefan_x_dough_air: Any
    ground_truth_x_dough_air: Any
    piecewise_position_error: Optional[float]
    stefan_position_error: Optional[float]
    piecewise_compute_ms: float
    stefan_compute_ms: float
    piecewise_role_match: dict
    stefan_role_match: dict
    notes: str = ""
    extras: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-fixture benchmark
# ---------------------------------------------------------------------------


def _position_error(
    predicted: Any, ground_truth: Any
) -> Optional[float]:
    """Return absolute position error in normalised coords.

    Returns ``None`` when either side is missing; for tuples (through-loaf),
    error is the mean absolute distance between matched fronts. When the
    ground truth is a scalar but the prediction is a tuple, we use the
    nearer of the two predicted fronts.
    """
    if ground_truth is None or predicted is None:
        return None
    if isinstance(ground_truth, tuple) and isinstance(predicted, tuple):
        # Match endpoints by sort order.
        gs = sorted(ground_truth)
        ps = sorted(predicted)
        return float(np.mean([abs(p - g) for p, g in zip(ps, gs)]))
    if isinstance(ground_truth, tuple):
        gs = sorted(ground_truth)
        return float(min(abs(predicted - g) for g in gs))
    if isinstance(predicted, tuple):
        ps = sorted(predicted)
        return float(min(abs(p - ground_truth) for p in ps))
    return float(abs(predicted - ground_truth))


def _role_match(result, expected: dict) -> dict:
    """Compare classify result against the fixture's expected_* annotations."""
    expected_core = expected.get("expected_core_sensor")
    if isinstance(expected_core, list):
        # Multi-curve case — fold to first-curve annotation.
        expected_core = expected_core[0] if expected_core else None

    expected_surface = expected.get("expected_surface_sensor")
    if isinstance(expected_surface, list):
        expected_surface = expected_surface[0] if expected_surface else None

    expected_ambient = expected.get("expected_ambient_sensors", []) or []
    if expected_ambient and isinstance(expected_ambient[0], list):
        # Multi-curve nested list — take first.
        expected_ambient = expected_ambient[0]

    expected_lid = expected.get("expected_lid_sensor")

    def _ok(actual, want) -> bool:
        if want is None:
            return actual is None
        return actual == want

    return {
        "core": _ok(result.core, expected_core),
        "surface": _ok(result.surface, expected_surface),
        "ambient": sorted(result.ambient) == sorted(expected_ambient),
        "lid": _ok(result.lid, expected_lid),
    }


def _segment_for_classify(case: dict) -> pd.DataFrame:
    """Pull the per-curve slice the contract test uses.

    For multi-curve cases (real_1000BA3C_1759), returns the *first* curve
    slice so the comparison harness has a single bake to score. The contract
    test runs all curves separately; here we report on curve-0 only.
    """
    df = case["df"]
    n_curves = case.get("expected_n_curves", 1)
    if n_curves <= 1:
        return df
    try:
        from src.data.curve_boundary_detector import CurveBoundaryDetector
        from config.constants import CURVE_DETECTION_CONFIG

        detector = CurveBoundaryDetector(CURVE_DETECTION_CONFIG)
        curves = detector.extract_curves(
            df, expected_durations_s=case.get("expected_durations_s")
        )
        if not curves:
            return df
        c0 = curves[0]
        if "data" in c0 and isinstance(c0["data"], pd.DataFrame):
            return c0["data"]
        return df.iloc[c0["start_idx"]:c0["end_idx"] + 1].reset_index(drop=True)
    except Exception:
        return df


def benchmark_fixture(case: dict) -> ModelComparison:
    """Run both spatial models on a single fixture and return a comparison."""
    from src.data.spatial_reconstruction.classifier import classify

    df = _segment_for_classify(case)
    name = case["name"]

    t0 = time.perf_counter()
    pw = classify(df, sample_period_ms=5000, model="piecewise")
    t_pw = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    sf = classify(df, sample_period_ms=5000, model="stefan")
    t_sf = (time.perf_counter() - t0) * 1000.0

    pw_sse = float(pw.profile_fit.fit_quality.get("residual_sse", 0.0))
    sf_sse = float(sf.profile_fit.fit_quality.get("residual_sse", 0.0))
    pw_x = pw.profile_fit.x_dough_air
    sf_x = sf.profile_fit.x_dough_air
    gt_x = case.get("expected_x_dough_air_normalised")

    pw_err = _position_error(pw_x, gt_x)
    sf_err = _position_error(sf_x, gt_x)

    pw_match = _role_match(pw, case)
    sf_match = _role_match(sf, case)

    notes = ""
    if name == "post_wonder_meal_lidded":
        notes = (
            f"piecewise.surface={pw.surface}, stefan.surface={sf.surface}, "
            f"expected={case.get('expected_surface_sensor')}"
        )

    extras = {
        "stefan_alpha_crust": sf.profile_fit.fit_quality.get("alpha_crust"),
        "stefan_T_cavity": sf.profile_fit.fit_quality.get("T_cavity"),
        "stefan_n_crossings_100c": sf.profile_fit.fit_quality.get("n_crossings_100c"),
        "piecewise_surface": pw.surface,
        "stefan_surface": sf.surface,
        "piecewise_core": pw.core,
        "stefan_core": sf.core,
        "piecewise_lid": pw.lid,
        "stefan_lid": sf.lid,
    }
    return ModelComparison(
        fixture_name=name,
        piecewise_residual_sse=pw_sse,
        stefan_residual_sse=sf_sse,
        piecewise_x_dough_air=pw_x,
        stefan_x_dough_air=sf_x,
        ground_truth_x_dough_air=gt_x,
        piecewise_position_error=pw_err,
        stefan_position_error=sf_err,
        piecewise_compute_ms=t_pw,
        stefan_compute_ms=t_sf,
        piecewise_role_match=pw_match,
        stefan_role_match=sf_match,
        notes=notes,
        extras=extras,
    )


def benchmark_all_cases() -> list[ModelComparison]:
    """Run :func:`benchmark_fixture` over every role-annotated fixture.

    The fixture set is the 5 real cases plus 4 synthetics — exactly the
    9-case contract surface defined in M1a/M1b.
    """
    from tests.fixtures.curve_boundary_cases import CASES

    role_named = {
        "real_100098DE_1351",
        "real_1000BA3C_0946",
        "real_1000BA3C_1759",
        "wonder_white_10k_lidded",
        "post_wonder_meal_lidded",
        "synthetic_shallow_insertion",
        "synthetic_full_immersion",
        "synthetic_lid_touch",
        "synthetic_probe_pull_mid_bake",
    }
    return [benchmark_fixture(c) for c in CASES if c["name"] in role_named]


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------


def _format_pos(x: Any) -> str:
    if x is None:
        return "None"
    if isinstance(x, tuple):
        return "(" + ", ".join(f"{v:.3f}" for v in x) + ")"
    return f"{float(x):.3f}"


def _format_err(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:.3f}"


def _bool_glyph(b: bool) -> str:
    return "✓" if b else "✗"


def write_comparison_report(
    comparisons: list[ModelComparison], output_path: str
) -> None:
    """Write the per-fixture Markdown comparison report to ``output_path``."""
    n = len(comparisons)
    pw_role_totals = {"core": 0, "surface": 0, "ambient": 0, "lid": 0}
    sf_role_totals = {"core": 0, "surface": 0, "ambient": 0, "lid": 0}
    for c in comparisons:
        for k in pw_role_totals:
            if c.piecewise_role_match.get(k):
                pw_role_totals[k] += 1
            if c.stefan_role_match.get(k):
                sf_role_totals[k] += 1

    pw_total_pass = sum(
        1 for c in comparisons if all(c.piecewise_role_match.values())
    )
    sf_total_pass = sum(
        1 for c in comparisons if all(c.stefan_role_match.values())
    )

    pw_mean_err = np.mean(
        [c.piecewise_position_error for c in comparisons
         if c.piecewise_position_error is not None]
    ) if any(c.piecewise_position_error is not None for c in comparisons) else float("nan")
    sf_mean_err = np.mean(
        [c.stefan_position_error for c in comparisons
         if c.stefan_position_error is not None]
    ) if any(c.stefan_position_error is not None for c in comparisons) else float("nan")
    pw_mean_sse = float(np.mean([c.piecewise_residual_sse for c in comparisons]))
    sf_mean_sse = float(np.mean([c.stefan_residual_sse for c in comparisons]))

    lines: list[str] = []
    lines.append("# Spatial-Reconstruction Model Comparison — Piecewise vs Stefan")
    lines.append("")
    lines.append(
        "Empirical comparison powering the default-model decision for "
        "`src/data/spatial_reconstruction/`. Both models read the same "
        "feature dict (DRY contract); they diverge only in how they "
        "reconstruct T(x) from the per-sensor terminal vector."
    )
    lines.append("")
    lines.append("**Models compared**")
    lines.append("")
    lines.append("- **Piecewise** (M2a HMS Indefatigable) — three independent regions:")
    lines.append(
        "  dough plateau, air rise (free slope), optional lid plateau. The "
        "dough/air interface is the largest adjacent ΔT exceeding "
        "`MONOTONIC_GRADIENT_MIN_JUMP_C`. Plateau temperature is free."
    )
    lines.append("- **Stefan** (M2b HMS Vanguard) — physics-constrained:")
    lines.append(
        "  dough/air interface pinned at exactly T = 100 °C (latent-heat "
        "evaporation front); air-side rise governed by one global thermal-"
        "diffusivity coupling parameter `α`. The model is "
        "`T(x) = 100 + (T_cavity − 100)(1 − exp(−α(x − x_front)))`."
    )
    lines.append("")
    lines.append(f"**Fixture set**: {n} cases — 5 real CSVs + 4 synthetics.")
    lines.append("")

    lines.append("## Per-fixture results")
    lines.append("")
    lines.append(
        "| Fixture | Piecewise SSE | Stefan SSE | Piecewise x | Stefan x | "
        "Ground truth x | Piecewise err | Stefan err | "
        "Piecewise role pass (c/s/a/l) | Stefan role pass (c/s/a/l) |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|"
    )
    for c in comparisons:
        pw_glyphs = "/".join(
            _bool_glyph(c.piecewise_role_match.get(k, False))
            for k in ("core", "surface", "ambient", "lid")
        )
        sf_glyphs = "/".join(
            _bool_glyph(c.stefan_role_match.get(k, False))
            for k in ("core", "surface", "ambient", "lid")
        )
        lines.append(
            f"| `{c.fixture_name}` | {c.piecewise_residual_sse:.2f} | "
            f"{c.stefan_residual_sse:.2f} | {_format_pos(c.piecewise_x_dough_air)} | "
            f"{_format_pos(c.stefan_x_dough_air)} | "
            f"{_format_pos(c.ground_truth_x_dough_air)} | "
            f"{_format_err(c.piecewise_position_error)} | "
            f"{_format_err(c.stefan_position_error)} | "
            f"{pw_glyphs} | {sf_glyphs} |"
        )
    lines.append("")

    # Surface picks side-by-side (the most informative single column for
    # diagnosing disagreement).
    lines.append("## Surface-pick side-by-side")
    lines.append("")
    lines.append("| Fixture | Piecewise.surface | Stefan.surface | Expected |")
    lines.append("|---|:---:|:---:|:---:|")
    for c in comparisons:
        lines.append(
            f"| `{c.fixture_name}` | {c.extras.get('piecewise_surface')} | "
            f"{c.extras.get('stefan_surface')} | "
            f"{_role_expected_surface_for_report(c)} |"
        )
    lines.append("")

    # Compute-time table.
    lines.append("## Compute time")
    lines.append("")
    lines.append("| Fixture | Piecewise (ms) | Stefan (ms) |")
    lines.append("|---|---:|---:|")
    for c in comparisons:
        lines.append(
            f"| `{c.fixture_name}` | {c.piecewise_compute_ms:.1f} | "
            f"{c.stefan_compute_ms:.1f} |"
        )
    lines.append("")

    # Stefan diagnostic — α, T_cavity per fixture.
    lines.append("## Stefan diagnostic")
    lines.append("")
    lines.append("| Fixture | T_cavity | α (1/x) | n 100°C crossings |")
    lines.append("|---|---:|---:|---:|")
    for c in comparisons:
        T_cav = c.extras.get("stefan_T_cavity")
        alpha = c.extras.get("stefan_alpha_crust")
        nc = c.extras.get("stefan_n_crossings_100c")
        T_cav_s = "—" if T_cav is None else f"{T_cav:.1f}"
        alpha_s = "—" if alpha is None else f"{alpha:.2f}"
        lines.append(
            f"| `{c.fixture_name}` | {T_cav_s} | {alpha_s} | {nc} |"
        )
    lines.append("")

    # Aggregates.
    lines.append("## Aggregate metrics")
    lines.append("")
    lines.append(
        f"- **Total fixtures passing all 4 roles**: piecewise {pw_total_pass}/{n}, "
        f"stefan {sf_total_pass}/{n}."
    )
    lines.append("")
    lines.append("| Role | Piecewise pass | Stefan pass |")
    lines.append("|---|---:|---:|")
    for k in ("core", "surface", "ambient", "lid"):
        lines.append(f"| {k} | {pw_role_totals[k]}/{n} | {sf_role_totals[k]}/{n} |")
    lines.append("")
    lines.append(
        f"- **Mean residual SSE** (lower = better fit): "
        f"piecewise {pw_mean_sse:.2f}, stefan {sf_mean_sse:.2f}."
    )
    if not np.isnan(pw_mean_err) or not np.isnan(sf_mean_err):
        lines.append(
            f"- **Mean position error** (only on synthetics with ground-truth): "
            f"piecewise {pw_mean_err:.3f}, stefan {sf_mean_err:.3f}."
        )
    lines.append("")

    # Specific scrutiny on post_wonder_meal_lidded.
    target = next(
        (c for c in comparisons if c.fixture_name == "post_wonder_meal_lidded"),
        None,
    )
    lines.append("## Spotlight: `post_wonder_meal_lidded` (the 1 piecewise-failing fixture)")
    lines.append("")
    if target is None:
        lines.append("_Fixture not present in this run._")
    else:
        lines.append(
            f"- Expected surface: **{_role_expected_surface_for_report(target)}** "
            f"(M1a/M1b annotation: first sensor on the air side past dough)."
        )
        lines.append(f"- Piecewise.surface: **{target.extras.get('piecewise_surface')}**")
        lines.append(f"- Stefan.surface: **{target.extras.get('stefan_surface')}**")
        lines.append("")
        if target.stefan_role_match.get("surface") and not target.piecewise_role_match.get("surface"):
            lines.append(
                "- **Stefan resolves the disagreement.** Pinning the dough/air "
                "front at exactly 100 °C and using the heat-up-speed split for "
                "lid-bake mode places the front past the dough cluster on the "
                "air side, which selects the air-side neighbour as surface."
            )
        elif target.piecewise_role_match.get("surface") and not target.stefan_role_match.get("surface"):
            lines.append(
                "- **Stefan also fails this fixture.** The all-plateau lid-bake "
                "regime hides the front: every sensor's terminal is in the "
                "100 °C band, so the Stefan-front crossing is degenerate and "
                "the model falls back to the same heat-up-speed split that "
                "piecewise uses. Resolving this fixture requires an additional "
                "feature (likely cool-rate or oven-proxy phase) — deferred to M4."
            )
        else:
            lines.append(
                "- **Both models agree on this fixture** (either both pass or "
                "both fail). The choice of model has no leverage here; the "
                "annotation convention in M1a's Truculent is the disagreement axis."
            )
    lines.append("")

    # Recommendation.
    lines.append("## Recommendation")
    lines.append("")
    if sf_total_pass > pw_total_pass:
        winner = "stefan"
        rationale = (
            f"Stefan passes {sf_total_pass}/{n} fixtures vs piecewise's "
            f"{pw_total_pass}/{n}. The 100°C pin removes a degree of freedom "
            "the piecewise model spends on free-plateau-T."
        )
    elif pw_total_pass > sf_total_pass:
        winner = "piecewise"
        rationale = (
            f"Piecewise passes {pw_total_pass}/{n} fixtures vs Stefan's "
            f"{sf_total_pass}/{n}. The Stefan model's stricter 100°C pin "
            "rejects fixtures where the latent-heat plateau sits 1-2°C below "
            "100 °C (real-CSV calibration noise)."
        )
    else:
        # Tie on overall pass-count — break by SSE then compute speed.
        if sf_mean_sse < pw_mean_sse:
            winner = "stefan"
            rationale = (
                f"Tied at {pw_total_pass}/{n} on overall role-pass count; "
                f"Stefan has lower mean residual SSE "
                f"({sf_mean_sse:.2f} vs {pw_mean_sse:.2f}) — fewer free "
                "parameters delivers tighter fits."
            )
        elif pw_mean_sse < sf_mean_sse:
            winner = "piecewise"
            rationale = (
                f"Tied at {pw_total_pass}/{n} on overall role-pass count; "
                f"piecewise has lower mean residual SSE "
                f"({pw_mean_sse:.2f} vs {sf_mean_sse:.2f}) — independent "
                "region slopes capture per-bake variation better than the "
                "single-α Stefan fit."
            )
        else:
            winner = "piecewise"
            rationale = (
                f"Tied on both role-pass count ({pw_total_pass}/{n}) and SSE. "
                "Piecewise is the incumbent (M2a, already wired), so we keep "
                "it as the default and revisit when M4's perturbation harness "
                "produces a tie-breaker."
            )
    lines.append(f"**Default model**: `{winner}`")
    lines.append("")
    lines.append(rationale)
    lines.append("")
    lines.append(
        "This recommendation is mirrored at "
        "`config.constants.ROLE_CLASSIFIER_CONFIG['DEFAULT_MODEL']` and is "
        "the value the loader (M3a) should pass through to `classify(...)`."
    )
    lines.append("")
    lines.append("## Open follow-ups")
    lines.append("")
    lines.append(
        "- **M4 perturbation harness**: re-run this comparison under bootstrap "
        "resampling of the input curves to score *stability* of position "
        "estimates as well as accuracy. The Stefan model's reduced parameter "
        "count should show up as lower position-error variance even when "
        "mean accuracy is comparable."
    )
    lines.append(
        "- **Lid-bake disambiguation**: if the spotlight fixture above is not "
        "resolved by either model, M4 should add `xcorr_lag_to_oven_proxy_seconds` "
        "and a cool-rate feature to the lid-bake split — this is the smallest "
        "remaining gap in the contract surface."
    )
    lines.append("")

    text = "\n".join(lines) + "\n"
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _role_expected_surface_for_report(c: ModelComparison) -> str:
    """Recover the fixture's expected_surface_sensor for the report (small
    convenience because the dataclass doesn't carry it directly)."""
    try:
        from tests.fixtures.curve_boundary_cases import CASES
        case = next(cs for cs in CASES if cs["name"] == c.fixture_name)
        s = case.get("expected_surface_sensor")
        if isinstance(s, list):
            s = s[0] if s else None
        return str(s)
    except Exception:
        return "?"
