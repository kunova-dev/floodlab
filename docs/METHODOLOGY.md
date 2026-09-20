# Methodology

STAGE: Experimental algorithms | VERSION: 0.2.0 | STATUS: DRAFT
PURPOSE: Honest, testable analysis-ready flood indicators and event grouping.
INPUTS: Comparable dB power grids, positive metric pixel areas, optional boolean permanent-water grid; historical fractions and an independent baseline.
OUTPUTS: Probable new inundation mask, area, QC and candidate observed-event intervals.
ASSUMPTIONS: See below; no validated universal threshold or accuracy claim.
TEST STATUS: Synthetic numerical and boundary tests; scientific validation pending.

## Backscatter and masks

`to_db` applies 10 log10 to positive finite linear power. Do not apply it to amplitude or data already in dB. Nonpositive, infinite and missing values become NaN. dB arrays passed directly to classification must encode nodata as NaN, not a numeric sentinel such as -9999.

A water candidate is finite event backscatter ≤ the configured threshold (default -17 dB). Otsu is available as a histogram-based alternative; it requires variable data and a scientifically suitable distribution. It is not automatically more accurate.

Probable new inundation requires all of: valid paired pixels, event water candidate, baseline not water, event minus baseline ≤ configured negative change (default -3 dB), and absence from an optional permanent-water mask. Four-connected components smaller than the configured pixel count are removed. No hole filling introduces detections into missing pixels. QC reports paired valid fraction and whether permanent water was supplied. Confidence is explicitly unvalidated, not a probability.

Each FloodResult separates `observed_derived`, `configuration`, `assumptions`, and `qc_confidence`; its array mask is derived evidence. Missing permanent-water data is reported, not treated as a verified dry background. A future reference-water provider should supply a aligned boolean mask with separately recorded provenance.

## Area and comparability

An affine determinant gives planar pixel area only in a suitable projected CRS with metre units. Longitude/latitude degrees are rejected. For other grids supply valid per-pixel geodesic areas computed externally. Projection distortion still requires review. Area is square metres; divide by 1,000,000 for square kilometres.

Inputs must share calibration convention, polarization, grid and comparable viewing geometry. Matching array shapes alone cannot prove registration. Metadata readiness checks report missing/differing orbit/mode fields and common polarization, but always remain AWAITING_PREPROCESSING. Processing must account for calibration, thermal/border noise, terrain correction, speckle, incidence angle, shadow/layover and invalid data. Urban/vegetated flooding can brighten rather than darken and will be missed by this first-pass method.

## History

A representative independent baseline of at least three fractions establishes median plus max(minimum excess, multiplier × 1.4826 × MAD). Defaults are a 0.02 absolute fraction excess and multiplier 3. Anomalies strictly exceed that threshold. Consecutive anomalous observations within the configured gap (12 days) form candidate episodes, even when intervening observations are below threshold. Grouping therefore expresses temporal proximity, not continuous confirmed inundation. Tied peaks choose the earliest sorted observation. Duplicate IDs and invalid fractions are rejected.

First/last anomalous observations and the sampled peak bound available evidence. Sparse sampling cannot determine exact onset, true peak or recession, and missing acquisitions are not dry observations. This engine uses synthetic series in tests; no Piura inundation series has been derived.

## Piura validation plan

1. Review AOI and event/baseline date windows with domain evidence.
2. Retrieve comparable Sentinel-1 observations and document access completeness.
3. Preprocess with a documented backend and audit all spatial/physical metadata.
4. Examine masks and sensitivity to thresholds, baseline and cleanup choices.
5. Compare against independent dated reference extents, report sampling/accuracy uncertainty and inspect false positives/negatives.
6. Only after explicit review may a scientific output become FROZEN.


## v0.2 openEO backscatter convention

Request CDSE SENTINEL1_GRD with exactly one explicit sar_backscatter process: sigma0-ellipsoid, COPERNICUS_30 elevation model and noise_removal=true. This parameterizes on-demand collection processing, not a second calibration of already processed data. Backend capability records describe Orfeo Toolbox and bilinear DEM/backscatter interpolation. We request Copernicus DEM orthorectification; gamma0 radiometric terrain flattening is not claimed. Execution and source identity remain unverified until actual authenticated job results are reviewed.

The graph explicitly resamples to a centroid-selected UTM CRS at configured 20 m resolution using bilinear interpolation and clips to the AOI polygon. Pixel spacing is not equivalent to sensor resolving power. If the returned grids differ, retain native files and explicitly warp the later raster to the earlier grid with bilinear interpolation. The alignment record and native/aligned QC remain in provenance. No difference image or flood classifier is automatically invoked.

Per-band valid pixels require the raster mask, finite values and positive linear power. The backend documents zero as both thermal-noise-removed data and nodata; excluding zero is conservative and can reduce coverage. Nodata fraction counts the raster mask; nonfinite and nonpositive counts are reported separately and may overlap it. Robust percentiles use a deterministic regular sample of at most about 200,000 pixels per band; min/max and validity counts inspect every block. Shared preview scaling uses 2nd/98th percentiles of display samples converted via 10 log10; downsampling is display-only. Extent overlap is a bounding-box metric; common valid fraction on a compatible grid provides the pixel-based counterpart. QC fractions use the output raster grid denominator, which can include area outside a nonrectangular AOI; review masks for such AOIs.

Matching catalogue footprints do not establish actual valid-pixel coverage. Matching metadata does not establish radiometric equivalence, true pre-flood conditions, or true event inundation. Relative orbit 91 ascending and 40 descending are separate series. The March 11–April 4 ascending demo hypothesis preserves platform, orbit, IW and VV with 100% catalogue-footprint coverage; date interpretation requires independent evidence.

References: [CDSE radar ARD](https://documentation.dataspace.copernicus.eu/notebook-samples/openeo/Radar_ARD.html) and [processing implementation notes](https://documentation.dataspace.copernicus.eu/APIs/openEO/openeo_processing.html). These document backend conventions, not evidence that this local implementation has completed a real processing job.
