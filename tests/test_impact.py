"""H3 partition correctness, absence semantics and mandatory non-flood independence."""

import json
import subprocess
import sys

import h3
import pytest
from pyproj import Geod
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from floodlab.impact.buildings import Building, OvertureBuildingProvider
from floodlab.impact.engine import analyse_impact, enrich_buildings


def test_index_geometry_partition_and_determinism(tmp_path):
    aoi = box(-80.65, -5.22, -80.61, -5.18)
    land = box(-80.64, -5.22, -80.61, -5.18)
    hazard = box(-80.65, -5.22, -80.625, -5.18)
    arguments = (hazard, aoi, "wildfire", "2020-01-01")
    result = analyse_impact(*arguments, land=land, analysis_id="fixed")
    repeat = analyse_impact(*arguments, land=land, analysis_id="fixed")
    assert result.grid == repeat.grid and result.provenance == repeat.provenance
    features = result.grid["features"]
    indices = [f["properties"]["h3_index"] for f in features]
    assert indices == sorted(set(indices)) and all(
        h3.is_valid_cell(i) and h3.get_resolution(i) == 7 for i in indices
    )
    geometries = [shape(f["geometry"]) for f in features]
    assert all(g.is_valid for g in geometries)
    assert sum(g.area for g in geometries) - unary_union(geometries).area < 1e-10
    assert unary_union(geometries).symmetric_difference(aoi).area < 1e-9
    geod = Geod(ellps="WGS84")
    expected = abs(geod.geometry_area_perimeter(hazard.intersection(land))[0])
    totals = result.provenance["totals"]
    assert totals["hazard_area_m2"] == pytest.approx(expected, rel=1e-5)
    assert totals["terrestrial_area_m2"] == pytest.approx(
        abs(geod.geometry_area_perimeter(land)[0]), rel=1e-5
    )
    for f in features:
        p = f["properties"]
        pct = p["terrestrial_affected_pct"]
        assert pct is None or 0 <= pct <= 100
        if p["terrestrial_area_m2"] <= 1e-6:
            assert pct is None and p["hazard_area_m2"] == 0
        assert p["hazard_area_m2"] <= p["terrestrial_area_m2"] + 1e-5
    result.export(tmp_path / "export")
    assert (
        json.loads((tmp_path / "export/grid.geojson").read_text())["features"][0]["properties"]
        == features[0]["properties"]
    )
    with pytest.raises(FileExistsError):
        result.export(tmp_path / "export")
    assert result.provenance["h3_versions"] == h3.versions()
    assert result.provenance["area_crs"] and result.provenance["input_geometry_sha256"]["hazard"]


def test_boundary_cells_tiny_aoi_and_duplicate_polygons():
    # Far smaller than a resolution-7 cell; centre-only filling would lose this AOI.
    aoi = box(-80.6321, -5.1941, -80.6320, -5.1940)
    duplicate = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": mapping(aoi), "properties": {}}] * 2,
    }
    result = analyse_impact(duplicate, aoi, "landslide", "2020-01-01", land=aoi)
    assert result.grid["features"]
    assert result.provenance["totals"]["hazard_area_m2"] == pytest.approx(
        result.provenance["totals"]["aoi_cell_area_m2"]
    )
    assert all(
        f["properties"]["terrestrial_affected_pct"] == pytest.approx(100)
        for f in result.grid["features"]
    )


def test_missing_land_empty_hazard_and_ocean_are_not_fabricated():
    aoi = box(-80.65, -5.22, -80.61, -5.18)
    empty = {"type": "FeatureCollection", "features": []}
    unknown = analyse_impact(aoi, aoi, "subsidence", "2020-01-01")
    assert unknown.provenance["totals"]["terrestrial_area_m2"] is None
    assert all(
        f["properties"]["terrestrial_affected_pct"] is None for f in unknown.grid["features"]
    )
    ocean = analyse_impact(aoi, aoi, "subsidence", "2020-01-01", land=empty)
    assert ocean.provenance["totals"]["hazard_area_m2"] == 0
    dry = analyse_impact(empty, aoi, "subsidence", "2020-01-01", land=aoi)
    assert dry.provenance["totals"]["hazard_area_m2"] == 0


def test_non_flood_runs_without_importing_any_hazard_or_eo_processor():
    code = """
import builtins,sys
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name.startswith(('floodlab.hazards','floodlab.eo_core','openeo')):
        raise AssertionError('Forbidden processing import: '+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from floodlab.impact.engine import analyse_impact
from shapely.geometry import box
result=analyse_impact(box(-80.64,-5.21,-80.63,-5.20),box(-80.65,-5.22,-80.61,-5.18),'volcanic_deformation','2020-01-01')
assert result.grid['features'] and result.provenance['hazard_type']=='volcanic_deformation'
assert not any(name.startswith(('floodlab.hazards','floodlab.eo_core','openeo')) for name in sys.modules)
print('NON-FLOOD INDEPENDENCE PASS')
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert "NON-FLOOD INDEPENDENCE PASS" in result.stdout


def test_invalid_configuration_and_regions_fail_explicitly():
    aoi = box(-80.65, -5.22, -80.61, -5.18)
    for resolution in [-1, 11, True]:
        with pytest.raises(ValueError):
            analyse_impact(aoi, aoi, "flood", "2020-01-01", resolution=resolution)
    with pytest.raises(ValueError, match="budget"):
        analyse_impact(aoi, aoi, "flood", "2020-01-01", max_cells=1)
    with pytest.raises(ValueError):
        analyse_impact(aoi, box(-179, -5, 179, 5), "flood", "2020-01-01")


def test_derived_complete_package_preserves_source_and_checksums(tmp_path):
    import hashlib
    import zipfile

    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    from floodlab.impact.package import build_impact_package

    source = tmp_path / "source"
    source.mkdir()
    aoi = box(-80.65, -5.22, -80.61, -5.18)
    (source / "flood.geojson").write_text(json.dumps(mapping(aoi)), encoding="utf-8")
    with rasterio.open(
        source / "land.tif",
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(-80.65, -5.18, 0.004, 0.004),
    ) as dst:
        land = np.ones((10, 10), dtype="uint8")
        land[:, :5] = 0
        dst.write(land, 1)

    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    report = {
        "analysis_id": "source-fixture",
        "aoi": mapping(aoi),
        "status": "DRAFT",
        "output_sha256": {n: digest(source / n) for n in ["flood.geojson", "land.tif"]},
    }
    (source / "provenance.json").write_text(json.dumps(report), encoding="utf-8")
    original = {p.name: digest(p) for p in source.iterdir()}
    with zipfile.ZipFile(source / "analysis.zip", "w") as archive:
        for name in original:
            archive.write(source / name, name)
        archive.writestr("checksums.json", json.dumps(original))
    original["analysis.zip"] = digest(source / "analysis.zip")

    class FixtureProvider:
        def retrieve(self, geometry):
            return [Building("fixture-building", aoi, "fixture", "1")], {
                "provider": "fixture",
                "release": "1",
                "status": "retrieved",
                "temporal_baseline": "MODERN / CONTEXTUAL BUILT-ENVIRONMENT BASELINE",
            }

    result = build_impact_package(
        source,
        tmp_path / "derived",
        hazard_type="wildfire",
        event_date="2020-01-01",
        building_provider=FixtureProvider(),
    )
    assert all(digest(source / name) == value for name, value in original.items())
    with zipfile.ZipFile(result / "analysis.zip") as archive:
        assert archive.testzip() is None
        checks = json.loads(archive.read("checksums.json"))
        assert "impact/grid.geojson" in checks and "impact/provenance.json" in checks
        for name, value in checks.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == value
        assert archive.read("provenance.json") == (source / "provenance.json").read_bytes()
    assert json.loads((result / "buildings_aoi.geojson").read_text())["features"]
    assert json.loads((result / "buildings_intersecting_hazard.geojson").read_text())["features"]
    (source / "flood.geojson").write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        build_impact_package(
            source, tmp_path / "derived", hazard_type="wildfire", event_date="2020-01-01"
        )


def test_building_enrichment_counts_once_and_apportions_geometry():
    aoi, hazard = box(-80.65, -5.22, -80.61, -5.18), box(-80.64, -5.21, -80.62, -5.19)
    analysis = analyse_impact(hazard, aoi, "wildfire", "2020-01-01", land=aoi)
    buildings = [
        Building("same", box(-80.641, -5.211, -80.625, -5.195), "fixture", "1", height_m=8),
        Building("same", box(-80.639, -5.209, -80.623, -5.193), "fixture", "1", levels=None),
        Building("dry", box(-80.619, -5.219, -80.615, -5.215), "fixture", "1"),
    ]
    all_buildings, exposed = enrich_buildings(
        analysis, buildings, aoi, hazard, {"provider": "fixture", "status": "retrieved"}
    )
    summary = analysis.provenance["buildings"]
    assert len(all_buildings) == summary["buildings_in_aoi"] == 2
    assert len(exposed) == summary["buildings_intersecting_hazard"] == 1
    assert sum(f["properties"]["building_count"] for f in analysis.grid["features"]) == 2
    assert sum(
        f["properties"]["building_footprint_m2"] for f in analysis.grid["features"]
    ) == pytest.approx(summary["building_footprint_m2"])
    assert sum(
        f["properties"]["building_hazard_intersection_m2"] for f in analysis.grid["features"]
    ) == pytest.approx(summary["building_hazard_intersection_m2"])
    assert all(0 <= f["properties"]["footprint_intersection_pct"] <= 100 for f in all_buildings)
    assert all_buildings[0]["properties"]["levels"] is None


def test_overture_no_data_cache_is_distinct_from_zero_buildings(tmp_path, monkeypatch):
    provider = OvertureBuildingProvider(tmp_path, executable="fixture-overture")
    calls = []

    class Completed:
        returncode = 1
        stdout = "No data found for release 2026-08-19.0"
        stderr = ""

    monkeypatch.setattr(
        "floodlab.impact.buildings.subprocess.run", lambda *a, **k: calls.append(a) or Completed()
    )
    monkeypatch.setattr(provider, "_duckdb_retrieve", lambda *a: ([], 0))
    first, metadata = provider.retrieve(box(-80.65, -5.22, -80.61, -5.18))
    second, reused = provider.retrieve(box(-80.65, -5.22, -80.61, -5.18))
    assert first == second == []
    assert metadata["status"] == "no_data" and reused["cache_status"] == "reused"
    assert len(calls) == 1


def test_non_flood_building_provider_path_has_no_processing_imports():
    code = """
import builtins,sys
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name.startswith(('floodlab.hazards','floodlab.eo_core','openeo')):
        raise AssertionError('Forbidden processing import: '+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from shapely.geometry import box
from floodlab.impact.engine import analyse_impact,enrich_buildings
from floodlab.impact.buildings import Building
aoi=box(-80.65,-5.22,-80.61,-5.18)
analysis=analyse_impact(box(-80.64,-5.21,-80.62,-5.19),aoi,'wildfire','2020-01-01')
enrich_buildings(analysis,[Building('b',box(-80.64,-5.21,-80.63,-5.20),'fixture','1')],aoi,box(-80.64,-5.21,-80.62,-5.19),{'status':'retrieved','provider':'fixture'})
assert analysis.provenance['buildings']['buildings_intersecting_hazard']==1
assert not any(name.startswith(('floodlab.hazards','floodlab.eo_core','openeo')) for name in sys.modules)
print('NON-FLOOD BUILDING PASS')
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert "NON-FLOOD BUILDING PASS" in result.stdout
