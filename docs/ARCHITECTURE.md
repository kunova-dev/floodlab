# Architecture

STAGE: Foundation | VERSION: 0.5.0a1 | STATUS: DRAFT
PURPOSE: Separate reusable Earth observation infrastructure from hazards and application workflows.
INPUTS: WGS84 polygon AOIs, UTC dates, STAC metadata, analysis-ready arrays, indicator series.
OUTPUTS: Acquisition metadata, preparation manifests, experimental masks/QC, candidate events.
ASSUMPTIONS: Source checkout installation; external services and scientific preprocessing are independently verified.
TEST STATUS: See STATUS.md for executed verification.

```text
UI (Streamlit) ──> EO core: AOI → catalogue → acquisitions → preparation manifest
                                      │
                    CDSE openEO → explicit sar_backscatter → downloaded GeoTIFFs + QC
                                      │
                       analysis-ready backscatter + provenance
                                      │
                   hazards/flood → indicators → history/events
                                      │
                              impact [interface]
```

## Packages

- `eo_core/aoi.py`: GeoJSON geometry validation, WGS84 bounds and dateline ambiguity rejection.
- `eo_core/config.py`: typed configuration wrapper, TOML loading and operational validation.
- `eo_core/catalogue.py`: provider protocol, query construction, bounded STAC access, normalization and defensive space/time filtering.
- `eo_core/processing.py`: product-access/preprocessing protocols, observation readiness, UUID/timestamp/version provenance manifests. The openEO implementation is in openeo_backend/pair_jobs; the Piura pair completed authenticated processing with numeric QC PASS and unresolved exact source-lineage warnings. SNAP and other adapters remain future work.
- `hazards/flood/engine.py`: sensor-processing-independent algorithms on analysis-ready arrays, with observed/derived, configuration, assumption and QC/confidence fields.
- `history/events.py`: validated indicators, independent median/MAD baseline, anomaly grouping and observed peak.
- `impact`: exposure-intersection protocol and affected-summary contract only.
- `ui`: navigation, map, AOI drawing/upload, catalogue search, metadata selection and manifest download.

## State and storage

Search results retain their original AOI/query even if form controls change. Changing AOI or attempting a new search clears previous results; failed searches cannot silently display an earlier successful timeline. Selection is constrained to current results. Streamlit session state is transient. Manifests download to the user's browser. No uploads, exposure or satellite products are committed or persisted automatically.

`data/reference` is for reviewed, small public reference metadata, with its own source/license notes. Runtime caches, uploads and outputs are Git-ignored. The cache/output paths are configuration contracts for subsequent backends. Bootstrap creates standard runtime directories without deletion or configuration replacement.

## Extension constraints

Keep generic sensor/AOI functionality in EO core. Processing adapters must report calibration convention (sigma0/gamma0), units, DEM, grid/CRS, masking, orbit/polarization, software versions and product provenance. A future impact implementation must state spatial predicate and boundary/deduplication behavior. Monitoring needs a scheduler, retries, persistent jobs and review policy; the current Watch page describes this architecture only.


## v0.2 backend path

`pairs.py` assesses satellite comparability using matching relative orbit, direction, mode, bands and geodesic common AOI coverage. It deliberately does not infer flood timing. `openeo_backend.py` discovers and validates live capabilities, constructs explicit process graphs and handles memory-only OIDC device authentication. `pair_jobs.py` records plans, graphs, capabilities and resumable batch IDs, downloads fixed-name TIFF outputs and writes provenance. `raster.py` computes QC, explicitly aligns grids if needed, and generates shared-scale dB previews. `ui/processing.py` presents plans and state; the terminal worker owns authentication and long-running processing.

Plans and state live under configured ignored runtime directories. Atomic JSON writes let UI refresh safely; an exclusive worker lock prevents concurrent execution of one plan. Jobs are recorded before start and reused on resume. The worker validates graphs before creating jobs; public graph validation is not proof of successful execution. No token/password or refresh cache is written. The download stage stores no signed result URLs in provenance.

Source STAC candidates are recorded separately from actual backend lineage: one-second temporal requests and orbit/mode filters constrain the cube, but the backend does not advertise relative-orbit filtering or exact product pinning. Source identity stays unverified; the worker refuses multiple TIFFs. Numeric QC PASS is possible independently of overall QC WARNING for unresolved lineage. The real Piura run has completed; its engineering checkpoint is PASS while exact source identity and scientific flood interpretation remain DRAFT.


## v0.4 reconstruction

EO CORE → PERIL ENGINES → RISK APPLICATIONS remains the boundary. Generic verified context alignment, public STAC pagination and gauge observation contracts live in `eo_core`. Historical-water interpretation, optical classification and evidence states live in `hazards/flood`. The consumer UI uses `reconstruction.reconstruct`, while the v0.3 workflow and outputs remain as a regression reference. No risk/loss implementation is introduced.

Operator preparation scripts download public context/optical extracts with source metadata. Consumer analysis is local and never triggers paid remote jobs or authentication. It reuses verified SAR processing, applies land and historical-water domains, retains independent sensor states and creates a new UUID package. Missing optical/gauge evidence is explicit and nonfatal; missing/unverified mandatory land/history prevents a misleading result. Context is currently bounded to the prepared Piura area. A future service can replace preparation adapters without moving scientific interpretation into the UI.

## v0.5a impact aggregation

`impact.engine` is a hazard-independent library. It accepts WGS84 hazard, AOI, and optional land polygons plus hazard/event metadata; it dissolves overlapping source geometry, builds sorted unique H3 candidates, clips each cell to the AOI and supplied land, and calculates exact planar intersections in a local equal-area CRS. The output retains both square metres and hectares. The land denominator is null if no land was supplied or a cell has no terrestrial area. Area conservation checks ensure partition totals match the source geometry within a declared tolerance.

`impact.package` adapts a completed FloodLab package, verifies source hashes, vectorizes the land raster, and writes a new derived ZIP with the original contents and source manifest preserved alongside H3 GeoJSON/provenance. `ui/impact.py` exposes the optional grid/map and derived download after a completed analysis. H3 supports visual aggregation; the source hazard raster/vector remains the scientific footprint. No exposure datasets, loss calculations or new hazard-validation claims are provided. Regional input geometry is limited to non-dateline polygons; cell candidate generation uses a pinned experimental H3 API.
