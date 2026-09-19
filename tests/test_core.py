from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from floodlab.eo_core.aoi import AOI
from floodlab.eo_core.catalogue import StacCatalogue, normalize, query
from floodlab.eo_core.config import load_config
from floodlab.eo_core.processing import ProcessingJob, readiness
from floodlab.hazards.flood.engine import (
    analyze,
    change_db,
    cleanup,
    inundated_area,
    otsu_threshold,
    pixel_area_m2,
    to_db,
    water_mask,
)
from floodlab.history.events import Indicator, detect_events
from scripts.bootstrap import bootstrap

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def aoi():
    return AOI.read(ROOT / "config/aoi/piura2017.geojson")


@pytest.fixture
def item(aoi):
    return {
        "id": "synthetic-test-item",
        "collection": "sentinel-1-grd",
        "geometry": aoi.geojson()["geometry"],
        "assets": {"vv": {"href": "s3://example/vv"}},
        "properties": {
            "datetime": "2017-03-15T12:00:00Z",
            "platform": "sentinel-1a",
            "sat:orbit_state": "ascending",
            "sat:relative_orbit": 18,
            "sar:polarizations": ["VV", "VH"],
            "sar:instrument_mode": "IW",
        },
    }


def test_config():
    cfg = load_config(ROOT / "config/piura2017.toml")
    assert cfg.path(cfg.values["demo"]["aoi"]).is_file()
    assert cfg.values["catalogue"]["collection"] == "sentinel-1-grd"


def test_bad_config(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text(
        (ROOT / "config/piura2017.toml").read_text().replace("max_items = 100", "max_items = 0")
    )
    with pytest.raises(ValueError):
        load_config(path)


def test_aoi_roundtrip(aoi):
    assert AOI.from_geojson(aoi.geojson()).geometry.equals(aoi.geometry)
    assert "NOT AUTHORITATIVE" in aoi.name


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [0, 0]},
        {"type": "Polygon", "coordinates": [[[200, 0], [201, 0], [201, 1], [200, 0]]]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]},
        {"type": "FeatureCollection", "features": []},
        {"type": "Polygon", "coordinates": [[[179, 0], [-179, 0], [-179, 1], [179, 0]]]},
    ],
)
def test_invalid_aoi(geometry):
    with pytest.raises(ValueError):
        AOI.from_geojson(geometry)


def test_bootstrap(tmp_path):
    assert all(x.startswith("CREATED") for x in bootstrap(tmp_path))
    file = tmp_path / "data/user_uploads/keep.txt"
    file.write_text("preserve me")
    assert all(x.startswith("OK") for x in bootstrap(tmp_path))
    assert file.read_text() == "preserve me"


def test_bootstrap_collision(tmp_path):
    (tmp_path / "data").write_text("user data")
    with pytest.raises((FileExistsError, NotADirectoryError)):
        bootstrap(tmp_path)
    assert (tmp_path / "data").read_text() == "user data"


def test_catalogue_query(aoi):
    result = query(aoi, date(2017, 3, 1), date(2017, 3, 31), "sentinel-1-grd", 50)
    assert result["datetime"].endswith("2017-03-31T23:59:59.999999Z")
    assert result["intersects"]["type"] == "Polygon"
    with pytest.raises(ValueError):
        query(aoi, date(2017, 4, 1), date(2017, 3, 1), "x", 50)


def test_normalization(item):
    assert normalize(item).polarizations == ["VV", "VH"]
    assert normalize(item).relative_orbit == 18
    item["properties"] = {"start_datetime": "2017-03-15T12:00:00Z"}
    assert normalize(item).orbit is None
    assert normalize(item).polarizations == []


def test_catalogue_mock_filters(aoi, item):
    from copy import deepcopy

    outside = deepcopy(item)
    outside["geometry"] = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    late = deepcopy(item)
    late["properties"]["datetime"] = "2020-01-01T00:00:00Z"
    client = MagicMock()
    client.search.return_value.items_as_dicts.return_value = [item, outside, late]
    with patch("floodlab.eo_core.catalogue.Client.open", return_value=client):
        result = StacCatalogue("https://example.com", "sentinel-1-grd").search(
            aoi, date(2017, 3, 1), date(2017, 3, 31)
        )
    assert len(result) == 1
    client.get_collection.assert_called_once_with("sentinel-1-grd")


def test_job_and_readiness(aoi, item):
    observation = normalize(item)
    assert not readiness([observation])["paired_candidates"]
    job = ProcessingJob([observation.to_dict()], aoi.geojson(), "test", {}, {})
    assert job.to_dict()["status"] == "AWAITING_PREPROCESSING"


def test_db():
    result = to_db([1, 0.1, 0.01, 0, -1, np.nan, np.inf])
    np.testing.assert_allclose(result[:3], [0, -10, -20])
    assert np.isnan(result[3:]).all()


def test_threshold_change():
    np.testing.assert_array_equal(water_mask([-20, -17, -10, np.nan]), [True, True, False, False])
    np.testing.assert_allclose(change_db([-10, np.nan], [-20, -20]), [-10, np.nan])
    with pytest.raises(ValueError):
        change_db([1], [1, 2])


def test_new_inundation_and_exclusion():
    before = np.array([[-10, -20], [-10, np.nan]])
    event = np.full((2, 2), -22.0)
    result = analyze(before, event, 100, min_pixels=1)
    assert result.observed_derived["probable_new_inundation_m2"] == 200
    assert result.qc_confidence["valid_fraction"] == 0.75
    exclusion = np.array([[True, False], [False, False]])
    assert analyze(before, event, 100, min_pixels=1, permanent_water=exclusion).mask.sum() == 1
    with pytest.raises(ValueError):
        analyze(before, event, 100, permanent_water=np.zeros((1, 1), dtype=bool))


def test_cleanup():
    mask = np.array([[1, 1, 0], [0, 0, 0], [0, 0, 1]], dtype=bool)
    assert cleanup(mask, 2).sum() == 2


def test_area():
    assert pixel_area_m2((10, 0, 0, 0, -10, 0), crs_units="metre") == 100
    assert inundated_area([[True, False]], [[50, 100]]) == 50
    with pytest.raises(ValueError):
        pixel_area_m2((0.1, 0, 0, 0, -0.1, 0), crs_units="degree")
    with pytest.raises(ValueError):
        inundated_area([True], -100)


def test_otsu():
    threshold = otsu_threshold([-22, -21, -20, -7, -6, -5])
    assert -20 < threshold < -7
    with pytest.raises(ValueError):
        otsu_threshold([1, 1])


def test_event_grouping():
    observations = [
        Indicator(date(2017, 3, day), fraction, str(day))
        for day, fraction in [(25, 0.3), (1, 0.2), (7, 0.4), (10, 0.01)]
    ]
    threshold, events = detect_events(observations, [0.01, 0.01, 0.01], gap_days=6)
    assert threshold == pytest.approx(0.03)
    assert len(events) == 2
    assert events[0].peak_observed == date(2017, 3, 7)
    assert events[0].observation_ids == ["1", "7"]
    assert detect_events([], [0.01, 0.02, 0.03])[1] == []
    with pytest.raises(ValueError):
        detect_events(observations, [np.nan, 0, 0])


@pytest.mark.parametrize(
    "old,new",
    [
        ("drop_db = -3.0", "drop_db = 1.0"),
        ("anomaly_multiplier = 3.0", "anomaly_multiplier = nan"),
        ("minimum_excess = 0.02", "minimum_excess = inf"),
        ("min_pixels = 4", "min_pixels = 4.5"),
        ("gap_days = 12", "gap_days = nan"),
        ("https://stac.dataspace.copernicus.eu/v1", "https:///v1"),
        ("https://stac.dataspace.copernicus.eu/v1", "https://user:example@example.com/v1"),
    ],
)
def test_invalid_operational_config(tmp_path, old, new):
    path = tmp_path / "invalid.toml"
    path.write_text((ROOT / "config/piura2017.toml").read_text().replace(old, new))
    with pytest.raises(ValueError):
        load_config(path)


@pytest.mark.parametrize(
    "value",
    [
        {"type": "Feature", "geometry": None},
        {"type": "Feature", "properties": ["bad"], "geometry": {}},
        {"type": "FeatureCollection", "features": None},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]},
    ],
)
def test_malformed_aoi_is_validation_error(value):
    with pytest.raises((TypeError, ValueError)):
        AOI.from_geojson(value)
