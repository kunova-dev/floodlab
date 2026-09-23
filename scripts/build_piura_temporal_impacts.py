"""Derive generic impact packages from immutable Piura hazard footprints; no EO work."""

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
from floodlab.impact.buildings import OvertureBuildingProvider
from floodlab.impact.engine import analyse_impact, enrich_buildings

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "outputs/analyses/855dc008-898e-42ea-9dba-7aa46ee4b587"
TEMPORAL = ROOT / "outputs/analyses/3bb5d30e-d3bf-46db-a55c-6c746847d558"


def land_polygon():
    with rasterio.open(LEGACY / "land.tif") as src:
        return unary_union(
            [
                shape(transform_geom(src.crs, "EPSG:4326", geometry))
                for geometry, value in shapes(
                    src.read(1), mask=src.read(1) == 1, transform=src.transform
                )
                if value == 1
            ]
        )


def run():
    legacy_report = json.loads((LEGACY / "provenance.json").read_text())
    provider = OvertureBuildingProvider(ROOT / "data/cache")
    buildings, exposure = provider.retrieve(legacy_report["aoi"])
    land = land_polygon()
    products = [
        (
            "legacy-pair",
            LEGACY / "flood.geojson",
            LEGACY,
            "2017-04-04",
            1921.24,
            "Legacy pair-based observation",
        ),
        (
            "maximum-observed-single-date",
            TEMPORAL / "maximum-observed-single-date.geojson",
            TEMPORAL,
            "2017-03-26",
            6328.76,
            "Maximum observed single-date inundation",
        ),
        (
            "event-observed-temporal-union",
            TEMPORAL / "event-observed-temporal-union.geojson",
            TEMPORAL,
            "2017-03-20/2017-04-13",
            10666.64,
            "Areas observed inundated at least once; not simultaneous impact",
        ),
    ]
    output = ROOT / "outputs/impacts" / str(uuid4())
    output.mkdir(parents=True)
    comparison = []
    for name, footprint_path, source, period, native_ha, meaning in products:
        footprint = json.loads(footprint_path.read_text())
        result = analyse_impact(
            footprint,
            legacy_report["aoi"],
            "flood",
            "2017-03-27",
            {
                "hazard_product_type": name,
                "observation_period": period,
                "upstream_product_sha256": sha256_file(footprint_path),
                "native_hazard_area_ha": native_ha,
                "scientific_status": "DRAFT",
                "limitations": meaning,
            },
            land=land,
            resolution=7,
            analysis_id=str(uuid4()),
        )
        aoi_buildings, intersecting = enrich_buildings(
            result, buildings, legacy_report["aoi"], footprint, exposure
        )
        folder = output / name
        result.export(folder)
        for filename, data in [
            ("buildings_aoi.geojson", {"type": "FeatureCollection", "features": aoi_buildings}),
            (
                "buildings_intersecting_hazard.geojson",
                {"type": "FeatureCollection", "features": intersecting},
            ),
            ("hazard-product.geojson", footprint),
        ]:
            (folder / filename).write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        write_json(
            folder / "hazard-product.json",
            {
                "product_type": name,
                "observation_period": period,
                "native_hazard_area_ha": native_ha,
                "upstream_folder": str(source),
                "upstream_footprint_sha256": sha256_file(footprint_path),
                "meaning": meaning,
            },
        )
        summary = {
            "product_type": name,
            "native_hazard_area_ha": native_ha,
            "h3_hazard_area_ha": result.provenance["totals"]["hazard_area_m2"] / 10000,
            "h3_cells_containing_hazard": result.provenance["affected_cell_count"],
            "h3_cells_with_hazard_and_buildings": sum(
                f["properties"]["hazard_area_m2"] > 0
                and f["properties"].get("building_hazard_intersection_m2", 0) > 0
                for f in result.grid["features"]
            ),
            "buildings": result.provenance["buildings"],
            "exposure": exposure,
        }
        write_json(folder / "summary.json", summary)
        comparison.append(summary)
        checks = {p.name: sha256_file(p) for p in folder.iterdir() if p.is_file()}
        write_json(folder / "checksums.json", checks)
        with zipfile.ZipFile(folder / "impact.zip", "x", zipfile.ZIP_DEFLATED) as z:
            for p in folder.iterdir():
                if p.is_file() and p.name != "impact.zip":
                    z.write(p, p.name)
    write_json(
        output / "comparative-summary.json",
        {
            "products": comparison,
            "exposure_temporal_status": "MODERN / CONTEXTUAL BUILT-ENVIRONMENT BASELINE",
            "limitation": "Mapped buildings are not confirmed 2017 buildings, damage, occupancy or loss.",
        },
    )
    print(output)


if __name__ == "__main__":
    run()
