# FloodLab v0.4 — land-only Piura flood reconstruction

Open the default **FLOOD EVENT** page and click **ANALYSE FLOOD EVENT**. Switch **Before / During / Flood footprint**. The Piura reference case reuses real processed Sentinel-1 data; no new login or jobs are required. Outputs are experimental, not validated flood extent.

See the [v0.4 scientific assessment](docs/V04_SCIENTIFIC_ASSESSMENT.md), [validation checkpoint](docs/STATUS.md) and preserved [v0.3 assessment](docs/PIURA_2017_EVENT.md). The current estimate is **1,921.24 ha**, with **229 ha of offshore v0.3 candidates removed**. Historical water, limited Sentinel-2 evidence, rivers, terrain and gauge discovery are auditable. Use **Download complete analysis** for the GIS/provenance ZIP. Technical details are under **Advanced / Scientific Details**. Previous catalogue and processing tools remain available in Flood History / Flood Lab.

# FloodLab v0.2

Earth-observation flood investigation with a global AOI workflow and a Piura 2017 demo. The v0.1 foundation remains intact; v0.2 adds the first CDSE openEO backscatter processing implementation. **The Piura pair has completed authenticated processing with numeric QC PASS and unresolved exact source-lineage warnings. The experimental flood footprint remains scientifically unvalidated.**

## Install and run

Python 3.11+; use a source checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts/bootstrap.py
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
```

On Linux/macOS use `.venv/bin/python`. Codespaces configuration forwards port 8501. Runtime directories and credentials are ignored by Git.

## First processing journey

1. In **Flood History**, load the Piura demo AOI or draw/upload another WGS84 polygon; search the catalogue.
2. Open **Flood Lab**. Select a comparable earlier/later pair and review matching relative orbit, direction, mode, requested polarization and common footprint coverage. Independent flood timing is not established by these checks.
3. Click **Prepare openEO pair plan**. The UI shows the exact terminal command for the saved plan.
4. Run that command in a terminal from the repository root. Open the CDSE verification URL printed by the client, enter the device code on the CDSE page and sign in there. **Never enter passwords or tokens into FloodLab.**
5. After login, the command submits/resumes two processing jobs. These may consume CDSE processing credits. Keep the terminal open. Tokens are memory-only; refresh-token storage is explicitly disabled.
6. Click **Refresh processing state** in Flood Lab. Successful downloads show matched-scale backscatter previews, native/aligned raster QC and downloadable provenance. They are not flood maps.

Processing states are NOT AUTHENTICATED, READY, PROCESSING, PROCESSED, QC PASS, QC WARNING and FAILED. These operational states are separate from DRAFT/PASS/FROZEN audit designations. The backend audit status stays **DRAFT** until authenticated processing succeeds.

## Public checks without authentication or processing credits

```powershell
.\.venv\Scripts\python.exe scripts/check_openeo.py
.\.venv\Scripts\python.exe scripts/check_openeo.py --prepare-demo
```

The second command also queries real Piura catalogue data, prepares the configured demo pair and checks its graphs with the public validation endpoint. It does not authenticate or submit jobs. The selected pair is a configurable temporal hypothesis, not a finding that its earlier date was dry or later date flooded.

## Processing convention and limitations

The backend requests `SENTINEL1_GRD` with explicit `sar_backscatter(coefficient="sigma0-ellipsoid", elevation_model="COPERNICUS_30", noise_removal=True)`. Results are linear power. This configures CDSE's collection processing once; FloodLab does not independently recalibrate the output. It does not claim gamma0 terrain flattening. A 20 m UTM grid and bilinear resampling are explicit. Native outputs remain cached; differing returned grids trigger a recorded later-to-earlier bilinear alignment before comparison. No change classification is run in v0.2.

Public collection metadata does not advertise relative-orbit filtering. FloodLab rejects mixed relative orbits in pair selection, then requests a one-second acquisition-start interval plus advertised direction/mode filters. This narrows processing but **does not pin or prove the exact source product**. Expected STAC IDs and any recoverable backend source IDs are recorded separately; this remains a QC warning pending lineage review. The worker refuses unexpected multiple TIFF results rather than guessing a scene/mosaic.

Nodata masks and nonfinite/nonpositive values are excluded. CDSE documents an ambiguity between zero after thermal-noise removal and zero nodata; zero is conservatively invalid here. QC checks dimensions, CRS, resolution, valid/nodata fractions, extrema, sampled robust percentiles, nonfinite values, footprint overlap and common valid coverage. These are engineering checks, not calibrated scientific confidence.

Authentication expiry or local timeout does not silently create replacement jobs. Saved job IDs allow a new device login and resume using the same command. Remote failed/canceled jobs require inspection in CDSE and, if appropriate, a new plan. A hard-killed worker may leave `worker.lock`; confirm no worker is running before removing that single stale lock. Raw remote exception text and signed result URLs are not stored in status/provenance.

## Architecture and configuration

`eo_core` provides AOIs, STAC, pair selection, openEO, job state and raster QC. `hazards/flood` retains experimental analysis-ready-array algorithms. `history` retains generic candidate grouping. Watch and Impact are shells; exposure intersection and losses are not implemented. Landslide and InSAR are not implemented.

Edit `config/piura2017.toml` for STAC/openEO endpoints, dates, bands, coefficient/DEM, resolution, coverage thresholds, polling and demo date preferences. The openEO cache must stay under ignored `data/cache` or `outputs`. AOIs crossing the dateline must be split; automatic UTM processing currently supports centroid latitudes -80° to 84°, and projection suitability still requires review.

Piura's polygon is **PIURA 2017 DEMO AOI — NOT AUTHORITATIVE FLOOD EXTENT**. It represents a search region, never observed inundation.

## Tests and status

```shell
python scripts/bootstrap.py
python -m pytest -q
python -m ruff check src app scripts tests
python -m compileall -q src app scripts
```

Tests mock remote processing and use synthetic rasters; no automated test consumes processing credits. See [status and exact handoff](docs/STATUS.md), [architecture](docs/ARCHITECTURE.md), [methodology](docs/METHODOLOGY.md), and [decisions](docs/DECISIONS.md). Prior v0.1 acceptance is preserved in [the checkpoint report](docs/STATUS_v0.1.md).

Next milestone after real backscatter acceptance: apply and validate flood detection using independent dated evidence. Roadmap remains v0.x Flood, v1 Landslide, v2 InSAR deformation.


## Diagnose an unsuccessful remote job

Run the same saved-plan command with `--diagnose` appended. Complete device login; this mode only reads the saved jobs' status and redacted error logs, and does not start/resubmit jobs or change their state. The report is saved beside the plan as `job-errors.json`. Repeating a normal run with a failed saved job ID does not create a replacement. Inspect the error before preparing a corrected plan.


Resource settings can be specified under `[openeo.job_options]` using CDSE's documented memory/worker options. Saved plans retain their own settings: editing TOML does not mutate existing jobs. Use a separate resource-retry plan to preserve failed-job evidence. Resource changes do not change SAR calibration, AOI, dates or the soft-error acceptance threshold. Higher memory is not proof of successful execution and can change processing cost.
