"""Pure helpers for the expected-bake-time sidebar widgets (M6 HMS Spartan).

Keep the pure logic (unit conversion, session-key construction, hint-list
assembly) out of the Streamlit integration so it can be unit-tested
without a browser.  The sidebar module imports these and wires them into
``st.session_state``.

Key invariants:
  - Widget keys are scoped by filename AND curve_number (1-indexed), NOT
    by ``current_curve_index`` — prevents widget state bleeding across
    curves when the user swaps the currently-viewed curve (precedent:
    mission 2026-04-24_102020_af6532e1).
  - Empty / zero / None minutes are ALL treated as "no hint" — the
    detector (M3) short-circuits on ``None`` entries per-curve.
  - If every per-curve slot is empty for a file, the overall hint list
    collapses to ``None`` so the loader forwards ``None`` to the
    detector, preserving byte-identical no-hint behaviour.
"""

from __future__ import annotations

from typing import Mapping


def minutes_to_seconds(value: float | None) -> float | None:
    """Convert minutes → seconds, treating 0.0 and None as "no hint"."""
    if value is None:
        return None
    if value <= 0.0:
        return None
    return float(value) * 60.0


def seconds_to_minutes(value: float | None) -> float | None:
    """Convert seconds → minutes, preserving ``None``."""
    if value is None:
        return None
    return float(value) / 60.0


def session_key_for_curve(filename: str, curve_number: int) -> str:
    """Return a stable per-file, per-curve widget/session key.

    The curve_number (1-indexed) is baked into the key instead of
    ``current_curve_index`` so that swapping the viewed curve does not
    clobber hints for other curves (Streamlit widget-state hazard
    closed by mission 2026-04-24_102020_af6532e1).
    """
    return f"expected_bake_minutes__{filename}__c{int(curve_number)}"


def build_hint_list_from_session(
    filename: str,
    n_curves: int,
    session_store: Mapping[str, float | None],
) -> list[float | None] | None:
    """Assemble a positional ``list[float | None]`` in SECONDS from the
    session store, or return ``None`` when every slot is empty.

    Args:
        filename: the current file's name; used to scope the keys.
        n_curves: number of detected curves for this file.
        session_store: dict-like mapping from widget key to minutes value
            (Streamlit's ``st.session_state`` satisfies this contract).

    Returns:
        - ``None`` when every curve slot is unset or 0.0 (→ detector
          preserves byte-identical no-hint behaviour).
        - Otherwise a list of length ``n_curves`` where each entry is
          either the hinted duration in SECONDS or ``None``.
    """
    raw_minutes: list[float | None] = []
    for curve_number in range(1, n_curves + 1):
        key = session_key_for_curve(filename, curve_number)
        raw_minutes.append(session_store.get(key))

    seconds = [minutes_to_seconds(m) for m in raw_minutes]
    if all(s is None for s in seconds):
        return None
    return seconds


__all__ = [
    "minutes_to_seconds",
    "seconds_to_minutes",
    "session_key_for_curve",
    "build_hint_list_from_session",
]
