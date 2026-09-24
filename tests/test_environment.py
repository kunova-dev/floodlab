import hashlib
import json
import runpy
import subprocess
import sys
import zipfile

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
    return EnvironmentalAsset(
        "dem",
        "fixture",
        "dem",
        "1",
        "a" * 64,
        "static",
        relationship,
        "30 m",
        None,
        None,
        CoverageStatus.VALID,
    )


def test_lineage_temporal_states_and_aggregation():
    slope = EnvironmentalVariable(
        "slope",
        "slope",
        "continuous",
        "degrees",
        TemporalRelationship.STATIC,
        CoverageStatus.VALID,
        (asset(),),
        "gradient",
        "1",
        {"method": "central"},
        checksum="b" * 64,
    )
    assert slope.to_dict()["upstream_assets"][0]["checksum"] == "a" * 64
    assert (
        continuous_summary(np.array([[1.0, np.nan]]), np.array([[1, 1]]), np.array([[1, 1]]))[
            "mean"
        ]
        == 1.0
    )
    assert categorical_summary(np.array([[1, 2]]), np.ones((1, 2)), np.ones((1, 2)))["classes"] == {
        "1": 1,
        "2": 1,
    }
    with pytest.raises(ValueError):
        EnvironmentalVariable(
            "x",
            "x",
            "continuous",
            None,
            TemporalRelationship.EVENT_TIME,
            CoverageStatus.VALID,
            (asset(),),
        )


def test_generic_non_event_environment_has_no_hazard_or_exposure_imports():
    variable = EnvironmentalVariable(
        "lithology",
        "lithology",
        "categorical",
        None,
        TemporalRelationship.STATIC,
        CoverageStatus.NO_COVERAGE,
        (),
    )
    assert variable.coverage_status == CoverageStatus.NO_COVERAGE


def test_temporal_vocabulary_and_missing_provider_do_not_make_zero_data():
    assert {value.value for value in TemporalRelationship} == {
        "EVENT_TIME",
        "NEAR_EVENT",
        "CLIMATOLOGY",
        "STATIC",
        "MODERN_CONTEXTUAL",
        "UNKNOWN",
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
    kwargs = {
        "source_checksum": "a" * 64,
        "source_version": "1",
        "aoi_geojson": {"type": "Polygon"},
        "grid": {"width": 2},
        "algorithm": {"version": 1},
        "reference_period": "2017",
    }
    key = cache_key(**kwargs)
    receipt = tmp_path / "receipt.json"
    atomic_json(receipt, {"schema": "environment-cache-v1", "cache_key": key})
    assert load_receipt(receipt, key)
    for change in (
        "source_checksum",
        "source_version",
        "aoi_geojson",
        "grid",
        "algorithm",
        "reference_period",
    ):
        altered = dict(kwargs)
        altered[change] = "changed" if change != "grid" else {"width": 3}
        assert cache_key(**altered) != key
    resolution_six = dict(kwargs)
    resolution_six["algorithm"] = {"version": 1, "h3_resolution": 6}
    resolution_seven = dict(kwargs)
    resolution_seven["algorithm"] = {"version": 1, "h3_resolution": 7}
    assert cache_key(**resolution_six) != cache_key(**resolution_seven)


def test_export_reload_checksum_integrity(tmp_path):
    folder = export_environment_package(
        tmp_path / "package",
        provenance={"status": "DRAFT"},
        summaries={"aoi": {}},
        sidecar={"type": "FeatureCollection", "features": []},
    )
    assert validate_environment_package(folder)["files"] == 3


def _package(tmp_path, name):
    return export_environment_package(
        tmp_path / name,
        provenance={"status": "DRAFT"},
        summaries={"aoi": {}},
        sidecar={"type": "FeatureCollection", "features": []},
    )


def _rewrite_archive(folder, replacement):
    archive_path = folder / "environment.zip"
    with zipfile.ZipFile(archive_path) as archive:
        payloads = {name: archive.read(name) for name in archive.namelist()}
    payloads.update(replacement)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in payloads.items():
            archive.writestr(name, content)
    package = json.loads((folder / "package.json").read_text(encoding="utf-8"))
    package["package_sha256"] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (folder / "package.json").write_text(json.dumps(package), encoding="utf-8")


def test_environment_package_rejects_archived_payload_checksum_mismatch(tmp_path):
    folder = _package(tmp_path, "payload")
    _rewrite_archive(folder, {"summaries.json": b'{"tampered":true}'})
    with pytest.raises(ValueError, match="ZIP payload checksum"):
        validate_environment_package(folder)


def test_environment_package_rejects_archived_manifest_relationship_mismatch(tmp_path):
    folder = _package(tmp_path, "manifest")
    _rewrite_archive(folder, {"checksums.json": b'{"summaries.json":"bad"}'})
    with pytest.raises(ValueError, match="ZIP checksum manifest differs"):
        validate_environment_package(folder)


def test_environment_package_rejects_zip_crc_corruption(tmp_path):
    folder = _package(tmp_path, "crc")
    archive_path = folder / "environment.zip"
    with zipfile.ZipFile(archive_path) as archive:
        info = archive.getinfo("summaries.json")
    raw = bytearray(archive_path.read_bytes())
    name_length = int.from_bytes(raw[info.header_offset + 26 : info.header_offset + 28], "little")
    extra_length = int.from_bytes(raw[info.header_offset + 28 : info.header_offset + 30], "little")
    payload_start = info.header_offset + 30 + name_length + extra_length
    raw[payload_start + max(1, info.compress_size // 2)] ^= 0x01
    archive_path.write_bytes(raw)
    package = json.loads((folder / "package.json").read_text(encoding="utf-8"))
    package["package_sha256"] = hashlib.sha256(raw).hexdigest()
    (folder / "package.json").write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises((ValueError, zipfile.BadZipFile), match="CRC|Bad CRC"):
        validate_environment_package(folder)


def test_provider_contract_and_execution_context_do_not_load_openeo():
    from floodlab.environment.providers import EnvironmentalProvider

    class Fixture:
        def __init__(self):
            self.provider_id = "fixture"

        def describe(self):
            return (asset(),)

        def variables(self):
            return (
                EnvironmentalVariable(
                    "fixture",
                    "Fixture",
                    "continuous",
                    "m",
                    TemporalRelationship.STATIC,
                    CoverageStatus.VALID,
                    (asset(),),
                ),
            )

    provider = Fixture()
    assert isinstance(provider, EnvironmentalProvider)
    assert provider.describe()[0].checksum == "a" * 64
    assert provider.variables()[0].variable_id == "fixture"
    probe = """
import json, sys, tempfile
from pathlib import Path
import numpy as np
from affine import Affine
import floodlab.environment.context as context
root=Path(tempfile.mkdtemp()); folder=root/'data/cache/v04'; folder.mkdir(parents=True)
(folder/'dem.bin').write_bytes(b'dem'); (folder/'rivers.geojson').write_text('{\\"features\\": []}')
(folder/'sources.json').write_text(json.dumps({'dem': {'file':'dem.bin','sha256':'a','product':'Copernicus DEM','version':'1'}, 'rivers': {'file':'rivers.geojson','sha256':'b','product':'HydroRIVERS','version':'1'}}))
context.sha256_file=lambda path: 'a' if path.name=='dem.bin' else 'b'
context.aligned=lambda *args, **kwargs: np.ma.masked_array(np.arange(4,dtype=float).reshape(2,2), mask=False)
context.vector_mask=lambda *args, **kwargs: np.array([[1,0],[0,0]], dtype=bool)
profile={'height':2,'width':2,'transform':Affine(20,0,0,0,-20,40),'crs':'EPSG:3857'}
aoi={'type':'Polygon','coordinates':[[[-.001,-.001],[.001,-.001],[.001,.001],[-.001,.001],[-.001,-.001]]]}
result=context.load_verified_static_context(root, profile, aoi)
assert result['arrays']['slope_degrees'].shape == (2,2)
assert not any(name.startswith(('openeo','floodlab.hazards','floodlab.impact')) for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, check=False, text=True
    )
    assert result.returncode == 0, result.stderr


def test_h3_sidecar_reconciles_a_generic_landslide_like_polygon_without_flood_imports():
    profile = {
        "height": 2,
        "width": 2,
        "transform": Affine(0.01, 0, -80.8, 0, -0.01, -5.1),
        "crs": "EPSG:4326",
    }
    arrays = {
        "valid": np.ones((2, 2), dtype=bool),
        "aoi": np.ones((2, 2), dtype=bool),
        "elevation_m": np.ones((2, 2)),
        "slope_degrees": np.ones((2, 2)),
        "mapped_drainage_distance_m": np.ones((2, 2)),
    }
    aoi = {
        "type": "Polygon",
        "coordinates": [
            [[-80.8, -5.12], [-80.78, -5.12], [-80.78, -5.1], [-80.8, -5.1], [-80.8, -5.12]]
        ],
    }
    result = environmental_h3_sidecar(aoi, profile, arrays, resolution=4, generated_utc="fixed")
    assert result["properties"]["h3_represented_valid_pixels"] == 4
    assert result["properties"]["h3_unrepresented_valid_pixels"] == 0


def test_labelled_h3_aggregation_matches_polygon_reference_on_controlled_grid():
    profile = {
        "height": 4,
        "width": 4,
        "transform": Affine(0.01, 0, -80.8, 0, -0.01, -5.1),
        "crs": "EPSG:4326",
    }
    values = np.arange(16, dtype=float).reshape(4, 4)
    arrays = {
        "valid": np.ones((4, 4), bool),
        "aoi": np.ones((4, 4), bool),
        "elevation_m": values,
        "slope_degrees": values,
        "mapped_drainage_distance_m": values,
    }
    aoi = {
        "type": "Polygon",
        "coordinates": [
            [[-80.8, -5.14], [-80.76, -5.14], [-80.76, -5.1], [-80.8, -5.1], [-80.8, -5.14]]
        ],
    }
    fast = environmental_h3_sidecar(aoi, profile, arrays, resolution=4, generated_utc="fixed")
    slow = {
        item["properties"]["h3_index"]: item["properties"]
        for item in polygon_reference_sidecar(aoi, profile, arrays, resolution=4)
    }
    for feature in fast["features"]:
        current = feature["properties"]
        reference = slow[current["h3_index"]]
        assert current["elevation_m"] == reference["elevation_m"]


def test_resolution_seven_equivalence_accounts_for_nodata_and_edge_pixels():
    profile = {
        "height": 10,
        "width": 10,
        "transform": Affine(0.002, 0, -80.8, 0, -0.002, -5.1),
        "crs": "EPSG:4326",
    }
    values = np.arange(100, dtype=float).reshape(10, 10)
    valid = np.ones((10, 10), bool)
    valid[0, 0] = valid[4, 5] = valid[9, 9] = False
    arrays = {
        "valid": valid,
        "aoi": np.ones((10, 10), bool),
        "elevation_m": values,
        "slope_degrees": values,
        "mapped_drainage_distance_m": values,
    }
    aoi = {
        "type": "Polygon",
        "coordinates": [
            [[-80.8, -5.12], [-80.78, -5.12], [-80.78, -5.1], [-80.8, -5.1], [-80.8, -5.12]]
        ],
    }
    fast = environmental_h3_sidecar(aoi, profile, arrays, resolution=7, generated_utc="fixed")
    slow = {
        item["properties"]["h3_index"]: item["properties"]
        for item in polygon_reference_sidecar(aoi, profile, arrays, resolution=7)
    }
    represented = [
        item for item in fast["features"] if item["properties"]["coverage_status"] == "VALID"
    ]
    assert len(represented) >= 2
    assert fast["properties"]["native_valid_pixels"] == 97
    assert (
        fast["properties"]["h3_represented_valid_pixels"]
        + fast["properties"]["h3_unrepresented_valid_pixels"]
        == 97
    )
    for feature in represented:
        assert (
            feature["properties"]["elevation_m"]
            == slow[feature["properties"]["h3_index"]]["elevation_m"]
        )


def test_environment_provenance_records_data_metadata_and_footprint_lineage(tmp_path):
    builder = runpy.run_path("scripts/build_piura_environment.py")
    root = tmp_path / "root"
    temporal = root / "outputs/analyses/fixture"
    temporal.mkdir(parents=True)
    for name, content in {
        "maximum-observed-single-date.tif": b"maximum",
        "event-observed-temporal-union.tif": b"union",
    }.items():
        (temporal / name).write_bytes(content)
    item = EnvironmentalVariable(
        "elevation_m",
        "Elevation",
        "continuous",
        "m",
        TemporalRelationship.STATIC,
        CoverageStatus.VALID,
        (asset(),),
        "aligned DEM",
        "test",
        {"method": "bilinear"},
        "test grid",
        derived_data_checksum="d" * 64,
        metadata_checksum="m" * 64,
        native_grid={"crs": "EPSG:4326", "width": 2},
        nodata_semantics="invalid excluded",
    )
    provenance = builder["build_environment_provenance"](
        root=root,
        source=temporal / "maximum-observed-single-date.tif",
        temporal=temporal,
        aoi_geometry={"type": "Polygon", "coordinates": []},
        context={"assets": [asset()], "variables": [item]},
        environment_config={"standard_event_resolution": 7},
    )
    variable = provenance["variables"][0]
    assert variable["derived_data_checksum"] == "d" * 64
    assert variable["metadata_checksum"] == "m" * 64
    assert variable["upstream_assets"][0]["checksum"] == "a" * 64
    assert variable["native_grid"]["crs"] == "EPSG:4326"
    assert variable["nodata_semantics"] == "invalid excluded"
    assert variable["temporal_relationship"] == "STATIC"
    assert variable["derivation_algorithm"] == "aligned DEM"
    assert (
        provenance["footprint_inputs"]["temporal_union"]["sha256"]
        == hashlib.sha256(b"union").hexdigest()
    )
    assert provenance["native_derived_arrays_exported"] is False


def test_explicit_multi_resolution_is_deterministic_and_directly_joinable():
    from floodlab.impact.engine import analyse_impact

    profile = {
        "height": 2,
        "width": 2,
        "transform": Affine(0.01, 0, -80.8, 0, -0.01, -5.1),
        "crs": "EPSG:4326",
    }
    arrays = {
        "valid": np.ones((2, 2), bool),
        "aoi": np.ones((2, 2), bool),
        "elevation_m": np.ones((2, 2)),
        "slope_degrees": np.ones((2, 2)),
        "mapped_drainage_distance_m": np.ones((2, 2)),
    }
    aoi = {
        "type": "Polygon",
        "coordinates": [
            [[-80.8, -5.12], [-80.78, -5.12], [-80.78, -5.1], [-80.8, -5.1], [-80.8, -5.12]]
        ],
    }
    four = environmental_h3_sidecar(aoi, profile, arrays, resolution=4, generated_utc="fixed")
    seven = environmental_h3_sidecar(
        aoi, profile, arrays, resolution=7, generated_utc="fixed", related_resolutions=(4,)
    )
    repeat = environmental_h3_sidecar(
        aoi, profile, arrays, resolution=7, generated_utc="fixed", related_resolutions=(4,)
    )
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
