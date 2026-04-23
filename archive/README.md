# archive/

Historical investigation artifacts preserved for forensics. Nothing here is
imported by the live app or the test suite; these files are retained so the
development history (how certain bugs were diagnosed, which hypotheses were
explored, what planning docs preceded the current design) remains inspectable.

## Contents

- `scripts/` — ad-hoc `analyze_*.py`, `debug_*.py`, `check_*.py`, and
  root-level `test_*.py` one-off scripts that were used to probe specific
  issues during development. The canonical pytest suite lives in `tests/`.
- `docs/` — superseded `*_PLAN.md`, `*_SUMMARY.md`, `*_ANALYSIS.md`,
  `*_DESIGN.md`, and related planning/critique/report docs. The current
  refactoring spec is `REFACTORING_ANALYSIS.md` at the repo root; current
  code-review reference is `CODE_REVIEW_SUMMARY.md`.

Do not import from this directory. Treat everything here as read-only history.
