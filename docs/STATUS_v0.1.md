# FloodLab v0.1 formal validation checkpoint

STAGE: EO foundation and Piura catalogue investigation
VERSION: 0.1.0
STATUS: PASS
PURPOSE: Accept the engineering foundation within its declared v0.1 scope, not scientific flood-map accuracy.
INPUTS: Repository source/configuration, independent live CDSE query, bounded asset-access probes, synthetic/mocked automated tests.
OUTPUTS: Validation matrix, acquisition inventory, asset-access evidence and remaining processing requirements.
ASSUMPTIONS: No authenticated product access, raster decoding, SAR preprocessing or Piura flood delineation has been completed.
TEST STATUS: 35 pytest tests passed; import/configuration/bootstrap/startup/static checks passed on Windows, Python 3.12, 2026-09-19.

No component is FROZEN. PASS is restricted to the verified behavior listed below. Scientific algorithms and unimplemented services remain DRAFT. This is a working-tree documentation checkpoint: Git currently has zero tracked files and zero commits; no commit or tag was created by this review.

## Validation matrix

| Component | Status | Real/Mocked | Tests | Limitations |
|---|---|---|---|---|
| Package, installation and imports | PASS | Real local installation | All 13 package modules imported; compileall; pip check | Editable source checkout; dependency ranges rather than a scientific lockfile; Python 3.11 not separately exercised |
| TOML configuration and path resolution | PASS | Real Piura configuration | Valid config/AOI loaded; invalid endpoint, numeric and threshold regression tests | Fixed default config path in UI; values stored in dicts; custom cache directories are not automatically created |
| AOI/GeoJSON validation | PASS | Real demo polygon; synthetic invalid geometries | Roundtrip, geometry/bounds/dateline and malformed-input tests | Search rectangle, not observed flooding; dateline regions require splitting; not a geodetic area calculator |
| Temporal query and STAC discovery | PASS | LIVE Copernicus CDSE | Mock query/spatial/time-filter tests plus independent live query below | Capped at 100; archive/provider completeness not independently established; a search is not a flood-event census |
| Sentinel-1 normalization and asset discovery | PASS | Real returned product metadata | Orbit/polarization/missing-field tests; real assets inspected | Asset URLs are advertised metadata, not proof of readable calibrated backscatter |
| Readiness and preparation manifests | PASS | Real metadata, local serialization; mock fixtures in tests | Readiness/serialization and selection-persistence checks | Metadata comparability only; no backend submission, download or preprocessing; manifest timestamp represents creation, not a retained raw catalogue-response timestamp |
| Streamlit History/Lab journey | PASS | Real application and live service; mocked service/map in deterministic tests | AppTest navigation/demo/search failure/selection tests; independent server health smoke | Drawing controls present but manual drawing/upload/browser combinations not exhaustively tested; external map tiles require network |
| Product access | DRAFT | Protocol only; real unauthenticated probes | All ten VV HTTPS URLs returned HTTP 401 | No authenticated download or S3 access tested; actual raster readability and availability after authentication unverified |
| SAR preprocessing backends | DRAFT | Architectural protocols only | Imports only | No SNAP, openEO, analysis-ready service or local GeoTIFF ingestion implementation |
| Flood array algorithms | DRAFT | Real numerical implementation; SYNTHETIC input tests | dB, threshold, change, exclusion, cleanup, area, Otsu tests pass | Experimental science; assumes externally verified calibration/grid/units; not connected to catalogue imagery; no real flood output or accuracy assessment |
| Historical event engine | DRAFT | Real generic grouping; SYNTHETIC series | Baseline/anomaly/gap/peak tests pass | No real Piura indicator series or UI event catalogue; temporal clusters do not prove continuous inundation or exact onset/recession |
| Permanent-water reference | DRAFT | Boolean-array input interface only | Synthetic exclusion and shape validation | No provider, real reference layer, alignment or provenance ingestion |
| Flood Watch | DRAFT | UI architectural shell | Page renders | No scheduler, automatic ingestion, alerts or current monitoring |
| Impact | DRAFT | Protocol and UI shell | Import/page checks | No spatial intersection execution, exposure ingestion or financial losses |
| Bootstrap and runtime isolation | PASS | Real filesystem operations | Repeated bootstrap, preservation and path-conflict tests | Standard directories only; no cache implementation or job store |
| Git hygiene | PASS | Real index/history/ignore inspection | Zero tracked files/commits; ignore probes; candidate-file and credential-pattern review | Entire implementation remains untracked; pattern scan is not a formal secret-scanner guarantee |
| CI and Codespaces | DRAFT | Real configuration files, not executed remotely | YAML/JSON/configuration inspected; corresponding local commands pass | GitHub Actions and devcontainer build not executed |
| Documentation/scientific boundaries | PASS | Real source/documentation review | Architecture, methodology, decisions, README and warnings inspected | Engineering acceptance only; no scientific certification |

## Executed verification and small fixes

- Reviewed every source module, both test modules, scripts, app entry point, package metadata, operational/demo configuration, ignore rules, CI/devcontainer/Streamlit settings, environment example and repository documentation. Runtime output and installed third-party dependencies are not application source.
- `python scripts/bootstrap.py`: all four standard folders OK; existing files preserved.
- `python -m pytest -q`: **35 passed in 1.67 seconds** after fixes (previous suite: 24 tests).
- Imported **13 package modules** via pkgutil/importlib; UI import emits Streamlit's expected bare-mode ScriptRunContext warning, not an import error.
- Explicit `load_config` and `AOI.read`: valid `sentinel-1-grd` configuration and bounds `(-80.95, -5.65, -80.45, -5.05)`.
- Launched a separate Streamlit process on localhost port 8502; `/_stcore/health` returned **HTTP 200, `ok`**; terminated only that owned smoke-test process. AppTest separately executes app code, since health alone does not validate rendered application logic. The existing user app on port 8501 was not stopped.
- Ruff checks, compileall and pip dependency checks passed.
- Small fixes only: reject nonfinite event parameters, noninteger operational counts, nonnegative change thresholds and malformed/credential-bearing endpoint URLs; normalize malformed GeoJSON input failures so the UI reports validation errors; catch configuration type errors in UI; repair a garbled dateline error string. Added 11 regression cases. No new processing functionality or architectural redesign.

## Live Piura search provenance

**The acquisitions displayed in the prior Piura browser journey came from a LIVE Copernicus query, not sample/mock data.** Source review confirms the production UI calls `StacCatalogue.search`, which uses `pystac_client.Client.open` and the provider's collection/search services. There is no production sample-result fallback. Mocks appear only in tests. The independent repeat query below returned the same ten product identifiers as the previously inspected browser results; an existing browser session is a snapshot of its last query, not a continuously refreshing feed.

Repeat query recorded at **2026-09-19T19:33:21.646555+00:00**.

- AOI: `config/aoi/piura2017.geojson`, **PIURA 2017 DEMO AOI — NOT AUTHORITATIVE FLOOD EXTENT**.
- WGS84 polygon ring, longitude/latitude: `[-80.95,-5.65] → [-80.45,-5.65] → [-80.45,-5.05] → [-80.95,-5.05] → [-80.95,-5.65]`.
- Requested UTC interval: **2017-03-01T00:00:00Z through 2017-04-30T23:59:59.999999Z**, inclusive.
- Provider: Copernicus Data Space Ecosystem public STAC, `https://stac.dataspace.copernicus.eu/v1`.
- Collection: **`sentinel-1-grd`**; verified at runtime using the collection endpoint.
- Search intersects the AOI; adapter also checks returned geometry and acquisition timestamp.
- Returned: **10 acquisitions** with cap 100, so the configured cap was not reached. Two adjacent acquisitions occur on April 1; there are nine distinct acquisition dates. No claim of complete mission/archive coverage.

| Acquisition timestamp (UTC) | Orbit | Relative orbit | Polarization | Product identifier |
|---|---|---|---|---|
| 2017-03-11T23:43:11.173270Z | ascending | 91 | VV, VH | `S1B_IW_GRDH_1SDV_20170311T234311_20170311T234336_004667_008247_7495_COG` |
| 2017-03-20T11:01:08.214928Z | descending | 40 | VV | `S1B_IW_GRDH_1SSV_20170320T110108_20170320T110133_004791_0085E7_35ED_COG` |
| 2017-03-23T23:43:11.351606Z | ascending | 91 | VV, VH | `S1B_IW_GRDH_1SDV_20170323T234311_20170323T234336_004842_00875E_3C25_COG` |
| 2017-03-26T11:01:59.942978Z | descending | 40 | VV | `S1A_IW_GRDH_1SSV_20170326T110159_20170326T110224_015862_01A234_10B8_COG` |
| 2017-04-01T11:01:01.646277Z | descending | 40 | VV, VH | `S1B_IW_GRDH_1SDV_20170401T110101_20170401T110126_004966_008AF0_1D06_COG` |
| 2017-04-01T11:01:26.646788Z | descending | 40 | VV, VH | `S1B_IW_GRDH_1SDV_20170401T110126_20170401T110157_004966_008AF0_2236_COG` |
| 2017-04-04T23:43:11.844763Z | ascending | 91 | VV, VH | `S1B_IW_GRDH_1SDV_20170404T234311_20170404T234336_005017_008C6C_B798_COG` |
| 2017-04-13T11:01:08.953335Z | descending | 40 | VV | `S1B_IW_GRDH_1SSV_20170413T110108_20170413T110133_005141_008FF2_B0BD_COG` |
| 2017-04-16T23:43:12.365925Z | ascending | 91 | VV, VH | `S1B_IW_GRDH_1SDV_20170416T234312_20170416T234337_005192_00916D_569A_COG` |
| 2017-04-28T23:43:12.849977Z | ascending | 91 | VV, VH | `S1B_IW_GRDH_1SDV_20170428T234312_20170428T234337_005367_00968B_390D_COG` |

## Can the raster assets actually be accessed?

**Not anonymously through the tested URLs in this environment.** All ten acquisitions advertise a VV TIFF asset with an S3 href and HTTPS alternative. For each acquisition, a real unauthenticated streaming GET against the advertised VV HTTPS URL requested `Range: bytes=0-15` with bounded timeouts. **All ten returned HTTP 401 Unauthorized; zero raster bytes were read.** No tokens were supplied and no authentication bypass was attempted. VH, archives and S3 were not separately fetched. A 401 confirms an access barrier, not successful product retrieval or proof that an authenticated account will be able to obtain the product.

The catalogue describes these measurement assets as **amplitude**, stored as uint16 COG TIFFs, with calibration/noise annotations advertised separately. They are not verified analysis-ready sigma0/gamma0 backscatter. Do not feed their digital numbers into `to_db`, which expects already-calibrated linear power. COG is a storage layout, not a scientific processing level.

The metadata and access-probe record is retained locally in ignored `outputs/validation-live.json`; the bounded probe script and startup log are also in ignored `outputs/`. This document retains the public acquisition inventory so the review does not depend on committing generated output.

## Git/security evidence

`git ls-files` returned **zero paths** and `git rev-list --all --count` returned **0**. Therefore no credentials, caches, satellite products, user data or generated outputs are tracked in the index or reachable commit history. All application files are currently untracked. The largest nonignored candidate at review time was the UI module, approximately 11 KB; no large satellite files were among candidates. Cache and user-upload folders contained no files.

`git check-ignore` confirmed exclusions for `.env`, `.streamlit/secrets.toml`, `.venv/pyvenv.cfg`, cache TIFFs, user exposure CSVs, generated validation JSON, SAFE directories and TIFF products. Review of the nonignored candidates and a targeted private-key/token-pattern scan found no embedded credentials; `.env.example` contains comments only. This is current-state evidence, not a guarantee that arbitrary future file names or secrets will be ignored. No Git commit/tag, credential configuration or exposure-data upload was performed.

## Scientific honesty and remaining processing

**No code or documentation claims that discovered Sentinel-1 GRD is a flood footprint.** The Piura polygon is labelled a demo search area. Catalogue discovery is implemented in EO core; raw/product access and preprocessing are unimplemented protocols; flood classification accepts externally prepared arrays. The UI retains `AWAITING_PREPROCESSING` (an operational job state, not an audit status).

Before a scientifically defensible mask can be produced:

1. Establish authorized product access and actual raster/annotation readability. Verify checksums, completeness and the product processing history; record source IDs and retrieval times.
2. Choose genuine pre-event/event dates from independent event evidence. Use comparable relative orbit, direction, mode, polarization and AOI coverage. This result set mixes ascending orbit 91 and descending orbit 40 and must not be treated as one interchangeable pair series. March 1 is merely the search start, not proof of a dry baseline.
3. Implement one documented preprocessing route: apply appropriate orbit metadata, calibration to a stated sigma0/gamma0 convention, applicable thermal/border-noise handling, and reviewed speckle treatment. Account for provider preprocessing already performed rather than applying corrections twice.
4. Perform DEM-based terrain/geometric correction and appropriate radiometric treatment; co-register/resample to a common grid with explicit CRS/resolution. Preserve nodata, border, shadow/layover and valid-coverage masks and record DEM/software/parameter provenance. Verify amplitude-versus-power and dB conventions explicitly.
5. Prepare a representative baseline and aligned permanent-water reference; compute experimental classification/change masks only on valid comparable pixels. Review incidence-angle, smooth-soil, urban and vegetation limitations, threshold/Otsu sensitivity, and cleanup effects. Calculate metric/geodesic areas with an appropriate valid-area denominator.
6. Compare derived masks against independent dated reference evidence; quantify omission/commission errors and uncertainty. Only then consider scientific acceptance. Event reconstruction also requires real per-observation indicators and adequate temporal sampling.

Official reference: [CDSE STAC documentation](https://documentation.dataspace.copernicus.eu/APIs/STAC.html) documents discovery; [CDSE Sentinel-1 processing documentation](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S1GRD.html) documents processing choices such as calibration, orthorectification and speckle filtering. These service capabilities are not implemented FloodLab capabilities.

## Single next engineering milestone

**Implement and validate one authenticated analysis-ready Sentinel-1 preprocessing path for a comparable Piura baseline/event pair, producing calibrated, terrain-corrected, co-registered backscatter with masks and complete provenance.** Acceptance should demonstrate actual raster access and processing/QC evidence before applying the existing experimental flood classifier. Backend selection and implementation are the next task, not part of this review.
