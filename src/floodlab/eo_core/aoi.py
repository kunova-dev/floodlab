"""RFC 7946 longitude/latitude polygon validation."""

import json
from dataclasses import dataclass
from pathlib import Path

from shapely.errors import GEOSException
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class AOI:
    geometry: BaseGeometry
    name: str = "User AOI"

    @classmethod
    def from_geojson(cls, value: dict) -> "AOI":
        """Accept a geometry, Feature, or single-feature collection in WGS84."""
        if not isinstance(value, dict):
            raise TypeError("GeoJSON must be a JSON object")
        if "crs" in value:
            raise ValueError("Use RFC 7946 GeoJSON in WGS84 without a crs member")
        if value.get("type") == "FeatureCollection":
            if not isinstance(value.get("features"), list) or len(value["features"]) != 1:
                raise ValueError("Provide exactly one polygon feature")
            return cls.from_geojson(value["features"][0])
        properties = value.get("properties") or {}
        if not isinstance(properties, dict):
            raise TypeError("GeoJSON properties must be an object or null")
        name = properties.get("name", "User AOI")
        geometry_value = value.get("geometry") if value.get("type") == "Feature" else value
        if not isinstance(geometry_value, dict):
            raise TypeError("AOI geometry must be a non-null object")
        try:
            geometry = shape(geometry_value)
        except (GEOSException, ValueError, TypeError, KeyError, IndexError) as exc:
            raise ValueError("Malformed GeoJSON geometry") from exc
        if geometry.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("AOI must be Polygon or MultiPolygon")
        if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
            raise ValueError("AOI must be nonempty and topologically valid")
        west, south, east, north = geometry.bounds
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError("Coordinates must be WGS84 longitude/latitude")
        # Reject ambiguous dateline edges; split into narrow polygons first.
        polygons = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
        if any(p.bounds[2] - p.bounds[0] > 180 for p in polygons):
            raise ValueError("Split dateline-crossing AOIs into polygons at +/-180 degrees")
        return cls(geometry, str(name))

    @classmethod
    def read(cls, path: Path) -> "AOI":
        return cls.from_geojson(json.loads(path.read_text(encoding="utf-8")))

    def geojson(self) -> dict:
        return {
            "type": "Feature",
            "properties": {"name": self.name},
            "geometry": mapping(self.geometry),
        }
