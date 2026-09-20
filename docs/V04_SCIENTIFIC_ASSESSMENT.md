# FloodLab v0.4: Piura 2017 scientific assessment

Engineering checkpoint: PASS after the checks recorded in STATUS.md. Scientific product: DRAFT, experimental, not a validated flood extent. No component is FROZEN. No new CDSE processing was submitted; the successful v0.2 backscatter pair and original v0.3 outputs remain intact.

## What changed numerically

All areas below use pixel centres on the common EPSG:32717, 20 m grid (0.04 ha per pixel). AOI: longitude −80.95 to −80.45, latitude −5.65 to −5.05. These are raster-domain areas, not geodesic polygon survey measurements.

| Quantity | ha |
| --- | ---: |
| Total AOI | 367,413.44 |
| Terrestrial AOI | 351,474.32 |
| Ocean excluded | 15,939.12 |
| Original v0.3 experimental footprint | 2,324.84 |
| Original footprint offshore | 229.00 |
| Additional component loss after coastline clipping | 1.36 |
| Land-only SAR candidates before historical-baseline screening | 2,094.48 |
| Candidates on historical persistent/recurrent water | 116.24 |
| Candidates with uncertain historical baseline | 12.32 |
| Additional component loss after baseline screening | 44.68 |
| **Revised experimental land-only footprint** | **1,921.24** |

The arithmetic reconciles the full 403.60 ha reduction. Component cleanup is reapplied after domain changes: clipping can split connected components below the unchanged nine-pixel minimum. Zero ocean pixels contribute to the final hectares, relative to the selected coastline. Ocean is also excluded from earlier/during water, comparisons, sensitivity and terrestrial exports; it is not merely hidden on the map.

## Baseline and method

The historical baseline combines [JRC GSW VER1-0](https://global-surface-water.appspot.com/download) annual classes for 2013, 2014 and 2015 with its **1984–2015** occurrence map. It deliberately avoids summaries that include the 2017 event or later years. Source: EC JRC/Google; Pekel et al. (2016), doi:10.1038/nature20584. Public extracts, exact URLs, versions, retrieval times and SHA-256 hashes are packaged.

Annual history is sparse outside its classified water-history domain. Annual code 0 remains unknown. The separate occurrence map's explicit code 0 means mapped not-water; code 255 means no data. Those meanings are distinct in the [publisher's data guide](https://storage.googleapis.com/global-surface-water/downloads_ancillary/DataUsersGuidev2.pdf). Only explicit occurrence=0 resolves an otherwise unknown baseline to historically non-water. Positive long-term occurrence alone does not establish recurrent/permanent water, and missing data are never filled as dry.

| Baseline class | Rule | Land area, ha |
| --- | --- | ---: |
| Historically non-water | Every annual class is non-water, or annual history incomplete and historical occurrence explicitly zero | 343,410.24 |
| Recurrent/seasonal water | Water in any selected annual map, excluding persistent class | 6,448.40 |
| Persistent water | Permanent in every selected annual map | 982.12 |
| Uncertain | Remaining incomplete/unknown history | 633.56 |

This is a historical water baseline, **not** a calibrated March climatology, proof of dry conditions in early 2017, or a multi-date SAR backscatter baseline. Annual “permanent” is relative to valid source observations. Water changes during 2016–early 2017, short inundations, vegetation and 30 m mixed pixels remain limitations. March 11 stays a separately exported earlier observation. Conservative exclusion of recurrent-water pixels can omit event-related expansion within those pixels; their SAR evidence is retained separately.

The SAR thresholds are unchanged: April 4 VV sigma0-ellipsoid ≤ −18 dB, earlier observation above −18 dB, decrease of at least 3 dB, and four-connected components of at least nine 20 m pixels. The final footprint additionally requires valid land and historically non-water baseline. The fixed threshold is provisional, not inferred from a rating curve or scientifically calibrated baseline distribution. The v0.3 pooled Otsu diagnostic is retained in provenance, but does not choose the deployed threshold.

On land, **17,419.04 ha** of April 4 classified water was also classified water on March 11. **4,538.32 ha** overlaps historical persistent/recurrent water. These quantities overlap and must not be summed. Total April 4 classified terrestrial water is **32,472.08 ha**, substantially greater than the new-inundation estimate.

## Independent optical evidence

The preparation script searches the public Earth Search Sentinel-2 L2A catalogue, follows pagination and automatically chooses a date within each configured window using scene cloud metadata. It then evaluates actual pixels. The cached search contains 34 items for January 1–April 6. Selected dates are January 10 and March 31, with tiles 17MNQ, 17MNP, 17MMQ and 17MMP. Exact L2A product identifiers and asset metadata are in optical provenance.

Water classification uses MNDWI = (green − SWIR1)/(green + SWIR1) > 0. Reflectance scale/offset are applied; continuous bands are bilinearly aligned and SCL uses nearest neighbour. Only SCL 4/5/6 are eligible; cloud, shadow, defective and snow pixels are excluded with a 60 m (three-pixel, four-neighbour dilation) buffer. Unclassified, saturated, nonpositive and invalid data remain unavailable. This is an experimental fixed optical threshold, not locally calibrated truth.

March 31 has only **7,579.56 ha** usable terrestrial coverage, of which **742.60 ha** is classified water. January/March common clear coverage is **7,254.60 ha (2.064%)**. The configured 5% threshold triggers a limited-coverage warning; it does not discard useful clear pixels. The four-day difference from April 4 is within the configured seven-day matching tolerance, but is explicitly retained as a temporal mismatch.

| Evidence state on historically non-water land | ha |
| --- | ---: |
| SAR footprint + optical supporting change | 0.04 |
| SAR footprint, optical unavailable | 1,920.84 |
| SAR footprint, optical disagreement | 0.36 |
| Optical change without corresponding final SAR evidence | 36.36 |

Optical and radar masks are not unioned. A one-pixel agreement is weak support, not independent validation of the footprint. Disagreement may reflect timing, cloud-screening error, water-index error or radar limitations. Missing, corrupt or fully cloudy optical inputs leave SAR analysis available with an explicit unavailable state.

## Geographic and hydrological plausibility

Land is rasterized from full-resolution level 1 [GSHHG 2.3.7](https://www.ngdc.noaa.gov/mgg/shorelines/shorelines.html), using the official GMT distribution and verified archive SHA-256. Level 1 retains inland water within the terrestrial analysis domain. Its historical shoreline is not guaranteed accurate to 20 m; tides, coastal change and mixed coastal pixels remain uncertain. Numerical zero-ocean contamination is relative to this mask, not a claim of perfect shoreline truth.

[HydroRIVERS v1.0 South America](https://www.hydrosheds.org/products/hydrorivers) supplies 178 clipped river features with upstream-area and basin-link attributes. Median distance of footprint pixels to the mapped reaches is **835 m**, with 90th percentile **2,234 m**. Copernicus GLO-30 DSM context gives median elevation **15.41 m** and median slope **0.85°**. The low, gently sloping terrain near mapped drainage is consistent with floodplain inundation; it does not prove hydraulic connectivity or validate individual detections. No river-distance or slope exclusion is applied. Small unmapped channels, buildings/vegetation in the DSM, its non-2017 epoch, and local drainage structures limit interpretation. HAND and flow routing have not been implemented; doing so needs hydrologically conditioned terrain and validation.

Gauge integration is **discovery only**. The Puente Sánchez Cerro station on the Piura is located from a [SENAMHI study](https://www.senamhi.gob.pe/load/file/01401SENA-92.pdf), with rounded published coordinates and the study identifier explicitly distinguished from a verified API identifier. No authoritative machine-readable March–April 2017 hydrograph or date-valid rating curve was retrieved. No discharge, travel-time correction, peak or recession phase is invented. The observation schema requires station/provider/source, timestamp/timezone, units and quality; stage-derived discharge requires rating-curve provenance. Missing or malformed optional records do not block satellites.

## Why the INDECI-only region remains large

The same 37,035-feature [INDECI service](https://geosinpad.indeci.gob.pe/indeci/rest/services/SIRAIM/SDE_areasInundadasPiura2017/MapServer/0) is compared on valid land. It has no usable observation dates, surveyed dry-domain mask or sufficiently detailed production methodology. Geometry repair and AOI clipping before projection match v0.3; reference-domain area reconciliation is checked. It cannot be assumed to represent April 4, maximum extent, or independently verified ground truth. Reference offshore overlap is only **22.68 ha**: coastline contamination cannot explain the large reference-only region.

| Descriptive comparison | v0.3 ha | v0.4 ha |
| --- | ---: | ---: |
| Agreement | 1,076.24 | 945.60 |
| Possible omission | 37,844.56 | 37,952.52 |
| Possible commission | 1,248.60 | 975.64 |

The following mutually exclusive buckets describe classification conditions in the v0.4 possible-omission region, in the order shown. They are not established physical causes:

| Condition | ha |
| --- | ---: |
| Historical persistent/recurrent water | 6,702.84 |
| Uncertain historical baseline | 503.76 |
| Already classified water on March 11 | 10,982.88 |
| Not dark enough on April 4 | 17,365.76 |
| Insufficient decrease | 975.64 |
| Component cleanup / remaining | 1,421.64 |

This shows two major constraints: pre-existing/earlier water and the April 4 dark-water criterion. Different reference timing and maximum-versus-residual extent are plausible but unproven explanations. Vegetation, urban double-bounce, shallow water, wind, mixed pixels and classification error can explain radar nondetection, but these causes cannot be separated from two VV images alone. The reference-only region is concentrated south of the raster midpoint: southeast 23,478.36 ha, southwest 8,470.84 ha, northeast 4,954.40 ha and northwest 1,048.92 ha. Its median DSM elevation is 9.95 m, slope 0.72° and mapped-river distance 880 m. These low-lying areas are hydrologically plausible; they should not be dismissed as errors solely because the SAR change rule missed them. No threshold was fitted to INDECI. A dated reference with mapped negative observations, additional event-date imagery and land-cover stratification are the next validation needs.

## Sensitivity, QC and remaining uncertainty

The unchanged nine combinations of water threshold −20/−18/−16 dB and decrease −2/−3/−4 dB produce **627.64–5,025.96 ha** after land and historical-baseline exclusion. This is parameter sensitivity, not a confidence interval or probability. Source lineage remains a warning: real CDSE outputs exist and numeric pair QC passes, but exact backend input product identity/relative orbit was not independently verified from result metadata.

All primary rasters use the same CRS, transform and dimensions. Flood vector geometry is exported in WGS84 and independently reprojected to compare its area with the raster (tolerance one pixel, 0.04 ha). Archive CRCs, payload SHA-256 hashes and PNG readability are checked. Root-level derived rasters exclude ocean; native reference extracts in `context_sources/` retain source encodings for audit. The UUID analysis directory is never overwritten by the application; this is application-level immutability, not write-protected archival storage.

The event timeline distinguishes historical baseline, January 10 optical, March 11 radar, March 27 documented escalation, March 31 optical and April 4 continuing inundation. Additional catalogue dates are shown as unprocessed observations, not reconstructed intermediate flood states. No peak footprint, recession curve, validated accuracy, calibrated probability or flood depth is claimed.

## Reproduce and inspect

Run from the repository root with the existing verified SAR pair available:

```powershell
.\.venv\Scripts\python.exe scripts/bootstrap.py
# Public-data preparation, only needed when extracts/inventories are absent:
.\.venv\Scripts\python.exe scripts/prepare_v04_context.py
.\.venv\Scripts\python.exe scripts/prepare_v04_optical.py
# Local analysis; never submits CDSE jobs:
.\.venv\Scripts\python.exe scripts/reconstruct_piura.py
.\.venv\Scripts\python.exe scripts/validate_v04.py outputs/analyses/<analysis_id>
```

Preparation is parameterized by `config/v04.json` but currently requires the AOI to fit the downloaded source tiles and prepared context. Arbitrary global event automation is out of scope. Network/catalogue discovery is server-side operator preparation; the consumer page uses verified cached evidence. The main journey remains AOI → Analyse → Before/During/Flood footprint → Evidence/timeline → Download complete analysis. Original March 11 water, optical water, rivers and uncertain baseline remain inspectable. Scientific parameters and full provenance are in the advanced expander.

Each package includes flood/SAR/optical masks, historical and categorical baseline, evidence classes, comparison masks, polygons, geographic PNG overlays, a three-panel comparison, native context extracts, rivers, aligned DSM/slope, catalogue/product provenance, gauge discovery, summary CSV, methodology, README and checksums. Large original SAR products remain in the verified local cache with identifiers, processing provenance and input checksums recorded.

## v0.4 changed-file inventory

Existing v0.2/v0.3 uncommitted files were preserved. The files introduced or edited for this upgrade are:

- `config/v04.json`, `config/piura-gauges.json`
- `src/floodlab/__init__.py`, `pyproject.toml`
- `src/floodlab/eo_core/context.py`, `gauges.py`, `public_stac.py`
- `src/floodlab/hazards/flood/evidence.py`, `reconstruction.py`
- `src/floodlab/ui/event.py`, `main.py`
- `scripts/prepare_v04_context.py`, `prepare_v04_optical.py`, `reconstruct_piura.py`, `validate_v04.py`
- `tests/test_reconstruction.py`
- `README.md`, `docs/ARCHITECTURE.md`, `docs/STATUS.md`, this assessment, and `docs/V04_OUTPUT_CHECKSUMS.json`

Downloaded products, test scratch files and generated analyses are Git-ignored. Nothing was committed or pushed.


## Reviewed output

Analysis ID: `3c236bb0-0c6c-4d69-b6f0-ca604bbb84c3`; runtime folder `outputs/analyses/3c236bb0-0c6c-4d69-b6f0-ca604bbb84c3/`.

ZIP SHA-256: `7aee27e85fe440b8790135ef4056d79a2524ed0c00f9e1a2e2eb979790de71de`.

See [full output checksums](V04_OUTPUT_CHECKSUMS.json) and [executed validation matrix](STATUS.md). Preliminary development packages remain preserved but are superseded by this reviewed analysis. Fresh analyses receive new UUIDs and package hashes even when the scientific masks are identical.
