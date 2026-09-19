# Engineering decisions

STAGE: Foundation | VERSION: 0.1.0 | STATUS: DRAFT
PURPOSE: Record scope and scientific boundaries.
INPUTS: FloodLab v0.1 requirements and CDSE documentation.
OUTPUTS: Reversible architectural decisions.
ASSUMPTIONS: Future backends will require separate acceptance.
TEST STATUS: See STATUS.md.

1. Use a Python src layout and Streamlit to provide an inspectable research-to-product foundation. UI, EO infrastructure and numerical algorithms remain separate.
2. Use public CDSE STAC via pystac-client. Endpoint and collection remain configurable, are verified at runtime, and discovery is capped rather than downloading unbounded history. No fake observations are substituted on failure.
3. Define product-access and preprocessing interfaces without pretending to implement calibrated SAR processing. COG storage is not proof of analysis readiness.
4. Use SciPy for component cleanup and implement a small histogram Otsu routine; avoid requiring a raster processing stack before a backend is selected.
5. Preserve scientific uncertainty in result structures and job status. Synthetic tests verify implementation, not real-world flood accuracy.
6. Use a rectangular, explicitly labelled Piura demo search window. Support global WGS84 polygons; require dateline splitting instead of guessing polygon intent.
7. Impact is a contract only. Watch is an architectural shell. No exposure or financial modelling is included.
8. Use typed dataclasses plus explicit validation; configuration uses standard-library TOML. Runtime folders are created idempotently and user data is never deleted.

Source checked 2026-09-19: [CDSE STAC product catalogue](https://documentation.dataspace.copernicus.eu/APIs/STAC.html). Current configured endpoint is `https://stac.dataspace.copernicus.eu/v1`; collection `sentinel-1-grd`. Runtime verification is authoritative if a provider later changes its catalogue.
