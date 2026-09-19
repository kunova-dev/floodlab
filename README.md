# FloodLab v0.1

An Earth-observation flood investigation foundation with a global AOI workflow and a Piura / lower Piura valley 2017 demonstration search window.

## Run locally

Python 3.11 or newer is required. From this repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python scripts/bootstrap.py
python -m streamlit run app/streamlit_app.py
```

On Linux/macOS use `source .venv/bin/activate`. A Codespaces/devcontainer configuration installs dependencies and forwards port 8501. If PowerShell activation is restricted, invoke `.\.venv\Scripts\python.exe` directly.

Open Flood History → load Piura demo (or draw/upload an AOI) → choose dates → search → inspect metadata → select acquisitions → open Flood Lab → download a preparation manifest. This manifest records the source, exact search, AOI, assets, configuration and assumptions; it does not launch processing.

## Capabilities

- Hazard-neutral validated GeoJSON AOIs, inclusive UTC temporal queries, configurable STAC discovery and normalized Sentinel-1 metadata.
- Map drawing, metadata inspection, result caps, observation comparability checks and provenance manifests.
- Tested array functions for linear-power to dB conversion, water thresholds, Otsu, change detection, probable new inundation, permanent-water exclusion, component cleanup, area and QC.
- Functional median/MAD anomaly detection and temporal candidate grouping using independently supplied inundation indicators and baseline.
- Idempotent runtime bootstrap, pytest, static checks, CI and configuration.

The UI starts without catalogue access; searches show explicit failures without substituted satellite results. Base-map tiles require internet. Tests use synthetic arrays and mocked STAC responses; they are not Piura validation results.

## Boundaries

There is no raw Sentinel-1 download/preprocessing backend, validated Piura flood footprint, automatic monitoring, production event reconstruction, exposure intersection implementation, financial loss model, landslide implementation or InSAR implementation. COG/GeoTIFF storage alone does not make GRD calibrated and terrain-corrected. Local preprocessed GeoTIFF ingestion is a future backend: the current flood engine accepts arrays with externally verified grid/units.

## Architecture and configuration

`src/floodlab/eo_core` holds reusable EO services and processing contracts; `hazards/flood` holds flood algorithms; `history` groups indicators; `impact` defines a minimal future interface; `ui` presents the application. See [architecture](docs/ARCHITECTURE.md), [methodology](docs/METHODOLOGY.md), [decisions](docs/DECISIONS.md) and [audit status](docs/STATUS.md).

Edit `config/piura2017.toml` for endpoint, collection, paths, dates, thresholds, grouping and logging. Paths resolve relative to the repository containing `config/`. The app is intended to run from an editable source checkout. `scripts/bootstrap.py` creates the standard runtime folders, preserves all existing files and prints each folder's status. Configured custom directories should be created by the backend that uses them; v0.1 does not write satellite caches.

The default catalogue is `https://stac.dataspace.copernicus.eu/v1`, collection `sentinel-1-grd`, checked against [official CDSE STAC documentation](https://documentation.dataspace.copernicus.eu/APIs/STAC.html). Verify current identifiers at `/collections` or `/collections/sentinel-1-grd`; the adapter verifies the requested collection at runtime. Discovery is public; product access can require authentication and deferred retrieval. Never paste credentials into catalogue URLs or tracked configuration.

The Piura polygon is a **DEMO AOI — NOT AUTHORITATIVE FLOOD EXTENT**. It is a search rectangle, not a scientific finding. The architecture accepts global WGS84 polygons; dateline-crossing regions must be split at ±180°. No regional algorithm assumptions are embedded in the EO core.

## Verification

```shell
python scripts/bootstrap.py
python -m pytest -q
python -m ruff check .
python -m compileall -q src app scripts
```

No large satellite download is needed. Optional live probe: `python scripts/check_catalogue.py`. See `docs/STATUS.md` for what was actually verified in this environment.

## Scientific limits and roadmap

Thresholds are experimental configuration. SAR shadow, smooth soil, wind, vegetation, urban double bounce, speckle and orbit geometry affect interpretation. Algorithms assume calibrated, terrain-corrected, co-registered inputs with matched polarization and valid-data masks; array shape checks cannot establish these conditions. Missing/invalid pixels remain excluded. Fractions need a consistent valid-area denominator. Candidate first/last observations are not exact flood onset/recession.

Next milestone: select comparable real Piura pre-event/event observations, integrate one documented preprocessing backend, archive processing provenance, and validate against independent reference data before accepting any flood footprint.

Roadmap: v0.x scientifically validated Flood → v1 Landslide → v2 InSAR deformation. Nothing is FROZEN until explicitly reviewed and accepted.
