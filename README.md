# FloodLab v0.5 Release Candidate

FloodLab is an auditable Earth-observation foundation organised as EO Core → Hazard Intelligence → Risk Applications. Its Piura 2017 reference workflow is **DRAFT scientific evidence**, not a validated flood, damage, loss, or causal model.

## Piura 2017 reference case

FloodLab uses real processed Sentinel-1 observations to reconstruct separate ascending and descending event sequences. The maximum **satellite-observed single-date** inundation is 6,328.76 ha on 26 March 2017. The 10,666.64 ha event-observed temporal union is area observed inundated at least once; it is not simultaneous inundation or a hydrological peak. The frozen legacy pair is 1,921.24 ha.

The system preserves source/product expectations, processing plans, checksums, QC and limitations. Exact backend Sentinel-1 source lineage remains a warning, and all flood products require independent validation.

## Context, exposure and impact

Environmental Intelligence provides DRAFT elevation, DSM-derived slope and mapped-drainage-distance context from verified sources. It does not provide HAND, hydrological connectivity, causation or historic land cover; the selected 2017 land-cover layer remains explicitly unavailable pending a verified subset.

Impact Intelligence accepts generic hazard geometry. Overture mapped-building intersections are modern contextual geometric exposure only, not proof that buildings existed in 2017, were inundated, damaged or destroyed. H3 is derived aggregation/indexing: native scientific rasters and vectors remain authoritative.

## Run and validate

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts/bootstrap.py
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src scripts tests
```

Runtime caches, credentials, satellite products and generated packages are intentionally ignored by Git. CDSE device authentication occurs in the browser; never paste credentials or tokens into FloodLab.

Read [status](docs/STATUS.md), [architecture](docs/ARCHITECTURE.md), [methodology](docs/METHODOLOGY.md), and the [environmental data register](docs/ENVIRONMENT_DATA.md) before interpreting outputs.
