"""FloodLab investigation UI."""

import json
from datetime import date
from hashlib import sha256
from pathlib import Path

import folium
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

from floodlab.eo_core.aoi import AOI
from floodlab.eo_core.catalogue import StacCatalogue, query
from floodlab.eo_core.config import load_config
from floodlab.eo_core.processing import ProcessingJob, readiness
from floodlab.ui.event import show_event
from floodlab.ui.impact import show_saved_impact
from floodlab.ui.processing import show_pair_processing

ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    st.set_page_config(page_title="FloodLab | Earth observation", page_icon="🌊", layout="wide")
    st.markdown(
        """<style>
    .block-container {padding-top:2rem; max-width:1450px}
    h1 {letter-spacing:-.05em; color:#123747}
    [data-testid="stSidebar"] {background:#f3f7f8}
    div[data-testid="stMetric"] {background:#f3f7f8;padding:18px;border-radius:10px}
    </style>""",
        unsafe_allow_html=True,
    )
    try:
        cfg = load_config(ROOT / "config/piura2017.toml")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(f"Configuration could not be loaded: {exc}")
        return
    st.sidebar.title("FLOODLAB")
    st.sidebar.caption("EARTH OBSERVATION | v0.5a")
    page = st.sidebar.radio(
        "Workspace", ["FLOOD EVENT", "FLOOD HISTORY", "FLOOD LAB", "FLOOD WATCH", "IMPACT"], index=0
    )
    st.sidebar.divider()
    st.sidebar.caption(
        "Experimental satellite-derived inundation. Requires independent validation."
    )
    if page == "FLOOD EVENT":
        show_event(cfg)
        return
    if page == "FLOOD WATCH":
        st.title("Flood Watch")
        st.write("A foundation for repeatable observation monitoring.")
        st.info("Scheduling, ingestion and alert delivery are not implemented in v0.1.")
        st.markdown("Saved AOI → catalogue adapter → processing job → flood indicators → review")
        return
    if page == "IMPACT":
        show_saved_impact(cfg.root)
        return
    if page == "FLOOD LAB":
        show_lab(cfg)
        return
    st.title("Flood History")
    st.write("Find satellite observations. Build an auditable investigation.")
    left, right = st.columns([1, 2.4], gap="large")
    with left:
        st.subheader("1 · Define your search")
        if st.button("Load Piura 2017 demo AOI", type="primary", use_container_width=True):
            st.session_state.aoi = AOI.read(cfg.path(cfg.values["demo"]["aoi"]))
            st.session_state.pop("search", None)
            st.session_state.pop("selected_ids", None)
            st.session_state.pop("_selected_ids", None)
        st.caption("DEMO AOI — NOT AUTHORITATIVE FLOOD EXTENT")
        upload = st.file_uploader("Or upload a WGS84 polygon", type=["geojson", "json"])
        if upload is not None and st.button("Use uploaded AOI"):
            try:
                st.session_state.aoi = AOI.from_geojson(json.loads(upload.getvalue()))
                st.session_state.pop("search", None)
            except (ValueError, KeyError, TypeError) as exc:
                st.error(f"Invalid AOI: {exc}")
        start = st.date_input("From (UTC)", date.fromisoformat(cfg.values["demo"]["start"]))
        end = st.date_input(
            "Through (UTC, inclusive)", date.fromisoformat(cfg.values["demo"]["end"])
        )
        with st.expander("Catalogue settings"):
            endpoint = st.text_input("STAC endpoint", cfg.values["catalogue"]["endpoint"])
            collection = st.text_input("Collection", cfg.values["catalogue"]["collection"])
            maximum = st.number_input("Result cap", 1, 1000, cfg.values["catalogue"]["max_items"])
        search = st.button("Search Sentinel-1 catalogue", use_container_width=True)
    aoi = st.session_state.get("aoi")
    with right:
        st.subheader("Search area")
        center = [aoi.geometry.centroid.y, aoi.geometry.centroid.x] if aoi else [0, 0]
        map_view = folium.Map(location=center, zoom_start=9 if aoi else 2, tiles="OpenStreetMap")
        if aoi:
            folium.GeoJson(
                aoi.geojson(),
                style_function=lambda _: {"color": "#168a92", "weight": 2, "fillOpacity": 0.12},
            ).add_to(map_view)
            west, south, east, north = aoi.geometry.bounds
            map_view.fit_bounds([[south, west], [north, east]])
        Draw(
            draw_options={
                "polyline": False,
                "circle": False,
                "circlemarker": False,
                "marker": False,
            },
            edit_options={"edit": False, "remove": False},
        ).add_to(map_view)
        drawn = st_folium(
            map_view,
            height=430,
            use_container_width=True,
            returned_objects=["last_active_drawing"],
            key="aoi_map_" + (sha256(aoi.geometry.wkb).hexdigest()[:12] if aoi else "global"),
        )
        if drawn and drawn.get("last_active_drawing") and st.button("Use drawn polygon as AOI"):
            try:
                st.session_state.aoi = AOI.from_geojson(drawn["last_active_drawing"])
                st.session_state.pop("search", None)
                st.rerun()
            except (ValueError, KeyError, TypeError) as exc:
                st.error(f"Invalid drawing: {exc}")
        st.caption(
            aoi.name if aoi else "Load the demo, upload GeoJSON, or draw a polygon to begin."
        )
        st.caption(
            "Basemap tiles require network access; the AOI overlay is independent of tile availability."
        )
    if search:
        st.session_state.pop("search", None)
        st.session_state.pop("selected_ids", None)
        st.session_state.pop("_selected_ids", None)
        if not aoi:
            st.warning("Define an AOI before searching.")
        elif not endpoint.startswith("https://"):
            st.error("Use an HTTPS STAC endpoint.")
        else:
            try:
                with st.spinner("Checking collection and searching acquisitions…"):
                    arguments = query(aoi, start, end, collection, maximum)
                    acquisitions = StacCatalogue(endpoint, collection, maximum).search(
                        aoi, start, end
                    )
                st.session_state.search = {
                    "acquisitions": acquisitions,
                    "query": arguments,
                    "aoi": aoi.geojson(),
                    "endpoint": endpoint,
                    "cap": maximum,
                }
            except Exception as exc:  # noqa: BLE001 -- isolate provider failures at UI boundary
                st.error(
                    f"Live catalogue access unavailable or query rejected: {type(exc).__name__}: {exc}"
                )
                st.caption(
                    "The application remains usable. Check connectivity, dates and the collection identifier. No satellite results have been substituted."
                )
    show_results()


def show_results() -> None:
    context = st.session_state.get("search")
    if context is None:
        return
    observations = context["acquisitions"]
    st.subheader("2 · Inspect acquisitions")
    st.caption("Results describe the AOI and query from the most recent successful search.")
    st.metric("Matching acquisitions returned", len(observations))
    if len(observations) >= context["cap"]:
        st.warning(
            "Result cap reached. This may be a partial timeline; narrow dates or increase the cap."
        )
    if not observations:
        st.info(
            "No matching acquisitions returned. This is not evidence that flooding did not occur."
        )
        return
    st.dataframe(
        [
            {
                "ID": x.id,
                "UTC": x.datetime,
                "Platform": x.platform,
                "Orbit": x.orbit,
                "Relative orbit": x.relative_orbit,
                "Polarizations": ", ".join(x.polarizations),
            }
            for x in observations
        ],
        use_container_width=True,
    )
    ids = [x.id for x in observations]
    old = st.session_state.get("selected_ids", [])
    if any(x not in ids for x in old):
        st.session_state.pop("selected_ids", None)
        st.session_state.pop("_selected_ids", None)
    if "_selected_ids" not in st.session_state:
        st.session_state._selected_ids = [x for x in old if x in ids]
    st.session_state.selected_ids = st.multiselect(
        "Observations to prepare", ids, key="_selected_ids"
    )
    inspected = st.selectbox("Inspect acquisition metadata and asset links", ids)
    st.json(next(x.to_dict() for x in observations if x.id == inspected))
    st.caption(
        "Assets may require authentication or deferred retrieval. Asset presence does not establish calibration or terrain correction."
    )
    st.info("Open FLOOD LAB to review selected observations and export a preparation manifest.")


def show_lab(cfg) -> None:
    st.title("Flood Lab")
    st.write("Review observation comparability and prepare the next processing stage.")
    context = st.session_state.get("search")
    if not context:
        st.info("Search an AOI in FLOOD HISTORY first.")
        return
    show_pair_processing(cfg, context)
    st.divider()
    st.subheader("Catalogue preparation manifest")
    selected = [
        x for x in context["acquisitions"] if x.id in st.session_state.get("selected_ids", [])
    ]
    if not selected:
        st.info("Select observations in FLOOD HISTORY to prepare an investigation.")
        return
    st.json(readiness(selected))
    st.warning(
        "Awaiting preprocessing. No flood classification or real inundation indicator has been computed."
    )
    job = ProcessingJob(
        [x.to_dict() for x in selected],
        context["aoi"],
        context["endpoint"],
        context["query"],
        cfg.values,
    )
    st.download_button(
        "Download preparation manifest",
        json.dumps(job.to_dict(), indent=2),
        file_name="floodlab-preparation.json",
        mime="application/json",
    )
    st.caption(
        "Manifest records source items, query, AOI, configuration, timestamp and assumptions. It does not submit a remote processing job."
    )
    st.subheader("Analysis readiness")
    st.markdown(
        "Required next: calibrated and terrain-corrected backscatter, a common grid and polarization, valid-data masks, a suitable baseline, and a reviewed permanent-water layer."
    )
