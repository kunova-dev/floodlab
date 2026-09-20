"""Exercise the rendered app without remote map tiles or catalogue calls."""

from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app/streamlit_app.py"


def test_app_starts_and_demo_loads():
    with patch("floodlab.ui.main.st_folium", return_value={}):
        app = AppTest.from_file(str(APP)).run(timeout=30)
        app.sidebar.radio[0].set_value("FLOOD HISTORY").run()
        assert not app.exception
        app.button[0].click().run()
        assert not app.exception
        assert "NOT AUTHORITATIVE" in app.session_state["aoi"].name
        app.sidebar.radio[0].set_value("FLOOD LAB").run()
        assert not app.exception
        app.sidebar.radio[0].set_value("FLOOD WATCH").run()
        assert not app.exception
        app.sidebar.radio[0].set_value("IMPACT").run()
        assert not app.exception


def test_offline_catalogue_error():
    with (
        patch("floodlab.ui.main.st_folium", return_value={}),
        patch("floodlab.ui.main.StacCatalogue.search", side_effect=ConnectionError("offline test")),
    ):
        app = AppTest.from_file(str(APP)).run(timeout=30)
        app.sidebar.radio[0].set_value("FLOOD HISTORY").run()
        app.button[0].click().run()
        next(b for b in app.button if b.label == "Search Sentinel-1 catalogue").click().run()
        assert not app.exception
        assert "Live catalogue access unavailable" in app.error[0].value


def test_selection_survives_lab_reruns():
    from floodlab.eo_core.aoi import AOI
    from floodlab.eo_core.catalogue import Acquisition

    aoi = AOI.read(APP.parents[1] / "config/aoi/piura2017.geojson")
    observation = Acquisition(
        "synthetic-ui-test",
        "sentinel-1-grd",
        "2017-03-15T12:00:00Z",
        "sentinel-1a",
        "ascending",
        18,
        ["VV"],
        "IW",
        {},
        aoi.geojson()["geometry"],
    )
    with (
        patch("floodlab.ui.main.st_folium", return_value={}),
        patch("floodlab.ui.main.StacCatalogue.search", return_value=[observation]),
    ):
        app = AppTest.from_file(str(APP)).run(timeout=30)
        app.sidebar.radio[0].set_value("FLOOD HISTORY").run()
        app.button[0].click().run()
        next(b for b in app.button if b.label == "Search Sentinel-1 catalogue").click().run()
        app.multiselect[0].set_value(["synthetic-ui-test"]).run()
        assert not app.exception
        app.sidebar.radio[0].set_value("FLOOD LAB").run()
        assert not app.exception
        app.run()
        assert app.session_state["selected_ids"] == ["synthetic-ui-test"]
        assert not app.exception
        assert any("Awaiting preprocessing" in x.value for x in app.warning)


def test_pair_ui_creates_plan_without_authentication(tmp_path):
    from dataclasses import replace

    from floodlab.eo_core.aoi import AOI
    from floodlab.eo_core.catalogue import Acquisition
    from floodlab.eo_core.config import Config, load_config

    cfg = load_config(APP.parents[1] / "config/piura2017.toml")
    cfg = Config(tmp_path, cfg.values)
    aoi = AOI.read(APP.parents[1] / "config/aoi/piura2017.geojson")
    a = Acquisition(
        "synthetic-earlier",
        "sentinel-1-grd",
        "2017-03-11T23:43:11Z",
        "sentinel-1b",
        "ascending",
        91,
        ["VV"],
        "IW",
        {},
        aoi.geojson()["geometry"],
    )
    b = replace(a, id="synthetic-later", datetime="2017-04-04T23:43:11Z")
    with (
        patch("floodlab.ui.main.load_config", return_value=cfg),
        patch("floodlab.ui.main.st_folium", return_value={}),
    ):
        app = AppTest.from_file(str(APP)).run(timeout=30)
        app.sidebar.radio[0].set_value("FLOOD HISTORY").run()
        app.session_state["search"] = {
            "acquisitions": [a, b],
            "aoi": aoi.geojson(),
            "endpoint": "https://example.org",
            "query": {},
            "cap": 100,
        }
        app.session_state["selected_ids"] = [a.id, b.id]
        app.sidebar.radio[0].set_value("FLOOD LAB").run()
        assert not app.exception
        next(
            button for button in app.button if button.label == "Prepare openEO pair plan"
        ).click().run()
        assert not app.exception
        assert any(metric.value == "NOT AUTHENTICATED" for metric in app.metric)
        assert len(list((tmp_path / "data/cache/openeo").glob("*/plan.json"))) == 1
        assert any("scripts/process_pair.py" in code.value for code in app.code)
