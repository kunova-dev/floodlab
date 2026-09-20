"""Generic georeferenced mask export and geographic preview helpers."""

import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.features import shapes
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds, transform_geom


def export_mask(path, mask, valid, profile):
    profile = profile.copy()
    profile.update(driver="GTiff", count=1, dtype="uint8", nodata=255, compress="deflate")
    values = np.where(valid, mask.astype("uint8"), 255).astype("uint8")
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(values, 1)
    return values


def vectorize(path, mask, transform, crs, pixel_area):
    features = []
    from shapely.geometry import shape

    for geometry, value in shapes(
        mask.astype("uint8"), mask=mask, transform=transform, connectivity=4
    ):
        if value == 1:
            area = shape(geometry).area
            features.append(
                {
                    "type": "Feature",
                    "geometry": transform_geom(crs, "EPSG:4326", geometry),
                    "properties": {
                        "area_ha": area / 10000,
                        "pixels": round(area / pixel_area),
                        "status": "EXPERIMENTAL",
                    },
                }
            )
    Path(path).write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
    )
    return len(features)


def preview(path, values, profile, color):
    height, width = values.shape
    bounds = rasterio.transform.array_bounds(height, width, profile["transform"])
    west, south, east, north = transform_bounds(profile["crs"], "EPSG:4326", *bounds)
    w = 900
    h = max(1, round(w * (north - south) / (east - west)))
    out = np.full((h, w), 255, dtype="uint8")
    reproject(
        values,
        out,
        src_transform=profile["transform"],
        src_crs=profile["crs"],
        dst_transform=from_bounds(west, south, east, north, w, h),
        dst_crs="EPSG:4326",
        src_nodata=255,
        dst_nodata=255,
        resampling=Resampling.nearest,
    )
    rgba = np.zeros((h, w, 4), dtype="uint8")
    rgba[out == 1] = color
    Image.fromarray(rgba).save(path)
    return [[south, west], [north, east]]
