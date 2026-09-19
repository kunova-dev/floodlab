# Architecture

STAGE: Foundation | VERSION: 0.1.0 | STATUS: DRAFT
PURPOSE: Separate reusable Earth observation infrastructure from hazards and application workflows.
INPUTS: WGS84 polygon AOIs, UTC dates, STAC metadata, analysis-ready arrays, indicator series.
OUTPUTS: Acquisition metadata, preparation manifests, experimental masks/QC, candidate events.
ASSUMPTIONS: Source checkout installation; external services and scientific preprocessing are independently verified.
TEST STATUS: See STATUS.md for executed verification.

```text
UI (Streamlit) ──> EO core: AOI → catalogue → acquisitions → preparation manifest
                                      │
                    product access → preprocessing [future adapters]
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
- `eo_core/processing.py`: product-access/preprocessing protocols, observation readiness, UUID/timestamp/version provenance manifests. Future openEO, SNAP, analysis-ready services and local GeoTIFF adapters implement these contracts; no adapter is claimed complete.
- `hazards/flood/engine.py`: sensor-processing-independent algorithms on analysis-ready arrays, with observed/derived, configuration, assumption and QC/confidence fields.
- `history/events.py`: validated indicators, independent median/MAD baseline, anomaly grouping and observed peak.
- `impact`: exposure-intersection protocol and affected-summary contract only.
- `ui`: navigation, map, AOI drawing/upload, catalogue search, metadata selection and manifest download.

## State and storage

Search results retain their original AOI/query even if form controls change. Changing AOI or attempting a new search clears previous results; failed searches cannot silently display an earlier successful timeline. Selection is constrained to current results. Streamlit session state is transient. Manifests download to the user's browser. No uploads, exposure or satellite products are committed or persisted automatically.

`data/reference` is for reviewed, small public reference metadata, with its own source/license notes. Runtime caches, uploads and outputs are Git-ignored. The cache/output paths are configuration contracts for subsequent backends. Bootstrap creates standard runtime directories without deletion or configuration replacement.

## Extension constraints

Keep generic sensor/AOI functionality in EO core. Processing adapters must report calibration convention (sigma0/gamma0), units, DEM, grid/CRS, masking, orbit/polarization, software versions and product provenance. A future impact implementation must state spatial predicate and boundary/deduplication behavior. Monitoring needs a scheduler, retries, persistent jobs and review policy; the current Watch page describes this architecture only.
