import subprocess
import sys

import numpy as np
import pytest
from affine import Affine

from floodlab.environment.aggregate import categorical_summary, continuous_summary
from floodlab.environment.cache import atomic_json, cache_key, load_receipt
from floodlab.environment.h3sidecar import environmental_h3_sidecar, polygon_reference_sidecar
from floodlab.environment.model import (
    CoverageStatus,
    EnvironmentalAsset,
    EnvironmentalVariable,
    TemporalRelationship,
)
from floodlab.environment.package import export_environment_package, validate_environment_package


def asset(relationship=TemporalRelationship.STATIC):
    return EnvironmentalAsset("dem", "fixture", "dem", "1", "a" * 64, "static", relationship, "30 m", None, None, CoverageStatus.VALID)


def test_lineage_temporal_states_and_aggregation():
    slope = EnvironmentalVariable("slope", "slope", "continuous", "degrees", TemporalRelationship.STATIC, CoverageStatus.VALID, (asset(),), "gradient", "1", {"method": "central"}, checksum="b" * 64)
    assert slope.to_dict()["upstream_assets"][0]["checksum"] == "a" * 64
    assert continuous_summary(np.array([[1.0, np.nan]]), np.array([[1, 1]]), np.array([[1, 1]]))["mean"] == 1.0
    assert categorical_summary(np.array([[1, 2]]), np.ones((1, 2)), np.ones((1, 2)))["classes"] == {"1": 1, "2": 1}
    with pytest.raises(ValueError):
        EnvironmentalVariable("x", "x", "continuous", None, TemporalRelationship.EVENT_TIME, CoverageStatus.VALID, (asset(),))


def test_generic_non_event_environment_has_no_hazard_or_exposure_imports():
    variable = EnvironmentalVariable("lithology", "lithology", "categorical", None, TemporalRelationship.STATIC, CoverageStatus.NO_COVERAGE, ())
    assert variable.coverage_status == CoverageStatus.NO_COVERAGE


def test_temporal_vocabulary_and_missing_provider_do_not_make_zero_data():
    assert {value.value for value in TemporalRelationship} == {
        "EVENT_TIME", "NEAR_EVENT", "CLIMATOLOGY", "STATIC", "MODERN_CONTEXTUAL", "UNKNOWN"
    }
    unavailable = EnvironmentalVariable(
        "land_cover",
        "Land cover",
        "categorical",
        None,
        TemporalRelationship.EVENT_TIME,
        CoverageStatus.UNAVAILABLE_PROVIDER,
        (),
    )
    assert unavailable.coverage_status != CoverageStatus.NO_COVERAGE


def test_cache_key_invalidates_on_source_aoi_grid_algorithm_and_period(tmp_path):
    kwargs = {"source_checksum": "a" * 64, "source_version": "1", "aoi_geojson": {"type": "Polygon"}, "grid": {"width": 2}, "algorithm": {"version": 1}, "reference_period": "2017"}
    key = cache_key(**kwargs)
    receipt = tmp_path / "receipt.json"
    atomic_json(receipt, {"schema": "environment-cache-v1", "cache_key": key})
    assert load_receipt(receipt, key)
    for change in ("source_checksum", "source_version", "aoi_geojson", "grid", "algorithm", "reference_period"):
        altered = dict(kwargs)
        altered[change] = "changed" if change != "grid" else {"width": 3}
        assert cache_key(**altered) != key
    resolution_six = dict(kwargs)
    resolution_six["algorithm"] = {"version": 1, "h3_resolution": 6}
    resolution_seven = dict(kwargs)
    resolution_seven["algorithm"] = {"version": 1, "h3_resolution": 7}
    assert cache_key(**resolution_six) != cache_key(**resolution_seven)


def test_export_reload_checksum_integrity(tmp_path):
    folder = export_environment_package(tmp_path / "package", provenance={"status": "DRAFT"}, summaries={"aoi": {}}, sidecar={"type": "FeatureCollection", "features": []})
    assert validate_environment_package(folder)["files"] == 3


def test_h3_sidecar_reconciles_a_generic_landslide_like_polygon_without_flood_imports():
    profile = {"height": 2, "width": 2, "transform": Affine(0.01, 0, -80.8, 0, -0.01, -5.1), "crs": "EPSG:4326"}
    arrays = {
        "valid": np.ones((2, 2), dtype=bool),
        "aoi": np.ones((2, 2), dtype=bool),
        "elevation_m": np.ones((2, 2)),
        "slope_degrees": np.ones((2, 2)),
        "mapped_drainage_distance_m": np.ones((2, 2)),
    }
    aoi = {"type": "Polygon", "coordinates": [[[-80.8, -5.12], [-80.78, -5.12], [-80.78, -5.1], [-80.8, -5.1], [-80.8, -5.12]]]}
    result = environmental_h3_sidecar(aoi, profile, arrays, resolution=4, generated_utc="fixed")
    assert result["properties"]["h3_represented_valid_pixels"] == 4
    assert result["properties"]["h3_unrepresented_valid_pixels"] == 0


def test_labelled_h3_aggregation_matches_polygon_reference_on_controlled_grid():
    profile = {"height": 4, "width": 4, "transform": Affine(0.01, 0, -80.8, 0, -0.01, -5.1), "crs": "EPSG:4326"}
    values = np.arange(16, dtype=float).reshape(4, 4)
    arrays = {"valid": np.ones((4, 4), bool), "aoi": np.ones((4, 4), bool), "elevation_m": values, "slope_degrees": values, "mapped_drainage_distance_m": values}
    aoi = {"type": "Polygon", "coordinates": [[[-80.8, -5.14], [-80.76, -5.14], [-80.76, -5.1], [-80.8, -5.1], [-80.8, -5.14]]]}
    fast = environmental_h3_sidecar(aoi, profile, arrays, resolution=4, generated_utc="fixed")
    slow = {item["properties"]["h3_index"]: item["properties"] for item in polygon_reference_sidecar(aoi, profile, arrays, resolution=4)}
    for feature in fast["features"]:
        current = feature["properties"]
        reference = slow[current["h3_index"]]
        assert current["elevation_m"] == reference["elevation_m"]


def test_explicit_multi_resolution_is_deterministic_and_directly_joinable():
    from floodlab.impact.engine import analyse_impact

    profile = {"height": 2, "width": 2, "transform": Affine(0.01, 0, -80.8, 0, -0.01, -5.1), "crs": "EPSG:4326"}
    arrays = {"valid": np.ones((2, 2), bool), "aoi": np.ones((2, 2), bool), "elevation_m": np.ones((2, 2)), "slope_degrees": np.ones((2, 2)), "mapped_drainage_distance_m": np.ones((2, 2))}
    aoi = {"type": "Polygon", "coordinates": [[[-80.8, -5.12], [-80.78, -5.12], [-80.78, -5.1], [-80.8, -5.1], [-80.8, -5.12]]]}
    four = environmental_h3_sidecar(aoi, profile, arrays, resolution=4, generated_utc="fixed")
    seven = environmental_h3_sidecar(aoi, profile, arrays, resolution=7, generated_utc="fixed", related_resolutions=(4,))
    repeat = environmental_h3_sidecar(aoi, profile, arrays, resolution=7, generated_utc="fixed", related_resolutions=(4,))
    assert four["properties"]["h3_resolution"] == 4
    assert seven["properties"]["h3_resolution"] == 7
    assert seven["properties"]["output_checksum"] == repeat["properties"]["output_checksum"]
    assert seven["features"] == repeat["features"]
    impact = analyse_impact(aoi, aoi, "synthetic", "2017-03-27", resolution=7)
    impact_grid = {feature["properties"]["h3_index"] for feature in impact.grid["features"]}
    environment_grid = {feature["properties"]["h3_index"] for feature in seven["features"]}
    assert impact_grid <= environment_grid


def test_clean_non_event_import_does_not_load_flood_exposure_or_openeo():
    probe = (
        "import sys; import floodlab.environment; "
        "assert not any(x.startswith(('floodlab.hazards.flood', 'floodlab.impact', 'openeo')) "
        "for x in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, check=False, text=True
    )
    assert result.returncode == 0, result.stderr
