"""Hazard-independent polygon aggregation. No hazard processors or exposure datasets."""

import json
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from typing import Literal, Protocol
from uuid import uuid4

import h3
import pyproj
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import transform, unary_union

ExposureKind = Literal[
    "buildings",
    "building_height",
    "roads",
    "population",
    "land_cover",
    "cropland",
    "irrigation",
    "critical_facilities",
]


class ExposureEnrichment(Protocol):
    """Future providers return their own sourced attributes; no providers are bundled."""

    kind: ExposureKind

    def enrich(self, analysis: "ImpactAnalysis") -> dict: ...


@dataclass
class ImpactAnalysis:
    analysis_id: str
    grid: dict
    provenance: dict

    def enrich(self, exposure_layer: ExposureEnrichment) -> dict:
        return exposure_layer.enrich(self)

    def export(self, folder):
        folder.mkdir(parents=True, exist_ok=False)
        for name, value in [("grid.geojson", self.grid), ("provenance.json", self.provenance)]:
            (folder / name).write_text(
                json.dumps(value, sort_keys=True, allow_nan=False), encoding="utf-8"
            )


def polygon_input(value, allow_empty=False):
    """Accept WGS84 GeoJSON or Shapely polygons; dissolve overlap, reject ambiguous inputs."""
    if isinstance(value, dict):
        if value.get("type") == "FeatureCollection":
            parts = [polygon_input(f, allow_empty=True) for f in value["features"]]
            geometry = unary_union(parts)
        elif value.get("type") == "Feature":
            geometry = shape(value["geometry"])
        else:
            geometry = shape(value)
    else:
        geometry = value
    if geometry.is_empty and allow_empty:
        return Polygon()
    if (
        geometry.geom_type not in ("Polygon", "MultiPolygon")
        or not geometry.is_valid
        or geometry.is_empty
    ):
        raise ValueError("Valid polygonal WGS84 geometry required")
    west, south, east, north = geometry.bounds
    if (
        not (-180 <= west < east <= 180 and -85 <= south < north <= 85)
        or east - west > 20
        or north - south > 20
    ):
        raise ValueError(
            "Use a regional non-dateline AOI within 85 degrees latitude (maximum span 20 degrees)"
        )
    return geometry


def analyse_impact(
    hazard_footprint,
    aoi,
    hazard_type,
    event_date,
    metadata=None,
    *,
    land=None,
    resolution=7,
    analysis_id=None,
    max_cells=20000,
):
    """Aggregate unioned hazard over AOI-clipped cells; terrestrial percentages require land."""
    if type(resolution) is not int or not 0 <= resolution <= 10:
        raise ValueError("H3 resolution must be an integer from 0 to 10")
    if not isinstance(hazard_type, str) or not hazard_type.strip():
        raise ValueError("A hazard type is required")
    date.fromisoformat(event_date)
    aoi = polygon_input(aoi)
    hazard = polygon_input(hazard_footprint, allow_empty=True)
    land = polygon_input(land, allow_empty=True) if land is not None else None
    metadata = json.loads(json.dumps(metadata or {}, allow_nan=False))
    analysis_id = analysis_id or str(uuid4())
    centre = aoi.centroid
    crs = CRS.from_proj4(
        f"+proj=laea +lat_0={centre.y} +lon_0={centre.x} +datum=WGS84 +units=m +no_defs"
    )
    forward = Transformer.from_crs(4326, crs, always_xy=True).transform
    inverse = Transformer.from_crs(crs, 4326, always_xy=True).transform

    # Shared boundaries receive identical vertices, preserving a non-overlapping partition.
    def project(g):
        return transform(forward, shapely.segmentize(g, 0.001))

    domain = project(aoi)
    terrestrial = project(land).intersection(domain) if land is not None else None
    affected = project(hazard).intersection(domain)
    if terrestrial is not None:
        affected = affected.intersection(terrestrial)
    # Bounding-box overlap is deliberately conservative; exact intersections follow.
    estimate = domain.area / (h3.average_hexagon_area(resolution, unit="m^2"))
    if estimate > max_cells:
        raise ValueError("AOI/resolution exceeds the cell budget")
    indices = sorted(
        set(
            h3.h3shape_to_cells_experimental(
                h3.geo_to_h3shape(mapping(aoi)), resolution, "bbox_overlap"
            )
        )
    )
    if len(indices) > max_cells:
        raise ValueError("AOI/resolution exceeds the cell budget")
    features = []
    for index in indices:
        cell = project(Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(index)]))
        clipped = cell.intersection(domain)
        if clipped.area <= 1e-6:
            continue
        land_area = clipped.intersection(terrestrial).area if terrestrial is not None else None
        hazard_area = clipped.intersection(affected).area
        percent = (
            100 * hazard_area / land_area if land_area is not None and land_area > 1e-6 else None
        )
        if percent is not None and not -1e-7 <= percent <= 100 + 1e-7:
            raise ValueError("Invalid terrestrial fraction")
        properties = {
            "h3_index": index,
            "analysis_id": analysis_id,
            "hazard_type": hazard_type,
            "event_date": event_date,
            "cell_area_m2": cell.area,
            "aoi_cell_area_m2": clipped.area,
            "terrestrial_area_m2": land_area,
            "hazard_area_m2": hazard_area,
            "terrestrial_affected_pct": None if percent is None else min(100.0, max(0.0, percent)),
            "evidence_status": metadata.get("evidence_status"),
        }
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(transform(inverse, clipped)),
                "properties": properties,
            }
        )
    totals = {
        key: sum(f["properties"][key] or 0 for f in features)
        for key in ["aoi_cell_area_m2", "terrestrial_area_m2", "hazard_area_m2"]
    }
    tolerance = max(0.01, domain.area * 1e-7)
    for key, expected in [("aoi_cell_area_m2", domain.area), ("hazard_area_m2", affected.area)]:
        if abs(totals[key] - expected) > tolerance:
            raise ValueError("H3 partition conservation failed")
    if (
        terrestrial is not None
        and abs(totals["terrestrial_area_m2"] - terrestrial.area) > tolerance
    ):
        raise ValueError("Terrestrial partition conservation failed")
    if terrestrial is None:
        totals["terrestrial_area_m2"] = None

    def digest(g):
        return sha256(shapely.normalize(g).wkb).hexdigest() if g is not None else None

    provenance = {
        "analysis_id": analysis_id,
        "hazard_type": hazard_type,
        "event_date": event_date,
        "h3_versions": h3.versions(),
        "resolution": resolution,
        "cell_count": len(features),
        "affected_cell_count": sum(f["properties"]["hazard_area_m2"] > 1e-6 for f in features),
        "input_crs": "EPSG:4326",
        "export_crs": "EPSG:4326",
        "area_crs": crs.to_wkt(),
        "area_method": "WGS84 local Lambert azimuthal equal-area; input edges densified at 0.001 degree; exact planar intersections",
        "cell_selection": "experimental bbox_overlap candidates, exact positive-area AOI intersection, sorted unique indices",
        "denominator": "cell intersect AOI intersect supplied land; null percentage when land absent or zero",
        "geometry_semantics": "union inputs; clip hazard to AOI and supplied land; grid geometry clipped to AOI",
        "software": {"shapely": shapely.__version__, "pyproj": pyproj.__version__},
        "input_geometry_sha256": {
            "aoi": digest(aoi),
            "hazard": digest(hazard),
            "land": digest(land),
        },
        "metadata": metadata,
        "totals": totals,
        "area_conservation_tolerance_m2": tolerance,
        "limitations": [
            "Area fractions are not exposure counts, severity, probability or loss.",
            "Source footprint uncertainty is inherited; no new hazard validation.",
            "Regional non-dateline geometries only; H3 polygon coverage API is experimental and dependency pinned.",
        ],
    }
    return ImpactAnalysis(
        analysis_id, {"type": "FeatureCollection", "features": features}, provenance
    )
