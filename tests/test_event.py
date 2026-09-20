"""Deterministic v0.3 tests: local fixtures, no remote processing."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from streamlit.testing.v1 import AppTest

from floodlab.eo_core.aoi import AOI
from floodlab.eo_core.catalogue import Acquisition
from floodlab.eo_core.event_selection import select_event_pair
from floodlab.eo_core.mask_io import export_mask, vectorize
from floodlab.hazards.flood.event import classify, compare_reference
from floodlab.hazards.flood.workflow import analyse_event

ROOT = Path(__file__).resolve().parents[1]


def test_evidence_windows_selection_and_rejection():
    aoi = AOI.read(ROOT / "config/aoi/piura2017.geojson")
    event = json.loads((ROOT / "config/piura2017-event.json").read_text())
    a = Acquisition(
        "a",
        "sentinel-1-grd",
        "2017-03-11T00:00:00Z",
        "s1b",
        "ascending",
        91,
        ["VV"],
        "IW",
        {},
        aoi.geojson()["geometry"],
    )
    b = replace(a, id="b", datetime="2017-04-04T00:00:00Z")
    contaminated = replace(a, id="c", datetime="2017-03-23T00:00:00Z")
    x, y, reason = select_event_pair([contaminated, b, a], aoi, event)
    assert (x.id, y.id) == ("a", "b") and reason["eligible_pairs"] == 1
    with pytest.raises(ValueError, match="No scientifically"):
        select_event_pair([contaminated, b], aoi, event)
    with pytest.raises(ValueError):
        select_event_pair([a, replace(b, relative_orbit=40)], aoi, event)
    with pytest.raises(ValueError):
        select_event_pair([a, b], aoi, dict(event, before_end="2017-04-05"))


def test_masks_exclude_existing_water_invalid_and_weak_change():
    before = np.array([[0.1, 0.001, 0.01], [0.1, 0.1, 0.0]])
    during = np.array([[0.001, 0.001, 0.009], [0.001, np.nan, 0.001]])
    valid = np.ones_like(before, dtype=bool)
    valid[1, 0] = False
    masks, method = classify(before, during, valid, threshold=-17, min_pixels=1)
    assert masks["flood"].sum() == 1 and masks["flood"][0, 0]
    assert masks["before"][0, 1] and not masks["flood"][0, 1]
    assert not masks["valid"][1].any()
    assert len(method["sensitivity"]) == 9
    with pytest.raises(ValueError, match="Insufficient"):
        classify(before, during, np.zeros_like(valid))


def test_comparison_categories_do_not_claim_accuracy():
    f = np.array([[1, 0], [1, 1]], bool)
    r = np.array([[1, 1], [0, 1]], bool)
    valid = np.array([[1, 1], [1, 0]], bool)
    comparison = compare_reference(f, r, valid)
    assert all(v.sum() == 1 for v in comparison.values())


def test_georeferenced_exports_area_and_nodata(tmp_path):
    profile = {
        "driver": "GTiff",
        "width": 3,
        "height": 2,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:32717",
        "transform": from_origin(500000, 9400000, 20, 20),
    }
    mask = np.array([[1, 1, 0], [0, 0, 0]], bool)
    valid = np.ones_like(mask)
    valid[1, 2] = False
    export_mask(tmp_path / "mask.tif", mask, valid, profile)
    with rasterio.open(tmp_path / "mask.tif") as src:
        assert src.nodata == 255 and src.read(1)[1, 2] == 255
    assert (
        vectorize(tmp_path / "flood.geojson", mask, profile["transform"], profile["crs"], 400) == 1
    )
    f = json.loads((tmp_path / "flood.geojson").read_text())["features"][0]
    assert f["properties"]["area_ha"] == pytest.approx(0.08)
    assert f["properties"]["pixels"] == 2
    assert -81 <= f["geometry"]["coordinates"][0][0][0] < -79


def test_event_missing_processing_never_submits(tmp_path):
    aoi = AOI.read(ROOT / "config/aoi/piura2017.geojson")
    event = json.loads((ROOT / "config/piura2017-event.json").read_text())
    a = Acquisition(
        "a",
        "s1",
        "2017-03-11T00:00:00Z",
        "s1b",
        "ascending",
        91,
        ["VV"],
        "IW",
        {},
        aoi.geojson()["geometry"],
    )
    b = replace(a, id="b", datetime="2017-04-04T00:00:00Z")
    with pytest.raises(ValueError, match="Additional authenticated processing"):
        analyse_event(tmp_path, aoi, event, observations=[a, b])


def test_primary_ui_hides_processing_and_reports_failures():
    with (
        patch("floodlab.ui.event.st_folium", return_value={}),
        patch(
            "floodlab.ui.event.analyse_event", side_effect=ValueError("Missing suitable imagery")
        ),
    ):
        app = AppTest.from_file(str(ROOT / "app/streamlit_app.py")).run(timeout=30)
        assert not app.exception
        assert app.sidebar.radio[0].value == "FLOOD EVENT"
        assert not app.code
        assert not any("orbit" in s.label.lower() for s in app.selectbox)
        next(b for b in app.button if b.label == "ANALYSE FLOOD EVENT").click().run()
        assert not app.exception and "Missing suitable imagery" in app.error[0].value


def test_event_pipeline_provenance_reference_and_integrity(tmp_path):
    from rasterio.warp import transform_bounds
    from shapely.geometry import box, mapping

    from floodlab.eo_core.pair_jobs import sha256_file

    event = json.loads((ROOT / "config/piura2017-event.json").read_text())
    folder = tmp_path / "data/cache/openeo/test"
    folder.mkdir(parents=True)
    bounds = transform_bounds("EPSG:32717", "EPSG:4326", 520000, 9409800, 520200, 9410000)
    aoi = AOI.from_geojson(mapping(box(*bounds)))
    a = Acquisition(
        "a",
        "s1",
        "2017-03-11T00:00:00Z",
        "s1b",
        "ascending",
        91,
        ["VV"],
        "IW",
        {},
        aoi.geojson()["geometry"],
    )
    b = replace(a, id="b", datetime="2017-04-04T00:00:00Z")
    outputs = {}
    for role in ["earlier", "later"]:
        values = np.full((10, 10), 0.1, dtype="float32")
        if role == "later":
            values[2:8, 2:8] = 0.001
        path = folder / f"{role}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=10,
            height=10,
            count=1,
            dtype="float32",
            crs="EPSG:32717",
            transform=from_origin(520000, 9410000, 20, 20),
            nodata=0,
        ) as dst:
            dst.write(values, 1)
        outputs[role] = {"raster": path.name, "sha256": sha256_file(path)}
    provenance = {
        "requested_observations": {"earlier": a.to_dict(), "later": b.to_dict()},
        "aoi": aoi.geojson(),
        "outputs": outputs,
    }
    (folder / "provenance.json").write_text(json.dumps(provenance))
    ref = tmp_path / "data/cache/references"
    ref.mkdir(parents=True)
    (ref / "indeci-piura2017.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": [aoi.geojson()]})
    )
    (ref / "reference-provenance.json").write_text(
        json.dumps(
            {"url": "https://example.org/synthetic-reference", "limitations": "Synthetic test only"}
        )
    )
    path = analyse_event(tmp_path, aoi, event, [a, b])
    result = json.loads(path.read_text())
    assert result["probable_flooded_area_ha"] == pytest.approx(1.44)
    assert result["status"] == "DRAFT"
    assert result["comparison"]["accuracy_metrics"] is None
    assert result["comparison"]["areas_ha"]["agreement"] == pytest.approx(1.44)
    assert result["selection"]["before"]["id"] == "a"
    assert result["processing_provenance_sha256"] == sha256_file(folder / "provenance.json")
    assert analyse_event(tmp_path, aoi, event, [a, b]) == path
    (path.parent / "flood.tif").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="integrity"):
        analyse_event(tmp_path, aoi, event, [a, b])
