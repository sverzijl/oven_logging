---
name: run-oven-logging
description: >-
  Run, launch, start, serve, smoke-test or screenshot the oven_logging Thermal
  Profile Analyzer — the Streamlit app that analyses Combustion Inc. probe CSVs
  and renders the Spatial Evolution / moisture-front timeline. Use when asked to
  run the app, see a change in the UI, screenshot a tab, or validate the
  spatial-reconstruction / isothermal pipeline.
---

# Run: oven_logging (Thermal Profile Analyzer)

A Streamlit app that reads Combustion Inc. probe CSVs (8 sensors T1–T8) and
produces baking analytics, incl. the **🌡️ Spatial Evolution** tab — the
60/80/100/110 °C isotherm "moisture-front" timeline.

**Two ways to drive it, and you almost always want the first:**

1. **Headless smoke (`driver.py`)** — drives the real analysis+figure pipeline
   behind the Spatial Evolution tab without a browser, in ~2 s, and writes a
   viewable HTML chart. This is the layer nearly every change here touches. Use
   it to validate work.
2. **Real browser UI** — launch the Streamlit server and drive it with the
   `mcp__claude-in-chrome__*` tools. Only needed to *see* the actual rendered
   page. Has two non-obvious traps (file upload + scrolling) — see Gotchas.

All paths below are relative to the repo root (`oven_logging/`, the git root).
The interpreter is the project venv — on this machine it lives in the **parent**
directory, not inside `oven_logging`:

```
PY="$(cd .. && pwd)/.venv/Scripts/python.exe"   # Windows; ../.venv, NOT ./venv
```

## Prerequisites

Use the existing venv if present (above). Fresh machine:

```bash
python -m venv .venv && . .venv/Scripts/activate   # or .venv/bin/activate on Linux
pip install -r requirements.txt                     # streamlit, pandas, numpy, scipy, plotly
```

The app needs a probe CSV to do anything; real ones live at the repo root
(`ProbeData_*.csv`, `wonder white 10k 13.01.2026.csv`, `Post Wonder Meal *.csv`).

## Run (agent path — headless smoke) ← start here

```bash
PY="$(cd .. && pwd)/.venv/Scripts/python.exe"
"$PY" .claude/skills/run-oven-logging/driver.py
```

Loads a CSV → `loader.isothermal_assignment(0)` → builds the Panel B/C plotly
figures → writes `_run_spatial_evolution.html`. Prints the four isotherm-front
trajectories, the core-confidence verdict, and whether the fronts are trackable.
Exit 0 = it ran and the figures built.

Pick a different bake (first positional arg, repo-root filename or absolute path):

```bash
"$PY" .claude/skills/run-oven-logging/driver.py "wonder white 10k 13.01.2026.csv"
```

Interpreting the result — this is **probe-placement dependent**:

- **`coverage: FRONTS TRACKED`** (e.g. `ProbeData_1000BA3C_2025-05-30 09_46_16.csv`)
  — the probe spans crumb→crust→air (outer sensors reach 120–180 °C), so the
  100 °C moisture front advances through the probe (≈0.99 → 0.59). Panel B shows
  four moving curves. This is the case to demo.
- **`coverage: DEGENERATE`** (e.g. the Wonder bakes) — the probe is fully inside
  the crumb (all sensors ≈98 °C, none reach 100 °C), so the moisture front is at
  the crust, out of range. The app shows a warning banner explaining this
  instead of flat lines. Still exit 0 — this is correct behaviour, not a failure.

## Run (real browser UI)

`chromium-cli` is **not** installed here; drive the page with the
`mcp__claude-in-chrome__*` tools. Launch the server headless:

```bash
PY="$(cd .. && pwd)/.venv/Scripts/python.exe"
"$PY" -m streamlit run app.py --server.port 8765 --server.headless true \
      --browser.gatherUsageStats false        # run in background; serves http://localhost:8765
```

Then, with the browser tools: `tabs_create_mcp` → `navigate` to
`http://localhost:8765`.

**Upload a CSV (the trap).** The `file_upload` tool **rejects host filesystem
paths**, and the app is a welcome screen until a CSV is uploaded. Workaround —
serve the CSV locally and inject it into the uploader from the page:

```bash
"$PY" .claude/skills/run-oven-logging/serve_csv.py 8799   # background; CORS-enabled
```

Then run this with `javascript_tool` (top-level await is unavailable — use the
async IIFE; spaces in the filename must be `%20` in the fetch URL):

```js
(async () => {
  const url = "http://localhost:8799/ProbeData_1000BA3C_2025-05-30%2009_46_16.csv";
  const buf = await (await fetch(url)).arrayBuffer();
  const file = new File([buf], "ProbeData_1000BA3C_2025-05-30 09_46_16.csv", { type: "text/csv" });
  const input = document.querySelector('input[type="file"]');
  const dt = new DataTransfer(); dt.items.add(file);
  input.files = dt.files;
  input.dispatchEvent(new Event("change", { bubbles: true }));
  return "injected " + input.files[0].name + " (" + input.files[0].size + " bytes)";
})();
```

Streamlit reruns and the tabs appear. `left_click` the "🌡️ Spatial Evolution"
tab. **Scrolling (the second trap):** the mouse wheel and window scroll do
nothing — the content scrolls inside `section[data-testid="stMain"]`. Scroll it
with `javascript_tool`, then `computer` screenshot:

```js
document.querySelector('section[data-testid="stMain"]').scrollBy(0, 1500);
```

## Run (human path)

```bash
"$PY" -m streamlit run app.py      # opens http://localhost:8501; Ctrl-C to stop
```

Upload a CSV in the sidebar, click the Spatial Evolution tab. (Useless headless —
that's what the agent paths above are for.)

## Test

```bash
PY="$(cd .. && pwd)/.venv/Scripts/python.exe"
"$PY" -m pytest tests/ -q            # ~7 min; baseline is fully green (0 failed, 2 skipped)
"$PY" -m pytest tests/test_spatial_evolution_tab.py tests/test_isothermal_tracker.py -q   # fast subset
```

## Gotchas

- **`file_upload` rejects host paths** — it no longer accepts host filesystem
  paths. Use `serve_csv.py` + the JS injection above. (Don't `left_click` the
  uploader — that opens a native file picker the agent can't see.)
- **Streamlit scroll** — page/window scroll and the mouse wheel don't move the
  content; scroll `section[data-testid="stMain"]` via JS (≈3120 px tall on a
  loaded page).
- **`await` in `javascript_tool`** — top-level await throws here; wrap fetch/etc.
  in `(async () => { ... })()`.
- **The venv is in `../.venv`** (parent of `oven_logging`), not `./venv`. There
  is no venv inside the repo.
- **Flat Spatial Evolution chart is data, not a bug** — a fully-immersed (in-crumb)
  probe never sees the 100 °C front; `driver.py` reports `DEGENERATE` and the app
  banners it. Use a `ProbeData_1000BA3C` bake to see moving fronts.
- **Email prompt on first `streamlit run`** — suppressed by
  `--server.headless true` (and `--browser.gatherUsageStats false`).

## Troubleshooting

- `ModuleNotFoundError` / `streamlit: command not found` → wrong interpreter; use
  `../.venv/Scripts/python.exe` (or `pip install -r requirements.txt`).
- `driver.py` prints `CSV not found` → pass a filename that exists at the repo
  root, or an absolute path.
- Browser shows only the title and a blank body → no CSV loaded yet; do the
  upload step.
- `_run_*.html` artifacts in the working tree → ignored via `.gitignore`; safe to
  delete.
