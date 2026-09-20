"""Verified geographic context on an EO reference grid."""

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_geom
from shapely import make_valid
from shapely.geometry import mapping, shape

from .pair_jobs import sha256_file


def read_sources(folder, years):
    manifest = json.loads((folder / "sources.json").read_text(encoding="utf-8"))
    for key in ["land"] + [f"water-{year}" for year in years]:
        if key not in manifest:
            raise ValueError(f"Required scientific context unavailable: {key}")
    for entry in manifest.values():
        path = (folder / entry["file"]).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256_file(path) != entry["sha256"]:
            raise ValueError("Context checksum/path validation failed")
    return manifest


def aligned(path, profile, categorical=True):
    with (
        rasterio.open(path) as src,
        WarpedVRT(
            src,
            crs=profile["crs"],
            transform=profile["transform"],
            width=profile["width"],
            height=profile["height"],
            resampling=Resampling.nearest if categorical else Resampling.bilinear,
        ) as vrt,
    ):
        return vrt.read(1, masked=True)


def vector_mask(path, profile, clip_geometry=None):
    source = json.loads(Path(path).read_text(encoding="utf-8"))
    geometries = []
    for feature in source["features"]:
        geometry = make_valid(shape(feature["geometry"]))
        if clip_geometry is not None:
            geometry = geometry.intersection(clip_geometry)
        if not geometry.is_empty:
            geometries.append((transform_geom("EPSG:4326", profile["crs"], mapping(geometry)), 1))
    return (
        rasterize(
            geometries,
            out_shape=(profile["height"], profile["width"]),
            transform=profile["transform"],
            fill=0,
            dtype="uint8",
        ).astype(bool)
        if geometries
        else np.zeros((profile["height"], profile["width"]), bool)
    )
