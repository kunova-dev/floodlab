"""Scientific domain, evidence states, optional failures and immutable package contracts."""

import hashlib
import json
import zipfile
from unittest.mock import patch

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from shapely.geometry import box, mapping

from floodlab.eo_core.aoi import AOI
from floodlab.eo_core.context import read_sources
from floodlab.eo_core.gauges import validate_gauge_observations
from floodlab.eo_core.pair_jobs import sha256_file, write_json
from floodlab.eo_core.public_stac import cached_search
from floodlab.hazards.flood.evidence import baseline_classes, evidence_classes, optical_water
from floodlab.hazards.flood.reconstruction import reconstruct


def test_baseline_unknown_is_not_dry_and_ocean_is_separate():
    history = np.array([[[1, 2, 3, 0, 0, 1]], [[1, 1, 3, 0, 1, 1]]])
    land = np.array([[1, 1, 1, 1, 1, 0]], bool)
    assert baseline_classes(history, land).tolist() == [[1, 2, 3, 4, 4, 0]]
    occurrence = np.array([[0, 0, 100, 0, 255, 0]])
    assert baseline_classes(history, land, occurrence).tolist() == [[1, 2, 3, 1, 4, 0]]
    with pytest.raises(ValueError):
        baseline_classes(history[:1], land)
    with pytest.raises(ValueError):
        baseline_classes(history + 10, land)


def test_clouds_shadows_and_invalid_optical_are_not_dry():
    green = np.full((9, 9), 0.2)
    swir = np.full((9, 9), 0.05)
    scl = np.full((9, 9), 4)
    scl[4, 4] = 9
    water, valid = optical_water(green, swir, scl, cloud_buffer_pixels=1)
    assert water[0, 0] and not valid[4, 4] and not valid[4, 3]
    for code in [0, 1, 2, 3, 7, 8, 9, 10, 11]:
        assert not optical_water(green, swir, np.full((9, 9), code))[1].any()
    green[0, 0] = np.nan
    assert not optical_water(green, swir, scl)[1][0, 0]


def test_evidence_states_do_not_union_sensors_or_make_probabilities():
    s1 = np.array([[1, 1, 1, 0, 1, 1, 1]], bool)
    s2 = np.array([[1, 1, 0, 1, 1, 1, 1]], bool)
    baseline = np.array([[1, 1, 1, 1, 3, 0, 4]])
    valid = np.ones_like(s1)
    s2valid = valid.copy()
    s2valid[0, 1] = False
    assert evidence_classes(s1, baseline, valid, s2, s2valid).tolist() == [[1, 2, 3, 4, 5, 6, 7]]
    assert evidence_classes(s1, baseline, valid).tolist() == [[2, 2, 2, 0, 5, 6, 7]]


def test_gauge_provenance_units_timezone_and_rating_curve():
    assert validate_gauge_observations([]) == []
    record = {
        "station_id": "fixture",
        "timestamp": "2017-03-27T10:00:00-05:00",
        "value": 10.0,
        "units": "m3/s",
        "variable": "discharge",
        "provider": "fixture",
        "source_url": "https://example.org",
        "quality": "unchecked",
    }
    assert validate_gauge_observations([record])
    for changes in [
        {"timestamp": "2017-03-27"},
        {"units": "feet"},
        {"value": float("nan")},
        {"derived_from_stage": True},
    ]:
        with pytest.raises(ValueError):
            validate_gauge_observations([{**record, **changes}])


@pytest.fixture
def reconstruction_fixture(tmp_path):
    root = tmp_path
    context = root / "data/cache/v04"
    context.mkdir(parents=True)
    config = root / "config"
    config.mkdir()
    old = root / "outputs/events/fixture"
    old.mkdir(parents=True)
    profile = {
        "driver": "GTiff",
        "width": 10,
        "height": 10,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:32717",
        "transform": from_origin(520000, 9410000, 20, 20),
    }

    def raster(path, array):
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(array.astype("float32"), 1)

    bounds = transform_bounds("EPSG:32717", "EPSG:4326", 520000, 9409800, 520200, 9410000)
    land_bounds = transform_bounds("EPSG:32717", "EPSG:4326", 520100, 9409800, 520200, 9410000)
    aoi = AOI.from_geojson(mapping(box(*bounds)))
    write_json(
        context / "land.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": mapping(box(*land_bounds)), "properties": {}}
            ],
        },
    )
    raster(root / "earlier.tif", np.full((10, 10), 0.1))
    raster(root / "later.tif", np.full((10, 10), 0.001))
    raster(old / "flood.tif", np.ones((10, 10)))
    history = np.ones((10, 10))
    history[:, 5] = 3
    history[:, 6] = 0
    for year in [2013, 2014, 2015]:
        raster(context / f"water-{year}.tif", history)
    sources = {
        key: {
            "file": file,
            "sha256": sha256_file(context / file),
            "url": "https://example.org/synthetic-test-only",
        }
        for key, file in [("land", "land.geojson")]
        + [(f"water-{y}", f"water-{y}.tif") for y in [2013, 2014, 2015]]
    }
    write_json(context / "sources.json", sources)
    settings = {
        "bbox": list(bounds),
        "baseline_years": [2013, 2014, 2015],
        "sar_water_db": -18,
        "sar_drop_db": -3,
        "min_pixels": 1,
        "optical_max_pair_days": 7,
        "optical_min_usable_fraction": 0.05,
    }
    write_json(config / "v04.json", settings)
    legacy = {
        "input_rasters": ["earlier.tif", "later.tif"],
        "method": {"min_pixels": 1},
        "selection": {"during": {"datetime": "2017-04-04T00:00:00Z"}},
    }
    write_json(old / "result.json", legacy)
    return root, aoi, {"before_end": "2017-03-16"}, old / "result.json", profile


@pytest.mark.parametrize("optical_state", ["missing", "corrupt", "cloudy", "clear"])
def test_full_reconstruction_land_package_and_optional_failures(
    reconstruction_fixture, optical_state
):
    root, aoi, event, legacy, profile = reconstruction_fixture
    folder = root / "data/cache/v04"
    if optical_state != "missing":
        periods = {}
        for role, date in [("before", "2017-01-10"), ("during", "2017-03-31")]:
            path = folder / f"s2-{role}.tif"
            values = np.full((10, 10), 255 if optical_state == "cloudy" else int(role == "during"))
            with rasterio.open(path, "w", **profile) as dst:
                dst.write(values.astype("float32"), 1)
            periods[role] = {
                "file": path.name,
                "date": date,
                "sha256": sha256_file(path) if optical_state != "corrupt" else "bad",
            }
        write_json(folder / "optical.json", {"periods": periods})
    # Malformed optional gauge input must also degrade to unavailable.
    write_json(root / "config/piura-gauges.json", {"observations": [{}]})
    with patch("floodlab.hazards.flood.reconstruction.analyse_event", return_value=legacy):
        path = reconstruct(root, aoi, event)
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["metrics"]["ocean_flood_pixels"] == 0
    assert report["metrics"]["v03_offshore_flood_ha"] == pytest.approx(2.0)
    assert report["probable_flooded_area_ha"] == pytest.approx(1.2)
    assert report["gauges"]["status"] == "unavailable"
    assert report["comparison"]["accuracy_metrics"] is None
    if optical_state == "clear":
        assert report["evidence_area_ha"]["1"] == pytest.approx(1.2)
    else:
        assert report["evidence_area_ha"]["2"] == pytest.approx(1.2)
    for name in ["flood", "before", "during", "s1-evidence"]:
        with rasterio.open(path.parent / f"{name}.tif") as src:
            assert (
                src.crs == rasterio.crs.CRS.from_epsg(32717)
                and src.transform == profile["transform"]
            )
            assert np.all(src.read(1)[:, :5] == 255)
    assert report["checks"]["vector_area_ha"] == pytest.approx(1.2)
    checks = json.loads((path.parent / "checksums.json").read_text())
    with zipfile.ZipFile(path.parent / "analysis.zip") as archive:
        assert archive.testzip() is None
        for name, digest in checks.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
    before = sha256_file(path)
    with patch("floodlab.hazards.flood.reconstruction.analyse_event", return_value=legacy):
        second = reconstruct(root, aoi, event)
    assert second != path and sha256_file(path) == before


def test_mandatory_land_integrity(reconstruction_fixture):
    root, _aoi, _event, _legacy, _ = reconstruction_fixture
    context = root / "data/cache/v04"
    (context / "land.geojson").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        read_sources(context, [2013, 2014, 2015])


def test_future_baseline_and_outside_context_are_rejected(reconstruction_fixture):
    root, aoi, event, _, _ = reconstruction_fixture
    with pytest.raises(ValueError, match="precede"):
        reconstruct(root, aoi, {**event, "before_end": "2015-03-16"})
    other = AOI.from_geojson(mapping(box(-82, -6, -81, -5)))
    with pytest.raises(ValueError, match="exceeds prepared"):
        reconstruct(root, other, event)


def test_public_catalogue_pagination_and_cached_read(tmp_path):
    from unittest.mock import Mock

    first = Mock()
    first.json.return_value = {
        "features": [{"id": "1"}],
        "links": [{"rel": "next", "href": "https://example.org/page2"}],
    }
    second = Mock()
    second.json.return_value = {"features": [{"id": "2"}], "links": []}
    with patch("floodlab.eo_core.public_stac.requests.get", side_effect=[first, second]) as get:
        result = cached_search(tmp_path / "catalog.json", "sentinel-2-l2a", [-81, -6, -80, -5])
        assert len(result["features"]) == 2 and get.call_count == 2
        assert (
            cached_search(tmp_path / "catalog.json", "sentinel-2-l2a", []) == result
            and get.call_count == 2
        )
