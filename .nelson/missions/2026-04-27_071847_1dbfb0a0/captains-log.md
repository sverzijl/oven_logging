# Captain's Log — M1b HMS Pelican

**Flotilla:** `refactor/role-classification-unified`
**Mission:** M1b — ambient annotations + 4 synthetic fixtures + failing classifier test
**Branch:** `refactor/role-classification-unified` (off main)
**Mission dir:** `.nelson/missions/2026-04-27_071847_1dbfb0a0`
**Status:** COMPLETE — outcome achieved.

## Outcome

Ambient sensor annotations on all 5 real-CSV cases. 4 synthetic fixtures (`shallow_insertion`, `full_immersion`, `lid_touch`, `probe_pull_mid_bake`) with full T1..T8 columns and `expected_x_dough_air_normalised`. Three new test classes in `tests/test_role_classifier_unified.py`: `TestAmbientAnnotationPresent` (5/5 pass), `TestSyntheticAnnotations` (4/4 pass), `TestClassifierReturnsExpectedRoles` (9/9 fail with `ModuleNotFoundError: No module named 'src.data.spatial_reconstruction'` — the M2a contract).

## Decisions

1. **Lidded ambient picks reflect physical reality, not canonical topology.** Both lidded fixtures use through-loaf insertion where T1 (probe tip) is also in air. `wonder_white_10k_lidded` ambient = `["T1","T8"]` (canonical alternate `["T8"]`); `post_wonder_meal_lidded` ambient = `["T1"]` (canonical alternate `[]`). Each carries `topology_note` and `ambiguous=True` so M2a's spatial reconstructor can branch on through-loaf geometry rather than silently violating the topology constraint.

2. **Synthetic boundary expectations tracked detector behaviour, not idealised cuts.** The boundary detector's start uses `max(T1..T8)` so it fires earlier than VCT-based starts; the probe-pull synthetic uses a -3 °C/sample drop which is sub-threshold for the cliff candidate, so the detector runs to EOF. Annotated as such with explanation in each `description`. No new failures in `tests/test_curve_boundary_detection.py` (33/33 still pass).

3. **`probe_pull_idx` field added to the probe-pull synthetic** so M4's perturbation harness can locate the contamination start without re-deriving it.

4. **TDD red-green flow** confirmed: tests written first, observed 14 failures (9 intentional + 5 ambient), then fixtures added in two passes (ambient first, synthetics second), each watching the corresponding tests flip green.

## Test counts

| Suite | Result |
|---|---|
| `TestSurfaceAnnotationPresent` | 5/5 pass (unchanged from M1a) |
| `TestLidAnnotationPresent` | 2/2 pass (unchanged from M1a) |
| `TestAmbientAnnotationPresent` | **5/5 pass (new)** |
| `TestSyntheticAnnotations` | **4/4 pass (new)** |
| `TestClassifierReturnsExpectedRoles` | **9/9 fail (M2a contract — by design)** |
| `tests/test_curve_boundary_detection.py` | 33/33 pass (no detector regression) |
| Full `tests/` suite | 429 pass, 16 fail, 2 skipped — 9 intentional contract failures + 7 pre-existing (`test_zone_color_consistency`, `test_realistic_baking_profile`, `test_shallow_insertion`, four `test_visualization.*`). `test_deep_insertion` flake passed in this ordering. |

## Diffs / artefacts

- `tests/fixtures/curve_boundary_cases.py`: +462 lines (4 new `_build_*` builders, 4 new CASES entries, ambient annotations on 5 real cases, topology_notes on 2 lidded cases).
- `tests/test_role_classifier_unified.py`: +196 lines (3 new test classes; existing classes unchanged).
- `.nelson/missions/2026-04-27_071847_1dbfb0a0/`: nelson mission scaffold (sailing-orders, battle-plan, plan-input, captain's log).

## Open risks / follow-ups

- **Lidded ambient ambiguity.** The `["T1","T8"]` vs `["T8"]` choice on `wonder_white_10k_lidded` (and `["T1"]` vs `[]` on `post_wonder_meal_lidded`) is an empirical call that the M2a classifier should resolve. If M2a returns `["T8"]` for wonder_white we should not flag a regression — the topology_note authorises both. M4 perturbation harness should report per-pick stability separately for these cases.

- **Synthetic full_immersion graceful degradation.** `expected_surface_sensor=None` and `expected_ambient_sensors=[]` test the classifier's behaviour when no air region is visible. M2a needs a `surface=None`/`ambient=[]` code path that returns a `SpatialAssignment` with explicit `None` values rather than crashing or fabricating a surface pick.

- **Pre-existing 7-8 pytest failures remain.** Tracked separately as flotilla follow-up (j); not in M1b scope.

## Mentioned in Despatches

- **HMS Pelican** — clean execution under TDD discipline. Caught the through-loaf insertion topology break on lidded cases and chose the physics-honest annotation with documented rationale rather than picking the convenient canonical answer. Synthetic builders mirror existing `_build_*` style; no boilerplate duplication.

## Reusable patterns

- **Adopt:** `topology_note` + `ambiguous=True` flags for fixtures where the standard topology constraint genuinely doesn't apply. The fixture documents the geometry in code rather than implicitly hoping the classifier handles it.
- **Adopt:** Importing the missing M2a module *inside the test body* so each parametrized case fails individually with the same clean ImportError. Cleaner per-case progress bar than collection-time failure.
- **Adopt:** Setting synthetic boundary expectations to detector outputs rather than time-domain idealisations. The synthetic fixtures still test what they need to test (sensor role assignment) without coupling to detector internals.
- **Avoid:** Don't refactor existing `_build_*` builders to share code at this scale; the duplication between builders is per-fixture intentional shaping, not accidental.

## Mission paid off

Ship idle, work verified on disk, 16 schema tests pass, 9 contract tests fail per design, no detector regression, captain's log written. Mission ready to stand down.
