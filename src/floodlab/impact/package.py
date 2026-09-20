"""Adapt a completed scientific package to the generic engine, without rerunning hazards."""

import json
import zipfile
from pathlib import Path
from uuid import uuid4

import rasterio
from rasterio.features import shapes
from rasterio.warp import transform_geom
from shapely.geometry import shape
from shapely.ops import unary_union

from floodlab.eo_core.pair_jobs import sha256_file, write_json

from .engine import analyse_impact


def build_impact_package(source, destination, *, hazard_type, event_date, resolution=7):
    """Create a derived complete ZIP; source package and its provenance remain untouched."""
    source = Path(source)
    report_path = source / "provenance.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for name in ["flood.geojson", "land.tif"]:
        if sha256_file(source / name) != report["output_sha256"][name]:
            raise ValueError("Source footprint/land integrity failure")
    with rasterio.open(source / "land.tif") as raster:
        values = raster.read(1)
        land = unary_union(
            [
                shape(transform_geom(raster.crs, "EPSG:4326", geometry))
                for geometry, value in shapes(values, mask=values == 1, transform=raster.transform)
                if value == 1
            ]
        )
    footprint = json.loads((source / "flood.geojson").read_text(encoding="utf-8"))
    result = analyse_impact(
        footprint,
        report["aoi"],
        hazard_type,
        event_date,
        {
            "source_analysis_id": report["analysis_id"],
            "source_provenance_sha256": sha256_file(report_path),
            "evidence_status": report.get("status"),
            "source_footprint_sha256": sha256_file(source / "flood.geojson"),
            "source_land_sha256": sha256_file(source / "land.tif"),
            "native_hazard_area_ha": report.get("probable_flooded_area_ha"),
        },
        land=land,
        resolution=resolution,
        analysis_id=str(uuid4()),
    )
    folder = Path(destination) / result.analysis_id
    result.export(folder)
    # Validate every payload in the original archive before constructing a derivative.
    with zipfile.ZipFile(source / "analysis.zip") as original:
        checks = json.loads(original.read("checksums.json"))
        from hashlib import sha256

        if original.testzip() is not None or any(
            sha256(original.read(n)).hexdigest() != d for n, d in checks.items()
        ):
            raise ValueError("Source archive integrity failure")
        if sha256(original.read("provenance.json")).hexdigest() != sha256_file(report_path):
            raise ValueError("Source archive provenance mismatch")
        package_checks = dict(checks)
        package_checks["impact/source-checksums.json"] = sha256(
            original.read("checksums.json")
        ).hexdigest()
        for name in ["grid.geojson", "provenance.json"]:
            package_checks["impact/" + name] = sha256_file(folder / name)
        with zipfile.ZipFile(folder / "analysis.zip", "x", zipfile.ZIP_DEFLATED) as out:
            for name in original.namelist():
                if name != "checksums.json":
                    out.writestr(name, original.read(name))
            out.writestr("impact/source-checksums.json", original.read("checksums.json"))
            for name in ["grid.geojson", "provenance.json"]:
                out.write(folder / name, "impact/" + name)
            out.writestr("checksums.json", json.dumps(package_checks, sort_keys=True))
    write_json(
        folder / "checksums.json",
        {
            name: sha256_file(folder / name)
            for name in ["grid.geojson", "provenance.json", "analysis.zip"]
        },
    )
    return folder
