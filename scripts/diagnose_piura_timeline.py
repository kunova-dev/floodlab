"""Read-only CDSE STAC chronology diagnostic; never submits or processes imagery."""

import json
from datetime import UTC, datetime
from pathlib import Path

import requests
from pyproj import Geod
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://stac.dataspace.copernicus.eu/v1/search"
START = "2017-01-01T00:00:00Z"
END = "2017-04-30T23:59:59Z"


def event_window(value):
    day = value[:10]
    if day <= "2017-03-15":
        return "BASELINE"
    if day <= "2017-03-24":
        return "PRE-EVENT / ESCALATION"
    if day <= "2017-03-31":
        return "CORE EVENT WINDOW"
    if day <= "2017-04-10":
        return "EARLY RECESSION / CONTINUING INUNDATION"
    return "LATE RECOVERY"


def role(window):
    return {
        "BASELINE": "BASELINE_CANDIDATE",
        "PRE-EVENT / ESCALATION": "PRE_EVENT",
        "CORE EVENT WINDOW": "EVENT_CANDIDATE",
        "EARLY RECESSION / CONTINUING INUNDATION": "RECESSION",
        "LATE RECOVERY": "RECOVERY",
    }[window]


def get_any(props, *names):
    for name in names:
        if props.get(name) is not None:
            return props[name]
    return None


def search(collection, aoi):
    payload = {
        "collections": [collection],
        "intersects": aoi,
        "datetime": f"{START}/{END}",
        "limit": 100,
    }
    features = []
    url, method = ENDPOINT, "POST"
    while url:
        response = requests.request(
            method, url, json=payload if method == "POST" else None, timeout=90
        )
        response.raise_for_status()
        page = response.json()
        features.extend(page["features"])
        next_link = next(
            (link for link in page.get("links", []) if link.get("rel") == "next"), None
        )
        url = next_link.get("href") if next_link else None
        method, payload = "GET", None
    return features


def normalize(feature, mission, aoi_shape, aoi_area, geod):
    props = feature["properties"]
    timestamp = get_any(props, "datetime", "start_datetime")
    footprint = shape(feature["geometry"])
    coverage = (
        abs(geod.geometry_area_perimeter(footprint.intersection(aoi_shape))[0]) / aoi_area
        if aoi_area
        else None
    )
    window = event_window(timestamp)
    polarisation = get_any(props, "sar:polarizations", "polarization", "s1:polarization")
    if isinstance(polarisation, list):
        polarisation = ",".join(polarisation)
    relative_orbit = get_any(
        props, "sat:relative_orbit", "relativeOrbitNumber", "s1:relative_orbit"
    )
    direction = get_any(props, "sat:orbit_state", "orbitDirection", "s1:orbit_direction")
    platform = get_any(props, "platform", "sat:platform")
    product_type = get_any(props, "productType", "s1:product_type", "processing:level")
    mode = get_any(props, "sar:instrument_mode", "instrumentMode", "s1:instrument_mode")
    cloud = get_any(props, "eo:cloud_cover", "cloudCover", "s2:cloud_cover")
    sequence = None
    if mission == "SENTINEL-1":
        sequence = "|".join(str(v) for v in [relative_orbit, direction, mode, polarisation])
    return {
        "mission": mission,
        "platform": platform,
        "acquisition_datetime": timestamp,
        "acquisition_end": props.get("end_datetime"),
        "event_window": window,
        "product_id": feature["id"],
        "product_name": get_any(props, "title", "productIdentifier"),
        "product_type": product_type,
        "acquisition_mode": mode,
        "relative_orbit": relative_orbit,
        "absolute_orbit": get_any(props, "sat:absolute_orbit", "orbitNumber", "s1:absolute_orbit"),
        "orbit_direction": direction,
        "polarisation": polarisation,
        "aoi_coverage": coverage,
        "cloud_cover": cloud,
        "sequence_id": sequence,
        "potential_role": role(window),
        "limitations": "Catalogue metadata only; footprint coverage is not valid-pixel coverage."
        if mission == "SENTINEL-1"
        else "Catalogue cloud cover is scene-level, not necessarily cloud cover over the AOI.",
    }


def main():
    source = ROOT / "outputs/analyses/855dc008-898e-42ea-9dba-7aa46ee4b587/provenance.json"
    report = json.loads(source.read_text(encoding="utf-8"))
    aoi = report["aoi"]["geometry"] if report["aoi"].get("type") == "Feature" else report["aoi"]
    aoi_shape = shape(aoi)
    geod = Geod(ellps="WGS84")
    aoi_area_m2 = abs(geod.geometry_area_perimeter(aoi_shape)[0])
    out = ROOT / "outputs/diagnostics/piura_2017_satellite_timeline"
    out.mkdir(parents=True, exist_ok=True)
    collections = {"sentinel-1-grd": "SENTINEL-1", "sentinel-2-l2a": "SENTINEL-2"}
    all_rows = []
    for collection, mission in collections.items():
        raw = search(collection, aoi)
        (out / f"{collection}.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
        all_rows.extend(normalize(item, mission, aoi_shape, aoi_area_m2, geod) for item in raw)
    all_rows.sort(key=lambda row: row["acquisition_datetime"])
    (out / "timeline.json").write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    provenance = {
        "checked_utc": datetime.now(UTC).isoformat(),
        "source_analysis_id": report["analysis_id"],
        "aoi_crs": "EPSG:4326",
        "aoi": aoi,
        "bbox": aoi_shape.bounds,
        "aoi_geodesic_area_m2": aoi_area_m2,
        "query": {
            "endpoint": ENDPOINT,
            "start": START,
            "end": END,
            "collections": list(collections),
        },
        "counts": {
            mission: sum(row["mission"] == mission for row in all_rows)
            for mission in collections.values()
        },
    }
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    s1 = [row for row in all_rows if row["mission"] == "SENTINEL-1"]
    s2 = [row for row in all_rows if row["mission"] == "SENTINEL-2"]
    sequences = {}
    for row in s1:
        sequences.setdefault(row["sequence_id"], []).append(row)
    lines = [
        "# Piura 2017 satellite catalogue diagnostic",
        "",
        f"Source analysis: `{report['analysis_id']}`. AOI: EPSG:4326 bbox `{aoi_shape.bounds}`; geodesic area {aoi_area_m2:,.2f} m².",
        f"Search: {START} through {END}, inclusive. Read-only CDSE STAC metadata queries; no imagery or processing was requested.",
        "",
        f"Sentinel-1 products: {len(s1)}. Sentinel-2 products: {len(s2)}.",
        "",
        "## Sentinel-1 compatible sequences",
    ]
    for sequence, items in sorted(sequences.items()):
        lines.append(
            f"- `{sequence}`: " + ", ".join(item["acquisition_datetime"][:10] for item in items)
        )
    lines += ["", "## Core event window (25–31 March)"]
    for row in [row for row in all_rows if row["event_window"] == "CORE EVENT WINDOW"]:
        lines.append(
            f"- {row['acquisition_datetime']} | {row['mission']} | `{row['product_id']}` | {row['potential_role']}"
        )
    lines += [
        "",
        "## Existing selection",
        (
            "`config/piura2017-event.json` defines before 1–16 March and during 27 March–4 April; "
            "the configured pair demo explicitly prefers 11 March → 4 April when it is compatible and processed. "
            "The UI does not discover an event maximum. Its pair ranking is technical (coverage/platform/gap), "
            "and the event workflow only reuses an already processed matching pair."
        ),
        "",
        "Catalogue cloud cover is scene-level rather than AOI-specific cloud cover. All roles are metadata-based and do not identify a hydrological peak.",
    ]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
