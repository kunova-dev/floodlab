"""Native-grid environmental H3 summaries; source rasters remain authoritative."""

import json
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter

import h3
import numpy as np
from rasterio.features import geometry_mask, rasterize
from rasterio.warp import transform_geom
from shapely.geometry import Polygon, mapping, shape

from .aggregate import continuous_summary

ALGORITHM = "native-pixel-centre-labelled-raster"
ALGORITHM_VERSION = "v2"
VARIABLES = ("elevation_m", "slope_degrees", "mapped_drainage_distance_m")


def _cells(aoi, resolution):
    selection = aoi.buffer(0.02)
    indices = sorted(set(h3.h3shape_to_cells_experimental(h3.geo_to_h3shape(mapping(selection)), resolution, "overlap")))
    return [(index, Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(index)]).intersection(aoi)) for index in indices]


def _profile_spec(profile):
    transform = profile["transform"]
    return {"crs": str(profile["crs"]), "width": profile["width"], "height": profile["height"], "transform": [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f]}


def _summary(values, valid, labels, label):
    use = valid & (labels == label)
    result = continuous_summary(values, valid, labels == label)
    result["min"] = float(np.min(values[use])) if use.any() else None
    result["max"] = float(np.max(values[use])) if use.any() else None
    return result


def polygon_reference_sidecar(aoi_geojson, profile, arrays, *, resolution):
    """Slow reference implementation retained solely for controlled equivalence tests."""
    aoi = shape(aoi_geojson)
    features = []
    for index, geometry in _cells(aoi, resolution):
        if geometry.is_empty:
            continue
        mask = geometry_mask([transform_geom("EPSG:4326", profile["crs"], mapping(geometry))], out_shape=(profile["height"], profile["width"]), transform=profile["transform"], invert=True)
        properties = {"h3_index": index}
        for name in VARIABLES:
            properties[name] = _summary(arrays[name], arrays["valid"], mask.astype("int8"), 1)
        features.append({"type": "Feature", "geometry": mapping(geometry), "properties": properties})
    return features


def environmental_h3_sidecar(aoi_geojson: dict, profile: dict, arrays: dict, *, resolution: int, source_checksums: tuple[str, ...] = (), variable_checksums: tuple[str, ...] = (), variable_metadata_checksums: tuple[str, ...] = (), generated_utc: str | None = None, related_resolutions: tuple[int, ...] = ()) -> dict:
    """Rasterize all H3 cells once, then calculate per-label native-pixel statistics."""
    if type(resolution) is not int or not 0 <= resolution <= 10:
        raise ValueError("H3 resolution must be an integer from 0 to 10")
    started = perf_counter()
    aoi = shape(aoi_geojson)
    cells = [(index, geometry) for index, geometry in _cells(aoi, resolution) if not geometry.is_empty]
    shapes = [(transform_geom("EPSG:4326", profile["crs"], mapping(geometry)), number) for number, (_, geometry) in enumerate(cells, start=1)]
    labels = rasterize(shapes, out_shape=(profile["height"], profile["width"]), transform=profile["transform"], fill=0, dtype="int32")
    valid = arrays["valid"] & arrays["aoi"]
    represented = valid & (labels > 0)
    features = []
    for number, (index, geometry) in enumerate(cells, start=1):
        properties = {"h3_index": index, "coverage_status": "VALID" if np.any(represented & (labels == number)) else "NOT_OBSERVED"}
        for name in VARIABLES:
            properties[name] = _summary(arrays[name], valid, labels, number)
        features.append({"type": "Feature", "geometry": mapping(geometry), "properties": properties})
    metadata = {
        "h3_resolution": resolution, "aggregation_algorithm": ALGORITHM, "aggregation_algorithm_version": ALGORITHM_VERSION,
        "aggregation_method": "native pixel-centre assignment using one labelled H3 raster", "native_data_authoritative": True,
        "native_grid": _profile_spec(profile), "source_environmental_asset_checksums": list(source_checksums),
        "source_environmental_derived_data_checksums": list(variable_checksums),
        "source_environmental_variable_metadata_checksums": list(variable_metadata_checksums),
        "nodata_policy": "Native invalid/nodata pixels are excluded; no observation is not zero.",
        "generated_utc": generated_utc or datetime.now(UTC).isoformat(), "related_resolutions": sorted(set(related_resolutions)),
        "candidate_h3_cells": len(cells), "valid_h3_cells": sum(f["properties"]["coverage_status"] == "VALID" for f in features),
        "native_valid_pixels": int(np.count_nonzero(valid)), "h3_represented_valid_pixels": int(np.count_nonzero(represented)),
        "h3_unrepresented_valid_pixels": int(np.count_nonzero(valid & ~represented)),
        "processing_seconds": round(perf_counter() - started, 3),
    }
    metadata["coverage_pct"] = 100 * metadata["h3_represented_valid_pixels"] / metadata["native_valid_pixels"]
    metadata["output_checksum"] = sha256(
        json.dumps(features, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {"type": "FeatureCollection", "properties": metadata, "features": features}
