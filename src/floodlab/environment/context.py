"""Read-only adapters for the verified v0.4 Piura terrain and drainage assets."""

import json
from pathlib import Path

import numpy as np
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from scipy.ndimage import distance_transform_edt

from floodlab.eo_core.context import aligned, vector_mask
from floodlab.eo_core.pair_jobs import sha256_file

from .aggregate import continuous_summary
from .model import CoverageStatus, EnvironmentalAsset, EnvironmentalVariable, TemporalRelationship


def _asset(entry: dict, *, asset_id: str, relationship: TemporalRelationship) -> EnvironmentalAsset:
    is_dem = entry.get("product", "").startswith("Copernicus")
    return EnvironmentalAsset(
        asset_id=asset_id,
        provider="Copernicus DEM" if is_dem else "HydroSHEDS",
        dataset=entry.get("product", "HydroRIVERS"),
        version=entry["version"],
        checksum=entry["sha256"],
        reference_period="static source dataset",
        temporal_relationship=relationship,
        native_resolution="30 m" if is_dem else "15 arc-second network",
        retrieved_utc=entry.get("retrieved_utc"),
        licence=entry.get("license"),
        coverage_status=CoverageStatus.VALID,
        limitations=(entry.get("limitations", ""),),
    )


def load_verified_static_context(root: Path, profile: dict, aoi_geometry: dict) -> dict:
    """Load static context without changing reconstruction code or source pixels."""
    folder = root / "data/cache/v04"
    manifest = json.loads((folder / "sources.json").read_text(encoding="utf-8"))
    result: dict = {"assets": [], "variables": [], "arrays": {}}
    inside = geometry_mask(
        [transform_geom("EPSG:4326", profile["crs"], aoi_geometry)],
        out_shape=(profile["height"], profile["width"]), transform=profile["transform"], invert=True,
    )
    for key in ("dem", "rivers"):
        entry = manifest[key]
        path = folder / entry["file"]
        if sha256_file(path) != entry["sha256"]:
            raise ValueError(f"Verified environmental source checksum failed: {key}")
    dem_asset = _asset(
        manifest["dem"],
        asset_id="copernicus-dem-glo30-piura",
        relationship=TemporalRelationship.STATIC,
    )
    dem = aligned(folder / manifest["dem"]["file"], profile, categorical=False).filled(np.nan).astype("float32")
    y, x = np.gradient(dem, abs(profile["transform"].e), profile["transform"].a)
    slope = np.degrees(np.arctan(np.hypot(x, y))).astype("float32")
    rivers_asset = _asset(
        manifest["rivers"],
        asset_id="hydrivers-v10-piura",
        relationship=TemporalRelationship.STATIC,
    )
    rivers = vector_mask(folder / manifest["rivers"]["file"], profile)
    drainage_distance = distance_transform_edt(
        ~rivers, sampling=(abs(profile["transform"].e), profile["transform"].a)
    ).astype("float32")
    result["assets"] = [dem_asset, rivers_asset]
    result["variables"] = [
        EnvironmentalVariable("elevation_m", "Elevation", "continuous", "m", TemporalRelationship.STATIC, CoverageStatus.VALID, (dem_asset,), "aligned DEM", "v0.5e", spatial_processing="bilinear alignment to supplied reference grid", limitations=("DSM context; not HAND.",)),
        EnvironmentalVariable("slope_degrees", "Slope", "continuous", "degrees", TemporalRelationship.STATIC, CoverageStatus.VALID, (dem_asset,), "numpy.gradient then arctan", "v0.5e", {"units": "degrees"}, "computed on supplied reference grid", limitations=("Derived from DSM; edge/nodata pixels excluded.",)),
        EnvironmentalVariable("mapped_drainage_distance_m", "Distance to nearest mapped reach", "continuous", "m", TemporalRelationship.STATIC, CoverageStatus.VALID, (rivers_asset,), "Euclidean distance transform", "v0.5e", {"sampling": "reference grid metres"}, "rasterized mapped reaches on supplied reference grid", limitations=("Mapped-reach proximity only; not flow connectivity or HAND.",)),
    ]
    result["arrays"] = {"elevation_m": dem, "slope_degrees": slope, "mapped_drainage_distance_m": drainage_distance, "valid": np.isfinite(dem) & inside, "aoi": inside}
    return result


def summarize_continuous_context(context: dict, domain: np.ndarray) -> dict:
    valid = context["arrays"]["valid"]
    return {name: continuous_summary(context["arrays"][name], valid, domain) for name in ("elevation_m", "slope_degrees", "mapped_drainage_distance_m")}
