# FloodLab v0.3: Piura event assessment

Status: DRAFT (scientific result). Engineering tests: PASS. Nothing is FROZEN.

## Event chronology and observation interpretation

This is a late-March escalation / early-April ongoing-inundation study, not a reconstruction of the complete 2017 flood season or its peak footprint.

- The [INDECI emergency declaration](https://portal.indeci.gob.pe/wp-content/uploads/2019/01/20171221162233.pdf), published March 29, records the March 27 overflow and worsening conditions from March 25. An earlier seasonal emergency already existed.
- [UNOSAT's March 24 Radarsat-2 assessment](https://unosat.org/static/unosat_filesystem/2481/UNOSAT_A3_FL20170317PER_Piura_FloodAnalysis_Portrait.pdf) shows overflow and wet agricultural plots before the escalation. Its preliminary map was not field validated.
- [Agro Rural's April 3 report](https://www.gob.pe/institucion/agrorural/noticias/526787-equipos-del-sector-agricultura-trabajan-para-reparar-diques-que-rompio-el-rio-piura) describes inundation from breached dikes and isolated Lower Piura communities.
- [EUMETSAT's April 4 observations](https://user.eumetsat.int/resources/case-studies/floods-in-south-america) provide coarse optical context for water/sediment south of Piura, not pixel-level truth for a 20 m product.

March 11 is an earlier observed-water comparison before the documented escalation. It is NOT demonstrated to be flood-free, normal, or permanent water. April 4 is interpreted as ongoing/remaining inundation, not March 27 peak extent. A recession date has not been independently established, so no AFTER layer is presented.

The reference event's baseline window March 1–16 is a conservative design choice to avoid developing mid/late-March flooding; it is not an independently measured onset. During window March 27–April 4 is supported by the evidence above. The selector excludes March 20/23/26 as baselines and observations after April 4 as unsupported during-event interpretations. It requires matching orbit, mode and VV, adequate geodesic common coverage, then ranks coverage, platform compatibility and temporal proximity. These windows are supplied by the peril application to the generic EO selector.

The cached live catalogue contains 10 observations. The selected pair remains:

- Before: 2017-03-11T23:43:11.173270Z, expected S1B_IW_GRDH_1SDV_20170311T234311_20170311T234336_004667_008247_7495_COG.
- During: 2017-04-04T23:43:11.844763Z, expected S1B_IW_GRDH_1SDV_20170404T234311_20170404T234336_005017_008C6C_B798_COG.

Catalogue metadata: ascending, relative orbit 91, IW, VV. The existing real CDSE outputs are reused. Backend product identity is NOT independently established; expected IDs and unverified lineage remain in provenance. No additional remote processing was needed or submitted.

## Method and sensitivity

Real single-band linear sigma0-ellipsoid rasters are converted to dB. Classification uses common positive, finite, unmasked pixels inside the selected AOI (pixel-center rule). Flood inference remains in hazards/flood; generic selection, grid QC and exports remain in eo_core. Risk/impact modules are unchanged.

An exploratory -18 dB absolute screen produces candidate water in each observation. Probable new inundation additionally requires no earlier water and an event-minus-earlier decrease of at least 3 dB. The threshold is a provisional conservative screening choice, NOT a validated or optimized Piura parameter. Existing -17 dB defaults are not assumed correct. Global pooled-scene Otsu is evaluated and recorded as an alternative, but its estimated -13.56 dB split is not established to separate water from land and is not adopted as truth. No single-band detector can establish water solely from darkness.

Reference approaches: [Sentinel Hub's multitemporal flood visualisation](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel-1/flood_mapping/) motivates compatible before/event comparison and describes urban scattering limitations; [DLR GFM documentation](https://extwiki.eodc.eu/en/GFM/PDD/GFM_algorithms/DLR_algo) describes more sophisticated threshold derivation using water references. FloodLab does not implement or claim equivalence to those operational algorithms.

Four-connected components smaller than 9 pixels (0.36 ha at 20 m) are removed to suppress isolated speckle-scale detections. This heuristic sacrifices small features; it is recorded, not scientifically calibrated. No terrain-shadow, urban, vegetation or land-cover correction is implemented. No permanent-water reference is inferred from one image.

Sensitivity grid: water screens -20/-18/-16 dB and change screens -2/-3/-4 dB. Derived areas span 758.84–5,273.24 ha. This is parameter sensitivity, NOT a confidence interval. The primary experimental result is 2,324.84 ha, with 2,703 polygons. Whole-scene Otsu at the same change/MMU settings produces approximately 7,290 ha, further illustrating method dependence.

## QC and output semantics

Source rasters share EPSG:32717, 20 m grids; both checksums match v0.2 provenance. Rectangular raster common-valid coverage is 99.8017%; inside the AOI pixel-center mask it is 100%. The difference arises from invalid cells outside the AOI boundary in the bounding raster, not from dropping invalid AOI pixels.

GeoTIFF masks use 0=no detection, 1=detection, 255=invalid/outside AOI. Before and during masks are experimental water observations. Flood polygons are RFC7946 WGS84 GeoJSON with projected area in hectares calculated before coordinate conversion. Raster area and polygons use the same grid. Display PNGs are nearest-neighbor geographic previews; all area calculations use full-resolution projected masks.

## Independent reference comparison

Retrieved 37,035 polygons intersecting the demo AOI from [INDECI's SIRAIM Piura 2017 service](https://geosinpad.indeci.gob.pe/indeci/rest/services/SIRAIM/SDE_areasInundadasPiura2017/MapServer/0). Every returned object ID was requested in bounded batches; count checked. Raw reference and retrieval metadata remain in ignored data/cache/references. The layer has no observation-date field, mapped dry-area/coverage mask, detailed method, or accuracy assessment. The publisher is independent; underlying source sensor independence is unknown.

The polygons are transformed to the analysis grid, rasterized by pixel center, and compared only on common valid AOI pixels:

| Category | Area (ha) | Meaning |
| --- | ---: | --- |
| Agreement | 1,076.24 | Both maps indicate inundation |
| Possible omission | 37,844.56 | Reference polygon present, FloodLab detection absent |
| Possible commission | 1,248.60 | FloodLab detection present, reference polygon absent |

These are descriptive overlaps, NOT confirmed errors or accuracy statistics. The reference may represent a broader period/extent or include normal water; outside its polygons is not established dry. Temporal mismatch, reference completeness and sensor effects preclude defensible accuracy scoring. The substantial reference-only area prevents a scientific PASS claim. Qualitative reports establish flood occurrence but do not validate every classification pixel.

## Reproduction and use

Open the default FLOOD EVENT page, select the Piura reference AOI and click ANALYSE FLOOD EVENT. Switch Before / During / Flood footprint. View comparison and complete audit details in their expanders. No credentials, terminal commands or satellite-parameter selection are required for this cached reference case.

Reproduce with `.venv/Scripts/python.exe scripts/analyse_piura.py`. Output directory is content-addressed under ignored outputs/events; result.json links AOI, chronology/citations, observations, raster hashes, processing provenance, classification, software version, QC, sensitivity and reference hashes. GeoTIFF, GeoJSON and PNG outputs have checksums. To refetch the public reference, run scripts/fetch_piura_reference.py (network required).

The page supports AOI selection/drawing/upload but only the curated Piura event. It reuses the recorded live catalogue inventory rather than claiming a fresh live query. If no suitable processed pair covers the AOI, it stops with an explicit additional-processing requirement and launches no jobs. General event discovery, UI-managed device authentication, new-job orchestration and calibrated confidence are not implemented in v0.3.

Next scientific limitation: establish a temporally matched reference with known surveyed coverage, then evaluate omission and commission and refine the baseline/classification. March 11 may already contain seasonal water, and April 4 does not capture all peak inundation.


## v0.3 files and verification

Added: config/piura2017-event.json; eo_core/event_selection.py and mask_io.py; hazards/flood/event.py and workflow.py; ui/event.py; scripts/analyse_piura.py and fetch_piura_reference.py; tests/test_event.py; this report. Updated: ui/main.py, package version metadata, tests/test_ui.py, README.md and STATUS.md. Prior uncommitted v0.2 files were retained.

Verification: 76 deterministic tests passed; bootstrap, 24-module import checks, configuration validation, Ruff, compileall, diff whitespace checks and independent Streamlit HTTP health smoke passed. Regression coverage includes legacy catalogue/processing UI. Rasterio emits pending-deprecation warnings from its Affine implementation. Runtime references, source rasters and event products remain Git-ignored. No commit or push.

The event identity and provenance include SHA-256 fingerprints of implementation source files as well as data and parameters, so code changes invalidate cached results. Tests do not use live remote processing. The cached reference result is generated from real data, not test fixtures.

Browser review confirmed the default v0.3 action, real result metrics, layer switcher and audit expanders. Replaced the initial Carto tiles after visual inspection exposed API-key watermarks; the event page uses standard OpenStreetMap tiles.
