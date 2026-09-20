"""Verify a completed local product, its GIS geometry, scientific domain and archive."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

from floodlab.eo_core.pair_jobs import sha256_file


def validate(folder):
    report = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    checks = json.loads((folder / "checksums.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(folder / "analysis.zip") as archive:
        assert archive.testzip() is None
        for name, digest in checks.items():
            assert sha256_file(folder / name) == digest
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    with rasterio.open(folder / "land.tif") as src:
        land = src.read(1) == 1
        grid = (src.crs, src.transform, src.shape)
    pixel_ha = abs(grid[1].a * grid[1].e) / 10000
    binary = [
        "flood",
        "before",
        "during",
        "s1-evidence",
        "s2-evidence",
        "s2-water",
        "agreement",
        "possible_omission",
        "possible_commission",
    ]
    for path in folder.glob("*.tif"):
        with rasterio.open(path) as src:
            assert (src.crs, src.transform, src.shape) == grid
            values = src.read(1)
            if path.stem in binary:
                assert not np.any((values == 1) & ~land), path.name
                assert np.all(values[~land] == 255), path.name
    with rasterio.open(folder / "flood.tif") as src:
        raster_area = float(np.count_nonzero(src.read(1) == 1) * pixel_ha)
    collection = json.loads((folder / "flood.geojson").read_text(encoding="utf-8"))
    projector = Transformer.from_crs(4326, grid[0], always_xy=True).transform
    vector_area = (
        sum(transform(projector, shape(f["geometry"])).area for f in collection["features"]) / 10000
    )
    assert abs(raster_area - vector_area) <= pixel_ha
    assert abs(raster_area - report["probable_flooded_area_ha"]) < 1e-6
    for path in folder.glob("*.png"):
        with Image.open(path) as image:
            image.verify()
    for entry in report["sources"].values():
        assert (
            entry["url"]
            and sha256_file(folder / "context_sources" / entry["file"]) == entry["sha256"]
        )
    assert report["comparison"]["accuracy_metrics"] is None
    comparison = report["comparison"]
    if "areas_ha" in comparison:
        legacy_path = folder.resolve().parents[2] / report["v03_comparison_provenance"]
        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        old_areas = legacy["comparison"]["areas_ha"]
        areas = comparison["areas_ha"]
        # Same repaired/clipped reference domain, with ocean excluded in v0.4.
        assert (
            abs(
                areas["agreement"]
                + areas["possible_omission"]
                + comparison["reference_offshore_ha"]
                - old_areas["agreement"]
                - old_areas["possible_omission"]
            )
            <= pixel_ha
        )
    result = {
        "analysis_id": report["analysis_id"],
        "checksummed_files": len(checks),
        "zero_ocean_flood_pixels": True,
        "raster_area_ha": raster_area,
        "reprojected_vector_area_ha": vector_area,
        "tolerance_ha": pixel_ha,
        "zip_sha256": sha256_file(folder / "analysis.zip"),
        "status": "PASS",
    }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis_directory", type=Path)
    print(json.dumps(validate(parser.parse_args().analysis_directory), indent=2))
