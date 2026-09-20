"""Flood event orchestration using independently evidenced windows and cached real EO data."""

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import geometry_mask, rasterize
from rasterio.warp import transform_geom

from floodlab import __version__
from floodlab.eo_core.aoi import AOI
from floodlab.eo_core.catalogue import Acquisition
from floodlab.eo_core.event_selection import select_event_pair
from floodlab.eo_core.mask_io import export_mask, preview, vectorize
from floodlab.eo_core.pair_jobs import sha256_file, write_json
from floodlab.eo_core.raster import pair_qc

from .event import classify, compare_reference


def analyse_event(root: Path, aoi: AOI, event: dict, observations=None):
    inventory_path = root / "data/cache/openeo/pair-candidates.json"
    inventory = (
        json.loads(inventory_path.read_text(encoding="utf-8")) if observations is None else None
    )
    observations = (
        observations
        if observations is not None
        else [Acquisition(**x) for x in inventory["acquisitions"]]
    )
    earlier, later, selection = select_event_pair(observations, aoi, event)
    selected = None
    for p in sorted((root / "data/cache/openeo").glob("*/provenance.json")):
        value = json.loads(p.read_text(encoding="utf-8"))
        if (
            value["requested_observations"]["earlier"]["id"] == earlier.id
            and value["requested_observations"]["later"]["id"] == later.id
            and AOI.from_geojson(value["aoi"]).geometry.covers(aoi.geometry)
        ):
            selected = (p, value)
            break
    if selected is None:
        raise ValueError(
            "Appropriate observations were selected, but processed rasters are unavailable. Additional authenticated processing is required; no jobs were submitted."
        )
    provenance_path, processing = selected
    files = []
    for role in ("earlier", "later"):
        item = processing["outputs"][role]
        f = provenance_path.parent / item["raster"]
        if (
            not f.resolve().is_relative_to(provenance_path.parent.resolve())
            or sha256_file(f) != item["sha256"]
        ):
            raise ValueError("Processed raster integrity check failed")
        files.append(f)
    qc = pair_qc(*files)
    if not qc["grid_compatible"] or qc["status"] != "QC PASS":
        raise ValueError("Input rasters require alignment or QC review before flood analysis")
    with rasterio.open(files[0]) as src, rasterio.open(files[1]) as other:
        if src.count != 1 or src.crs.to_epsg() != 32717:
            raise ValueError(
                "This reference implementation requires single-band Piura UTM 17S rasters"
            )
        profile = src.profile.copy()
        before = src.read(1, masked=True)
        during = other.read(1, masked=True)
        inside = geometry_mask(
            [transform_geom("EPSG:4326", src.crs, aoi.geojson()["geometry"])],
            out_shape=before.shape,
            transform=src.transform,
            invert=True,
        )
        valid = inside & ~np.ma.getmaskarray(before) & ~np.ma.getmaskarray(during)
    masks, method = classify(before.data, during.data, valid)
    valid = masks["valid"]
    area = abs(profile["transform"].a * profile["transform"].e)
    coverage = float(valid.sum() / inside.sum()) if inside.any() else 0
    if coverage < 0.8:
        raise ValueError("Insufficient common valid AOI coverage")
    reference_path = root / "data/cache/references/indeci-piura2017.geojson"
    implementation = {
        str(p.relative_to(root)): sha256_file(p) for p in (root / "src/floodlab").rglob("*.py")
    }
    identity = {
        "implementation_sha256": implementation,
        "event": event,
        "aoi": aoi.geojson(),
        "inputs": [sha256_file(f) for f in files],
        "reference": sha256_file(reference_path) if reference_path.exists() else None,
        "version": __version__,
        "method": method,
    }
    run_id = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
    output = root / "outputs/events" / run_id
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "result.json"
    if result_path.exists():
        cached = json.loads(result_path.read_text(encoding="utf-8"))
        for name, checksum in cached["output_sha256"].items():
            artifact = output / name
            if (
                not artifact.resolve().is_relative_to(output.resolve())
                or sha256_file(artifact) != checksum
            ):
                raise ValueError("Cached event output integrity check failed")
        return result_path
    bounds = None
    for name, color in [
        ("before", (35, 115, 215, 185)),
        ("during", (20, 160, 205, 185)),
        ("flood", (244, 77, 40, 215)),
    ]:
        values = export_mask(output / f"{name}.tif", masks[name], valid, profile)
        bounds = preview(output / f"{name}.png", values, profile, color)
    polygons = vectorize(
        output / "flood.geojson", masks["flood"], profile["transform"], profile["crs"], area
    )
    comparison = {"status": "Reference unavailable", "accuracy_metrics": None}
    if reference_path.exists():
        ref = json.loads(reference_path.read_text(encoding="utf-8"))
        from shapely import make_valid
        from shapely.geometry import mapping, shape

        geometries = []
        for f in ref["features"]:
            g = make_valid(shape(f["geometry"])).intersection(aoi.geometry)
            if not g.is_empty:
                geometries.append((transform_geom("EPSG:4326", profile["crs"], mapping(g)), 1))
        reference = (
            rasterize(
                geometries,
                out_shape=valid.shape,
                transform=profile["transform"],
                fill=0,
                dtype="uint8",
            ).astype(bool)
            if geometries
            else np.zeros_like(valid)
        )
        layers = compare_reference(masks["flood"], reference, valid)
        for name, color in [
            ("agreement", (46, 160, 75, 200)),
            ("possible_omission", (158, 82, 204, 185)),
            ("possible_commission", (250, 157, 30, 200)),
        ]:
            values = export_mask(output / f"{name}.tif", layers[name], valid, profile)
            preview(output / f"{name}.png", values, profile, color)
        comparison = {
            "status": "Descriptive spatial comparison only; not accuracy validation",
            "reference": json.loads(
                (reference_path.parent / "reference-provenance.json").read_text()
            ),
            "sha256": sha256_file(reference_path),
            "areas_ha": {k: float(v.sum() * area / 10000) for k, v in layers.items()},
            "accuracy_metrics": None,
            "limitations": "Unknown reference observation dates/completeness and sensor independence. Outside mapped polygons is not confirmed dry. Differences may reflect timing, reference scope or method error.",
        }
    result = {
        "version": __version__,
        "implementation_sha256": implementation,
        "created_utc": datetime.now(UTC).isoformat(),
        "status": "DRAFT",
        "confidence": "EXPERIMENTAL — REQUIRES VALIDATION",
        "event": event,
        "aoi": aoi.geojson(),
        "selection": selection,
        "inventory": {
            "mode": "cached live catalogue" if inventory else "provided observations",
            "checked_utc": inventory.get("checked_utc") if inventory else None,
        },
        "processing_provenance": processing,
        "processing_provenance_sha256": sha256_file(provenance_path),
        "input_rasters": [str(f.relative_to(root)) for f in files],
        "method": method,
        "qc": qc,
        "coverage_fraction": coverage,
        "probable_flooded_area_ha": float(masks["flood"].sum() * area / 10000),
        "before_water_ha": float(masks["before"].sum() * area / 10000),
        "during_water_ha": float(masks["during"].sum() * area / 10000),
        "minimum_mapping_unit_ha": method["min_pixels"] * area / 10000,
        "polygon_count": polygons,
        "sensitivity_area_ha": [
            dict(s, area_ha=s["pixels"] * area / 10000) for s in method["sensitivity"]
        ],
        "comparison": comparison,
        "bounds": bounds,
        "output_sha256": {p.name: sha256_file(p) for p in output.iterdir() if p.is_file()},
    }
    write_json(result_path, result)
    return result_path
