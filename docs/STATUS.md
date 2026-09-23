# FloodLab v0.5d generic temporal impact validation — 2026-09-23

**STATUS: PASS.** The unchanged generic Impact Engine consumed the frozen pair, maximum-observed single-date, and event-observed temporal-union hazard products without flood-specific core logic. Native hazard measurement remains authoritative; H3 is a reconciling representation. The packages reuse Overture release `2026-08-19.0` as modern/contextual mapped-building exposure only.

| Product | Native ha | H3 ha | Unique mapped buildings intersecting | Building-footprint intersection m² |
| --- | ---: | ---: | ---: | ---: |
| Legacy pair | 1,921.24 | 1,922.73 | 157 | 6,502.58 |
| Maximum observed single-date | 6,328.76 | 6,333.40 | 129 | 4,426.98 |
| Event-observed temporal union | 10,666.64 | 10,674.52 | 286 | 10,929.63 |

The temporal union means mapped buildings located in terrestrial areas observed inundated at least once during the event; it is not a simultaneous impact count. Each package records upstream footprint checksum, product type/period, H3 provenance, Overture provider/release/cache metadata, and exact geometric building intersections. All three impact ZIP CRCs and local checksum manifests validate.

The cached 282,185-building subset is normalized once with a source-checksum, release and normalization-schema-bound receipt. Current scalability remains limited: generic enrichment iterates through all normalized AOI buildings separately for every hazard footprint. Future work should add spatial-index candidate filtering plus reusable hazard-independent H3/exposure allocation, with equivalence tests before use. No such optimization is included here.

Validation: the previously failing UI test passed in a clean Python process, confirming a transient pandas partial-import state; no application workaround was added. Impact tests passed 9/9. The synthetic non-flood regression remains part of the Impact test suite and confirms no EO/flood imports are required. Full-suite rerun recorded 98 passes and one transient UI failure from the same pandas import state. No component is FROZEN.

# FloodLab v0.5c temporal reconstruction QC — 2026-09-23

**STATUS: PASS (engineering and reproducibility); flood science remains DRAFT.** A cached-data stable-terrestrial diagnostic supports retaining the March 26 Sentinel-1A observation without correction. It used 8,017,321 terrestrial, non-permanent-water, valid pixels outside all fixed-method candidate-change masks and slopes above 5 degrees. Relative to the S1B descending baseline median, stable-reference median shifts were +3.64 dB on Mar 20 (S1B), +4.38 dB on Mar 26 (S1A), and +2.20 dB on Apr 13 (S1B). Mar 26 minus Mar 20 was +0.61 dB median (+0.57 dB mean; 2.82 dB robust spread); quadrant medians ranged -0.17 to +1.60 dB. This is not a material scene-wide S1A/S1B anomaly, and the independently elevated S1B Mar 20 result supports the conclusion that Mar 26 is not solely a platform-transition artefact. No empirical offset was derived or applied.

The frozen March 11 -> April 4 pair regression remains unchanged at **1,921.24 ha**. It remains a legacy pair-based observation product. The cached real-data reconstruction used the existing v0.4 20 m grid, land/ocean exclusion, historical/permanent-water exclusion, -18 dB water screen, -3 dB change screen and 9-pixel mapping unit. Its temporal package is `outputs/analyses/3bb5d30e-d3bf-46db-a55c-6c746847d558`.

| Date | Sequence / platform | Baseline | Provisional observed-inundation area (ha) | Status |
| --- | --- | --- | ---: | --- |
| 2017-03-20 | descending rel. 40 / S1B | Jan 19, Feb 12, Feb 24 (S1B) | 5,374.12 | DRAFT; separate sequence |
| 2017-03-23 | ascending rel. 91 / S1B | Feb 3, Feb 27, Mar 11 (S1B) | 2,636.84 | DRAFT; same-platform sequence |
| 2017-03-26 | descending rel. 40 / S1A | Jan 19, Feb 12, Feb 24 (S1B) | 6,328.76 | DRAFT; retained after stable-reference QC |
| 2017-04-04 | ascending rel. 91 / S1B | Feb 3, Feb 27, Mar 11 (S1B) | 2,553.96 | DRAFT; same-platform sequence |
| 2017-04-13 | descending rel. 40 / S1B | Jan 19, Feb 12, Feb 24 (S1B) | 2,476.64 | DRAFT; separate sequence |

The independent ascending and descending baseline medians differ by 1.72 dB on terrestrial, non-permanent-water pixels. This is expected to include viewing-geometry effects and confirms that the sequences remain separate; it was not used as a correction. The temporal union is 10,666.64 ha; its descriptive INDECI overlap is 7,822.36 ha, with 31,087.76 ha reference-only and 2,844.28 ha satellite-only. Sentinel-2 remains limited clear-pixel evidence only: the preserved March 31 product has 2.06% usable terrestrial paired coverage with the January 10 baseline and is not independent validation. Generic Impact Engine contract checks passed in memory for selected single-date, maximum, and temporal-union GeoJSON footprints; no buildings/exposure analysis was run.

Validation before the stop: 99 pytest tests passed and Ruff passed. The pending temporal algorithms have synthetic tests for sequence separation, baseline requirements, partial coverage as NOT OBSERVED, union/count/fraction behavior and deterministic maximum selection. No satellite job was submitted or repeated during this QC step. No component is FROZEN.

# FloodLab v0.4 checkpoint — 2026-09-20

# FloodLab v0.5b Built Environment Intelligence checkpoint — 2026-09-23

Engineering implementation: **PASS**. Piura Overture building enrichment: **PASS WITH PIURA DATA** after independent DuckDB diagnosis and provider fallback. Flood science remains **DRAFT**. Nothing is FROZEN.

v0.5b introduces a provider-independent mapped-building interface and Overture Maps Buildings adapter. It does not alter the flood raster, flood method, baseline, thresholds, land mask, satellite processing, or H3 hazard calculation. The native Piura footprint remains 1,921.24 ha; H3 remains 1,922.73 ha. The initial Overture CLI/STAC path incorrectly reported `No data found`; independent DuckDB cloud GeoParquet retrieval proved coverage and the provider now falls back to that documented path. No replacement provider was selected.

| Component | Status | Real/Mocked | Tests | Limitations |
| --- | --- | --- | --- | --- |
| Overture Buildings provider | PASS | Real AOI-only DuckDB cloud GeoParquet retrieval, release `2026-08-19.0`; fixture provider tests | Cache reuse, fallback diagnosis, provenance, provider isolation | Current mapped layer is modern; no historical building claim |
| Normalized building model | PASS | Provider-neutral schema | Stable ID deduplication, nullable height/levels, geometry validity | Source attributes depend on provider completeness |
| Generic building/H3 enrichment | PASS | Synthetic non-flood and geometry fixtures | Unique count reconciliation, area apportionment, partial intersections, bounded percentages | Geometric intersection is potential exposure context only, never damage |
| Piura mapped-building result | PASS | Real Overture response: 282,185 raw/normalized buildings | Derived ZIP validation, source checksums, unique count and area reconciliation | 157 intersect hazard; modern contextual layer, not 2017 presence or damage |
| Derived impact package | PASS | Real Piura source package preserved | Archive CRC/checksum validation | No building GeoJSON exported when provider reports no data |

Source summary: Overture Maps Buildings is queried by its documented cloud GeoParquet/DuckDB workflow for `release/2026-08-19.0/theme=buildings/type=building/`, retrieving only the AOI subset. Overture's current documentation describes IDs, geometry, height, subtype and source fields where supplied; the Buildings theme is available under ODbL and source-level licence metadata is retained where available. The building layer is explicitly labelled **MODERN / CONTEXTUAL BUILT-ENVIRONMENT BASELINE**. It cannot show what existed in Piura during the 2017 event.

Piura validation: AOI WGS84 bbox is `(-80.95, -5.65, -80.45, -5.05)`, with longitude-first ordering and plausible Piura coordinates. Independent DuckDB returned **282,185 raw records** before FloodLab geometry filters. A small urban sanity bbox `(-80.66, -5.22, -80.60, -5.16)` returned **57,624 raw records**. FloodLab normalized **282,185** cached records; **157** unique buildings intersect the observed flood footprint. Total footprint area of AOI buildings is **30,789,831.88 m²**; geometrically intersecting hazard area is **6,502.58 m²**. Height is present for **17 / 282,185 (0.0060%)** and levels for **110 / 282,185 (0.0390%)**. The derived package `outputs/impacts/41e3d1a3-27d6-4700-b654-2f30ea023fb2/analysis.zip` validates with ZIP SHA-256 `9938ae526a85a903640b2168f704b6c3622f476c91b0cc8d06e4fbc064b21732`; its source manifest, H3 counts and area reconciliation pass.

Verification: **96 pytest tests passed** (128 existing Rasterio/Affine pending-deprecation warnings). The mandatory non-flood building path passed without EO core, flood processors, Sentinel or openEO imports. No satellite jobs were submitted; only public Overture queries ran. Caches and outputs remain ignored by Git. No commit or push.

---

# FloodLab v0.5a Impact Engine checkpoint — 2026-09-22

Engineering checkpoint: **PASS**. Piura flood science remains **DRAFT**. Nothing is FROZEN.

v0.5a adds a generic H3 area aggregation after a completed hazard footprint exists. It does not change or replace v0.4's native raster/vector footprint, does not rerun EO processing, and does not estimate exposed people/assets, probability, severity, or loss. Existing v0.4 result: 1,921.24 ha native land-only probable inundation; not validated by independent ground truth. H3 equal-area geometry measures 1,922.73 ha (difference +1.49 ha, 0.078%); native raster hectares remain the source result. At resolution 7 the real saved Piura AOI contains 663 intersecting cells, 293 with positive footprint, including 28 ocean-only cells whose land denominator and percent affected are null.

| Component | Status | Real/Mocked | Tests | Limitations |
| --- | --- | --- | --- | --- |
| Generic hazard-to-impact H3 engine | PASS | Real Shapely geometries; synthetic independent hazard test | Geometry/index, clipping, conservation, deduplication, areas, bounds, export, provenance | H3 bbox-overlap API is experimental; regional non-dateline polygons only; polygons inherited from source |
| AOI / land / hazard area semantics | PASS | Real Piura footprint and land mask; synthetic ocean/no-land cases | No double count, no area beyond AOI/land, null ocean denominator, percentages bounded | Land-mask accuracy inherited; hectare geometry may differ slightly from native raster measurement |
| Non-flood generic extension | PASS | Synthetic wildfire geometry, no mocked satellite inputs | Subprocess blocks imports from EO, flood and Sentinel/openEO processing modules | Generic aggregation only; no hazard-specific interpretation or validation |
| Optional Impact UI and map | PASS | Real saved Piura analysis; browser interaction | H3 map, cell popup, resolution selector, source footprint overlay, download | Expert details minimal; not an exposure or loss dashboard |
| Derived complete-analysis ZIP | PASS | Real completed v0.4 package `855dc008-898e-42ea-9dba-7aa46ee4b587` | Source hashes, all ZIP entries, CRC, H3 IDs/count, percentage bounds | Derived package preserves the source scientific status and inherits all source uncertainty |
| Exposure enrichment interface | DRAFT | Schema/protocol only | No synthetic exposures or fabricated values; type/interface imports | No buildings, population, roads, land-cover exposure products, risk or loss calculations |
| Scientific flood extent | DRAFT | Real experimental v0.4 result | Inherited v0.4 checks; H3 reconciles within 0.078% | No independent validation; uncertain event timing/source lineage and sparse optical coverage persist |

Verification: **93 pytest tests passed** (61.14 s; 128 existing Rasterio/Affine pending-deprecation warnings). Ruff check and format check passed; bootstrap passed. The v0.5a derived bundle validator passed: 663 cells, source archive and source flood/land/provenance checksums verified; ZIP SHA-256 `dfb353a7643bb3e9a7855042da10b6c72feedc6b5e5b75216d82517db9b094dd`. The synthetic non-flood test confirms the generic engine imports no EO/flood/Sentinel/openEO implementation. No remote jobs were submitted. Runtime outputs and caches remain Git-ignored; no commit or push.

Output: `outputs/impacts/6ab25fac-d4ea-44ad-92a4-afbd52a9a9cc/analysis.zip`. v0.4 source package SHA-256 remains `7aee27e85fe440b8790135ef4056d79a2524ed0c00f9e1a2e2eb979790de71de`; the original package was not modified. Best next milestone: choose one sourced exposure dataset (for example building footprints), define its date/coverage/licensing and spatial counting rules, then validate exposure aggregation independently before presenting any impact totals.

---

Engineering checkpoint: **PASS**. Scientific reconstruction: **DRAFT**. Nothing is FROZEN.

The real Piura run produced **1,921.24 ha** of experimental land-only new inundation, excluding **229.00 ha** of offshore v0.3 candidates. Zero ocean pixels contribute to terrestrial hectares. Historical water, uncertain baseline, sparse optical agreement and descriptive reference differences remain separate. This is not validated flood extent.

| Component | Status | Real/Mocked | Tests | Limitations |
| --- | --- | --- | --- | --- |
| Existing SAR acquisition/processing foundation | PASS | Real cached CDSE backscatter and catalogue; fixture regressions | All original 76 tests retained; input integrity and grid QC | Exact backend product lineage remains unverified; no new remote jobs |
| Land/ocean domain | PASS | GSHHG 2.3.7 full L1 | Integrity, domain tests; real zero-ocean check for water/flood/comparison exports | Historical shoreline, not guaranteed 20 m coastal truth |
| Historical-water baseline implementation | PASS | JRC annual 2013–2015 + 1984–2015 occurrence | Class semantics, unknown handling, temporal leakage rejection, land exclusion | Not a March climatology or multi-date SAR baseline |
| Sentinel-2 preparation and independent evidence | PASS | Real public January 10/March 31 L2A; synthetic failure fixtures | Cloud/shadow/invalid screening, missing/corrupt/cloudy inputs, evidence states | Only 2.064% common clear terrestrial coverage; four-day sensor mismatch |
| Public catalogue discovery | PASS | Real cached 34-item S2 inventory; mocked pagination test | Complete pagination and local cached read | Operator preparation, not arbitrary global event automation |
| River/terrain context | PASS | Real HydroRIVERS v1.0 and Copernicus GLO-30 DSM | Real CRS/grid checks, source hashes, diagnostic summaries | No HAND, routing, hydraulic connectivity proof or hard terrain filters |
| Gauge discovery/observation contract | PASS | Real published station discovery; schema fixtures | Provenance, units, timezone, finite values, rating provenance, optional failure | No usable historical hydrograph or authoritative rating curve retrieved |
| Gauge time-series integration | DRAFT | Discovery only | Explicit unavailable status verified | No flow/satellite temporal matching claimed |
| Reference-difference investigation | PASS | Real INDECI polygons | Valid-land categories, exclusive condition buckets, spatial diagnostics | Unknown reference dates/completeness; no accuracy score |
| Immutable product/export package | PASS | Real 77 MB ZIP; fixture products | UUID uniqueness, checksum/CRC, PNG readability, raster/vector area | Application does not overwrite; not filesystem-enforced archival immutability |
| Consumer journey | PASS | Real browser + mocked unavailable test | AOI → Analyse → Before/During/Flood footprint; evidence/timeline and ZIP download | Curated Piura event, prepared context required |
| Scientific flood interpretation | DRAFT | Real multi-evidence experimental result | Sensitivity 627.64–5,025.96 ha; independent evidence explicitly assessed | Sparse optical support, uncertain timing, fixed uncalibrated thresholds and source lineage |

Verification: **87 pytest tests passed** (11.82 s). Ruff check and format check passed for 45 Python files; compileall and git diff --check passed. Bootstrap passed. All 29 modules imported; primary configuration validated; new configuration checks and rejection cases passed. Independent Streamlit startup on port 8502 returned HTTP 200. Browser on port 8501 showed v0.4, completed a real analysis, switched layers, opened evidence/timeline and emitted a complete-analysis download. Third-party Rasterio/Affine pending-deprecation warnings remain (127 in the full test run); they are not scientific QC failures.

Real output validation: 58 payload SHA-256 hashes and archive CRCs passed. Derived GeoTIFF CRS/transforms match. Reprojected GeoJSON area is 1,921.2400000003443 ha versus raster 1,921.24 ha, within the documented 0.04 ha tolerance. The v0.4 terrestrial reference area plus excluded offshore reference area reconciles with the v0.3 reference domain. All 13 original v0.3 payload checksums still match. Git hygiene audit found no tracked/nonignored caches, outputs, satellite products or recognizable credential payloads. No commit or push.

Analysis ID: `3c236bb0-0c6c-4d69-b6f0-ca604bbb84c3`.
Package: `outputs/analyses/3c236bb0-0c6c-4d69-b6f0-ca604bbb84c3/analysis.zip`.
ZIP SHA-256: `7aee27e85fe440b8790135ef4056d79a2524ed0c00f9e1a2e2eb979790de71de`.

See [scientific assessment and full changed-file inventory](V04_SCIENTIFIC_ASSESSMENT.md) and [all output checksums](V04_OUTPUT_CHECKSUMS.json). Best next milestone: a dated Piura validation dataset and additional pre-event/event observations, to distinguish missed floodwater from temporal/reference mismatch before broadening to global automation.

---

# FloodLab v0.3 checkpoint

Scientific status: DRAFT. Engineering tests: PASS. Nothing is FROZEN.

Verification: 76 deterministic tests passed (4.62 s); Ruff, compileall and git diff --check passed. Bootstrap passed. All 24 modules imported, configuration validated, and independent Streamlit startup returned HTTP 200. Nine third-party Rasterio/Affine pending-deprecation warnings remain. Real-data execution produced the artifacts documented below; no remote processing was submitted. No commit or push was performed.

| Component | Status | Real/Mocked | Tests | Limitations |
| --- | --- | --- | --- | --- |
| Event-window observation selection | PASS | Cached live inventory; fixture tests | Compatible pairs, chronology exclusion, no-pair failures | Curated Piura windows, not automatic event discovery |
| Local flood inference and exports | PASS | Real v0.2 rasters; deterministic fixtures | Nodata, change, area, vectorization, checksums, provenance | Provisional parameters, no accuracy claim |
| Event UI | PASS | Real local result; mocked failure tests | Default journey, no technical controls, errors; browser review | New remote processing/authentication not orchestrated here |
| Independent spatial comparison | PASS | Real INDECI polygons | Category logic and end-to-end fixtures | Unknown reference dates, completeness and sensor independence |
| Scientific flood footprint | DRAFT | Real satellite-derived experimental result | 2,324.84 ha; sensitivity 758.84–5,273.24 ha | Substantial reference-only extent; no validated accuracy |

See [full v0.3 assessment](PIURA_2017_EVENT.md). The previous v0.2 checkpoint and execution history are preserved below.

# FloodLab v0.2 implementation and validation status

## Result selection correction — 2026-09-20 UTC

A separate new plan (`9ad09067-e319-46df-8b27-0848064f82af`) used empty resource options and failed with the original Orfeo memory allocation error in job `j-2609200255354d20b00a591aa9e0c2fe`. The completed resource-configured pair (`1aa75169-0fca-435b-b97e-8abb27a0d86f`) remains intact; its engineering PASS checkpoint is unchanged.

The UI now lists completed matching plans first, includes their runtime status in each label, and replaces execution instructions with a view-results message for completed plans. The Piura configuration now uses the resource options proven by the successful pair for future plan preparation. Existing plans and their evidence are unchanged. No remote jobs were submitted for this correction. Resource settings do not guarantee success for other workloads.

Validation: full pytest suite 69 passed; Ruff passed. Refresh the app and choose the completed QC WARNING plan to view its previews without authentication or further processing.

## Completed processing checkpoint — 2026-09-20 UTC

Authenticated execution completed at 02:34:43 UTC with runtime state `QC WARNING`. Both existing jobs were reused. The saved provenance contains both output checksums, and independent local checksum verification matches both files. No additional processing retry is needed.

| Component | Status | Real/Mocked | Tests | Limitations |
| --- | --- | --- | --- | --- |
| CDSE pair execution, download and provenance | PASS | Real authenticated jobs and backscatter rasters | Completed run; both SHA-256 checksums verified | Exact source-product lineage unavailable in saved result metadata |
| Pair numeric QC | PASS | Real March 11 / April 4 requested pair | Same grid; footprint overlap 100%; common valid positive pixels 99.8017%; no alignment required | Numeric QC does not establish scientific accuracy |
| Recovery implementation | PASS | Real recovered run plus mocked fault tests | Latest code suite: 69 passed; Ruff passed | Not all remote/network failures can be reproduced locally |
| Exact source identity and relative orbit | DRAFT | Catalogue candidates and real backend requests | Provenance retains expected IDs and warnings | Backend source IDs empty; actual input orbit not independently verified |
| Flood interpretation and mask validation | DRAFT | No validated flood mask | No accuracy claim | Event chronology, SAR quality review, masking and independent reference validation remain |

The engineering checkpoint for the real backscatter pair is PASS. Runtime `QC WARNING` is retained honestly: exact product lineage/relative orbit are unverified, zero values are conservatively excluded, and event interpretation/scientific accuracy remain unvalidated. The one-second timestamp warning is a general request limitation; it did not prevent this run from producing outputs. No component is FROZEN.

Best next milestone: verify the input source lineage and flood-event chronology, and visually review both backscatter rasters before defining or validating a flood classifier. This checkpoint does not authorize or claim a validated flood footprint.

The earlier entries below are historical; their incomplete-run status is superseded by this checkpoint.

## Local file recovery update — 2026-09-20 UTC

The latest run failed with PermissionError during the later download phase. The precise failing operation was not recorded. Subsequent local checks found a complete 41,573,020-byte later staging TIFF; every raster block is readable. Directory write/rename/delete probes succeeded. A transient Windows file lock is plausible, but its owner/cause is unconfirmed.

Recovered this file as `later.tif` without network access or remote job changes. An ignored `later.pending.json` records its SHA-256, saved later job association and explicit local-recovery origin; the remote asset key and source identity were not independently verified. The next authenticated execution reconciles the asset key and completes normal provenance. It can reuse both local rasters by checksum. State remains FAILED as the historical execution outcome until that run finishes.

Local real pair QC saved in `local-pair-qc.json`: matching EPSG:32717 20 m grids, footprint overlap 1.0, common positive valid fraction 0.9980169688, numeric QC PASS. Both rasters have one VV band and zero nonfinite/unmasked nonpositive pixels. This is an engineering data-quality result, not validation of a flood mask or source lineage.

File promotion now retries PermissionError five times with bounded backoff. A durable staging receipt prevents a rename/receipt-write failure from forcing a new transfer. Sanitized errno/winerror fields aid future diagnosis. No credentials or downloaded data are tracked by Git.

| Component | Status | Real/Mocked | Tests | Limitations |
| --- | --- | --- | --- | --- |
| Real pair numeric QC | PASS | Real downloaded CDSE rasters | Every block read; common valid coverage and grids checked | Source identity and event interpretation unvalidated |
| File-lock recovery | PASS | Real local recovery; mocked lock regression | Full suite: 69 tests passed; Ruff passed | Lock cause unconfirmed |
| End-to-end run and provenance | DRAFT | Real jobs and rasters | Local QC complete | Fresh authenticated metadata reconciliation still required |

This update supersedes the incomplete-later-download status below. Resume the same plan; do not create another processing retry.

## Download recovery update — 2026-09-20 UTC

The resource retry reached raster downloads for both saved jobs: earlier `j-2609200206284924b65ebc468a9f71dd` and later `j-2609200210494a36874b3e6aaf61ff02`. The worker downloads only after observing remote `finished`; this is local execution evidence, not a new live status check. The earlier raster is 41,569,781 bytes and readable; `later.download` contains only 10,000,000 bytes after `ChunkedEncodingError`. This failure occurred during transfer, rather than authentication or the previously diagnosed Orfeo memory failure.

Earlier raster QC: 2773 x 3319 pixels, one VV band, EPSG:32717, 20 m grid, valid positive fraction 0.9980169688, zero nonfinite or unmasked nonpositive pixels, nodata value 0. The later raster and pair QC remain unverified. These are backscatter data, not a flood footprint.

Download recovery now retries transient connection/timeout/chunked-stream failures three times, restarting each transfer from zero with a fresh results lookup. All raster blocks must be readable before atomic promotion. A completed-file receipt binds the checksum to job ID and asset key, allowing safe reuse after a later failure. Files from older runs without receipts are downloaded once again to establish this binding. Errors identify the failed phase without exposing raw URLs or credentials. Saved remote jobs are reused; finished jobs are not restarted.

| Component | Status | Real/Mocked | Tests | Limitations |
| --- | --- | --- | --- | --- |
| Download recovery | PASS | Real transfer implementation; mocked interruption tests | Full suite: 67 passed | Live recovery still requires user login |
| Earlier backscatter output | PASS | Real CDSE output | Full raster read and numeric QC | Exact source lineage and flood interpretation remain unvalidated |
| Complete pair and scientific validation | DRAFT | Later transfer incomplete | Pair recovery covered with fixtures | Await later raster, pair QC and provenance |

Resume the existing plan with the command below. It reuses both saved jobs. No new plan or remote processing retry was prepared for this transfer failure.

```powershell
.\.venv\Scripts\python.exe scripts/process_pair.py --plan "data\cache\openeo\1aa75169-0fca-435b-b97e-8abb27a0d86f\plan.json"
```

The entries below are historical and superseded by this update where their execution status differs.

## Resource retry update — 2026-09-20 UTC

Read-only diagnostics now establish the baseline failure: Orfeo Toolbox/ITK could not allocate image memory while processing the expected March 11 VV COG product. The final `Too many soft errors (0.25 > 0.1)` was a consequence. This is evidence that the expected baseline product reached SAR processing, not evidence of a successfully calibrated output. No later job was created.

Added validated, serialized resource `job_options`, forwarded to openEO `create_job`; legacy plans retain backend defaults. Created a separate resource-only retry at `data/cache/openeo/1aa75169-0fca-435b-b97e-8abb27a0d86f/plan.json`. The original failed plan, job ID and diagnostic file are preserved. The retry explicitly links to them and starts with an empty job map.

Retry options: `python-memory=8G`, `executor-memory=2G`, `executor-memoryOverhead=2G`, `executor-cores=1`, `task-cpus=1`, `max-executors=2`. The memory request is a proposed remedy, not proven sufficient or guaranteed accepted. No job was submitted during preparation. AOI, pair, one-second temporal intervals, bands, coefficient, DEM, output grid, resampling and soft-error threshold are unchanged. The soft-error threshold is not relaxed and missing tiles are not accepted as successful output.

The [official CDSE job configuration documentation](https://documentation.dataspace.copernicus.eu/APIs/openEO/job_config.html) identifies python-memory as the memory allocation used for SAR backscatter tasks. The retry increases per-task resources while limiting worker count; actual credit consumption is backend-dependent.

Validation: **65 tests passed in 9.93 s**, including option forwarding/validation and preservation of old evidence and identical process graphs across a resource-only retry. Backend audit remains **DRAFT** until successful authenticated processing and QC.

Run the following from the repository root and complete a fresh CDSE device login:

```powershell
.\.venv\Scripts\python.exe scripts/process_pair.py --plan "data\cache\openeo\1aa75169-0fca-435b-b97e-8abb27a0d86f\plan.json"
```

This command creates new retry jobs after authentication and may consume CDSE credits. Do not use the old failed plan as the retry. Future terminal failures automatically save redacted job errors for review.


## Latest execution update — 2026-09-20 UTC

This update supersedes the initial unauthenticated handoff recorded below. The user's terminal shows successful OIDC authorization on two attempts after an initial device-login timeout. Local state records baseline job `j-2609200149524d28a29c3e08c8b7c1b3`, no later job, and FAILED. The worker's terminal-job branch raises the reported RuntimeError for error/canceled status. Re-running retained the same job ID; it did not submit a fresh baseline job.

The underlying remote error is **not yet known**: the old handler discarded the message and no access token was persisted. Added `--diagnose`, which authenticates for read-only status/error-log retrieval and never creates or starts jobs. Backend log messages have URLs, bearer/JWT tokens and common credential fields redacted before storage/display in ignored `job-errors.json`. Future terminal-job failures preserve these diagnostics automatically. Raw authentication/HTTP exception text remains excluded.

Validation after this fix: **58 tests passed in 11.26 s**, including read-only/no-resubmission, terminal failure reporting, redaction and unavailable-log handling. Ruff and compileall passed. Backend remains **DRAFT**; no successful raster output has been established. A fresh user device login is required to retrieve the private job errors and determine the processing fix. No speculative scene/filter change or new processing job was made during diagnosis.


STAGE: First CDSE openEO processing path and Piura pair
VERSION: 0.2.0
STATUS: DRAFT
PURPOSE: Produce and inspect real analysis-ready backscatter after explicit user authentication; never claim a validated flood extent.
INPUTS: Real Piura STAC inventory, runtime openEO capabilities, user-selected compatible pair, CDSE OIDC session.
OUTPUTS: Implemented pair plans/process graphs/job lifecycle, cached raster outputs after execution, QC and provenance, UI previews.
ASSUMPTIONS: Authentication, actual jobs, output lineage and real-raster QC remain unverified until the user completes device login and execution.
TEST STATUS: 54 local tests passed; public capabilities and both selected-pair graphs validated. No authenticated job was submitted.

**Backend audit status remains DRAFT.** Public connectivity and mocked tests do not qualify it for PASS. Nothing is FROZEN. The existing v0.1 engineering PASS components remain PASS within their original scope.

## Baseline and local verification

- Began from clean committed v0.1 `062bf7a` (FloodLab v0.1 — EO foundation and Piura catalogue). Ran the unchanged test suite **before modifications: 35 passed in 2.76 s**. The historical validation report is preserved in `STATUS_v0.1.md`; its zero-commit statement describes that earlier review, not the current repository.
- Final complete suite: **54 passed in 8.78 s**. New tests mock openEO and use synthetic GeoTIFFs; no test authenticates, downloads satellite products or consumes processing credits.
- Tests cover capabilities, OIDC state/no token storage, submission guards, orbit/band/coverage compatibility, explicit graphs, QC/nodata/preview scaling, grid mismatch/alignment, provenance checksums, failure redaction, resume without duplicate submission, runtime-path constraints and the UI plan/authentication handoff.
- Bootstrap: all standard runtime directories OK.
- Import check: **18 package modules** imported; compileall passed. Streamlit emits its expected bare-mode import warning outside a session.
- Ruff checks and formatting checks passed; dependency consistency check passed. Editable package metadata updated to 0.2.0 with openEO 0.52.0 and Rasterio 1.5.1 in this environment.
- Independent Streamlit startup on localhost port 8502 returned `/_stcore/health` **HTTP 200, ok**. The owned smoke process was stopped afterward. AppTest executes the app and new plan workflow independently of that health check. No real-output visual inspection is possible before processing produces rasters.
- Public validation initially exposed a backend requirement for UTC timestamps ending in `Z`; this was fixed and both graphs revalidated. A UI regression test exposed GeoJSON tuple/list comparison after persistence; recovery now compares actual geometries.
- Git inspection: generated plans/capability records remain ignored under `data/cache/openeo`; startup logs remain under ignored `outputs`. No credential/token files or satellite products are tracked. `.openeo` and token-cache patterns are additionally ignored. No credentials were obtained or saved. No new commit/push was performed.

## Validation matrix

| Component | Status | Real / mocked | Tests | Limitations |
|---|---|---|---|---|
| v0.1 AOI/configuration/STAC/manifest foundation | PASS | Existing real implementation; live CDSE inventory | Original 35 tests retained | Original scientific limits unchanged |
| Pair comparability | PASS | Real live footprints/metadata; synthetic rejection tests | Orbit/direction/mode/bands/order/geodesic coverage | Date interpretation remains unvalidated; footprint is not valid-raster coverage |
| Public openEO discovery | PASS | Real public CDSE services | Runtime process, collection, DEM, format, OIDC checks | Advertised capability is not proof of execution |
| Process graph construction | PASS | Real graphs accepted by public validator | Explicit single sigma0 process, DEM, UTM grid and temporal filters | Exact source ID/relative-orbit filtering is not established |
| Authenticated openEO backend | DRAFT | Implemented real client; tests mock login/jobs | State, no persistent refresh token, errors and submission checks | User device authentication and actual jobs not performed |
| Job download/provenance pipeline | DRAFT | Implemented real job APIs; synthetic result tests | Checksums, native/aligned QC, resume and state files | Real job output structure, availability and lineage unverified |
| Raster QC/alignment | PASS | Real Rasterio numerical implementation, synthetic fixtures | Masks, zeros/nonfinite values, statistics, overlap, explicit warp | No real satellite-output QC yet; sampling and CRS assumptions documented |
| Flood Lab plan/state/preview UI | PASS | Real app; deterministic AppTest | Existing navigation plus new plan creation/auth handoff | Preview tested with synthetic arrays only; real output pending |
| Flood classification/history | DRAFT | Existing experimental algorithms | Existing tests retained | Not invoked by v0.2 processing; no flood footprint or real indicator series |
| Watch/Impact | DRAFT | Unchanged shells/interfaces | Existing checks retained | No new monitoring, exposure or loss functionality |
| Environmental Context v0.5e | PASS | Verified local Copernicus DEM and HydroRIVERS assets; ESA CCI 2017 land cover explicitly unavailable pending a verified subset | Asset/variable lineage, states, cache invalidation, native summaries, H3 sidecar, ZIP/checksum and import-isolation tests | DRAFT context only; DSM slope and mapped-reach distance are not HAND, causation, hazard, exposure or impact |
| Environmental H3 multi-resolution | PASS | Independently aggregated verified native context; R7 event/city sidecar and R4 overview policy | Polygon-reference equivalence, explicit resolution, deterministic output, resolution cache key and H3 join tests | H3 is derived context only; native grids remain authoritative and pixel-centre treatment can leave a small AOI-edge remainder explicitly unrepresented |

## Public backend evidence

Checked on 2026-09-19 without authentication or processing submission:

- Configured endpoint: `https://openeo.dataspace.copernicus.eu`.
- Resolved API: `https://openeo.dataspace.copernicus.eu/openeo/1.2/`; API **1.2.0**.
- Backend version: **0.73.0a17.dev20260915+72**; full advertised capabilities saved locally.
- `SENTINEL1_GRD`, requested `VV`, `COPERNICUS_30`, GTiff output and OIDC providers confirmed.
- Required processes confirmed: load_collection, sar_backscatter, resample_spatial, filter_spatial, save_result and eq.
- SAR coefficient enum advertises **sigma0-ellipsoid**. The process describes linear-scale output and bilinear DEM/backscatter interpolation via Orfeo Toolbox.
- Selected earlier and later graph validation responses: **[] and []** (no validation errors).
- These are real service responses. There are **no real processed rasters**, no real job IDs and no authenticated execution results to report.

Official references: [CDSE radar ARD example](https://documentation.dataspace.copernicus.eu/notebook-samples/openeo/Radar_ARD.html), [OIDC authentication](https://documentation.dataspace.copernicus.eu/APIs/openEO/authentication.html), [processing implementation notes](https://documentation.dataspace.copernicus.eu/APIs/openEO/openeo_processing.html).

## Piura pair review

AOI and date search remain the v0.1 demonstration: longitude -80.95 to -80.45, latitude -5.65 to -5.05, WGS84, March 1–April 30, 2017. The label remains **DEMO AOI — NOT AUTHORITATIVE FLOOD EXTENT**. A fresh real STAC query returned the same ten acquisitions. Thirteen pair combinations passed the configured 80% common-footprint threshold and metadata requirements.

| Candidate earlier → later | Series | Common AOI footprint | Interpretation |
|---|---|---|---|
| **March 11 → April 4** | Sentinel-1B, ascending relative orbit 91, IW, VV (both also advertise VH) | 100% | Prepared primary temporal hypothesis; same platform/geometry, wider baseline separation |
| March 23 → April 4 | Sentinel-1B, ascending relative orbit 91, IW, VV | 100% | Technically strong shorter-gap alternative; earlier date may already be affected, unverified |
| March 20 → April 13 | Sentinel-1B, descending relative orbit 40, IW, VV | 100% | Separate same-platform series; later date may represent a different event phase, unverified |
| March 20 → March 26 | Sentinel-1B → Sentinel-1A, descending relative orbit 40, IW, VV | 100% | Cross-platform warning; not selected merely because the dates are close |
| March 20 → either April 1 scene | Descending relative orbit 40, IW, VV | 40.8% / 59.2% | Individually rejected below 80%; no silent swath mosaic |

These are **satellite comparability assessments, not independent flood-timing evidence**. Independent event evidence has not been incorporated, so no candidate can yet be called the scientifically established pre-flood/during-flood pair. The primary hypothesis is configurable in `[pair_demo]`; generic ranking uses coverage/platform before time gap. Ascending and descending series are never mixed into a compatible pair.

Prepared primary candidate product IDs:

- Earlier: `S1B_IW_GRDH_1SDV_20170311T234311_20170311T234336_004667_008247_7495_COG`, `2017-03-11T23:43:11.173270Z`.
- Later: `S1B_IW_GRDH_1SDV_20170404T234311_20170404T234336_005017_008C6C_B798_COG`, `2017-04-04T23:43:11.844763Z`.

## Scientific limits and expected provenance

The graph calls sar_backscatter once with sigma0-ellipsoid, COPERNICUS_30 and noise removal. This configures CDSE on-demand processing; FloodLab does not recalibrate the resulting power arrays. We request DEM-based orthorectification and do **not** claim gamma0 terrain flattening. The requested output grid is EPSG:32717 at 20 m with explicit bilinear resampling for this Piura AOI.

The backend does not advertise `sat:relative_orbit` filtering. Requests use a one-second acquisition-start interval plus advertised direction/mode properties. Public validation accepts those graphs, but execution may still produce no data or use a differently indexed source. Exact source-product identity is therefore **unverified**. Expected catalogue IDs and recoverable backend source IDs are separate provenance fields. No automatic interval widening or scene substitution occurs. Multiple returned TIFFs are rejected for review.

After successful execution, provenance records the AOI, acquisition metadata, requested time/filter graph, coefficient/DEM, requested and actual CRS/resolution, nodata conventions, backend version/capabilities, processing timestamp, FloodLab version, configuration, job IDs, file checksums, native QC, any alignment, final QC and warnings. Signed result URLs and raw HTTP/auth errors are excluded. Source/date-interpretation warnings keep overall status at QC WARNING even when numerical raster QC passes.

The backend's documented zero/nodata ambiguity is retained as a warning. Validity requires mask + finite + positive linear power. Grid differences trigger recorded bilinear alignment of the later raster to the earlier one, retaining native files. No flood classification is performed. Before a scientific flood result, verify actual input lineage, valid coverage, preprocessing conventions, independent event dates and classification/reference accuracy.

## Authentication status and exact user action

**NOT AUTHENTICATED.** No login was attempted on the user's behalf; no processing resources were consumed. Run this from the repository root in a normal local terminal:

```powershell
.\.venv\Scripts\python.exe scripts/process_pair.py --plan "data\cache\openeo\d603c7c0-fa28-44d3-971d-f2c9741bdd1d\plan.json"
```

The client prints a CDSE verification URL and short device code. Open that URL in your browser, enter the code there and sign in with your CDSE account. Do not paste passwords or tokens into FloodLab/chat. Keep the terminal open. **Successful authentication causes the command to submit/resume the two reviewed jobs, which may consume CDSE credits.** It does not request/store a refresh token. If the access token expires, rerun the same command to reauthenticate and resume existing job IDs.

In Flood Lab, choose the March 11 → April 4 pair and its saved plan, then click **Refresh processing state**. The prepared plan is an ignored local runtime artifact, so a fresh clone should generate its own plan using `python scripts/check_openeo.py --prepare-demo` or the UI.

## Files changed and next milestone

Added EO modules: `pairs.py`, `openeo_backend.py`, `pair_jobs.py`, `raster.py`; UI module `ui/processing.py`; scripts `check_openeo.py`, `process_pair.py`; backend/QC tests and a UI regression test. Updated configuration, dependencies/version, ignore rules, Flood Lab integration, README, architecture, methodology, decisions and status; preserved the v0.1 report. Generic processing remains outside the flood classifier.

Immediate acceptance step: complete the above OIDC run, inspect actual rasters/QC/source lineage, and only then consider backend PASS. After that, the next engineering milestone is flood detection and validation against independent dated evidence. No component is FROZEN.
