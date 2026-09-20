"""Fetch public Piura reference polygons; no authentication or processing jobs."""

import json
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://geosinpad.indeci.gob.pe/indeci/rest/services/SIRAIM/SDE_areasInundadasPiura2017/MapServer/0"
p = ROOT / "data/cache/references"
p.mkdir(parents=True, exist_ok=True)
params = {
    "f": "json",
    "where": "1=1",
    "geometry": "-80.95,-5.65,-80.45,-5.05",
    "geometryType": "esriGeometryEnvelope",
    "inSR": 4326,
    "spatialRel": "esriSpatialRelIntersects",
    "returnIdsOnly": "true",
}
r = requests.get(URL + "/query", params=params, timeout=60)
r.raise_for_status()
ids = r.json()
if "error" in ids or not ids.get("objectIds"):
    raise ValueError("Reference query failed or empty")
features = []
for start in range(0, len(ids["objectIds"]), 100):
    response = requests.get(
        URL + "/query",
        params={
            "f": "geojson",
            "objectIds": ",".join(map(str, ids["objectIds"][start : start + 100])),
            "outFields": "*",
            "outSR": 4326,
        },
        timeout=90,
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data or data.get("exceededTransferLimit"):
        raise ValueError("Incomplete reference response")
    features.extend(data["features"])
if len(features) != len(ids["objectIds"]):
    raise ValueError("Reference feature count mismatch")
(p / "indeci-piura2017.geojson").write_text(
    json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
)
(p / "reference-provenance.json").write_text(
    json.dumps(
        {
            "url": URL,
            "retrieved_utc": datetime.now(UTC).isoformat(),
            "feature_count": len(features),
            "query": params,
            "limitations": "Service has no observation dates, mapped nonflood coverage, accuracy or detailed methodology. Independent publisher; underlying sensor independence unverified. Spatial agreement is descriptive, not validation accuracy.",
        },
        indent=2,
    ),
    encoding="utf-8",
)
print("Reference polygons:", len(features))
