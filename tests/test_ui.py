"""Exercise the rendered app without remote map tiles or catalogue calls."""

from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app/streamlit_app.py"


def test_app_starts_and_demo_loads():
    with patch("floodlab.ui.main.st_folium", return_value={}):
        app = AppTest.from_file(str(APP)).run(timeout=30)
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
