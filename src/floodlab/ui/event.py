"""Simple event experience; satellite implementation details remain inspectable."""

import json
from pathlib import Path

import folium
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

from floodlab.eo_core.aoi import AOI
from floodlab.hazards.flood.reconstruction import reconstruct as analyse_event
from floodlab.ui.impact import show_impact


def show_event(cfg):
    st.title("Piura, Peru")
    st.subheader("March 2017 flood")
    st.write("Where did flooding occur, and how did surface water change?")
    event = json.loads((cfg.root / "config/piura2017-event.json").read_text(encoding="utf-8"))
    choice = st.selectbox("Area of interest", ["Piura reference area", "Draw or upload an area"])
    aoi = (
        AOI.read(cfg.root / "config/aoi/piura2017.geojson")
        if choice == "Piura reference area"
        else st.session_state.get("event_aoi", st.session_state.get("aoi"))
    )
    st.selectbox("Flood event", ["Piura · 27 March 2017 escalation / early-April inundation"])
    st.caption(
        "Before shows historical persistent/seasonal water. During shows water observed on April 4, not the March 27 peak. The flood footprint excludes ocean and known historical water."
    )
    if choice == "Draw or upload an area":
        upload = st.file_uploader("Area polygon (GeoJSON)", type=["geojson", "json"])
        if upload is not None:
            try:
                aoi = AOI.from_geojson(json.loads(upload.getvalue()))
                st.session_state.event_aoi = aoi
            except (ValueError, KeyError, TypeError) as exc:
                st.error(f"Invalid area: {exc}")
                return
        if aoi is None:
            aoi = AOI.read(cfg.root / "config/aoi/piura2017.geojson")
        draw_map = folium.Map(
            location=[aoi.geometry.centroid.y, aoi.geometry.centroid.x], zoom_start=10
        )
        Draw(
            draw_options={
                "polyline": False,
                "circle": False,
                "circlemarker": False,
                "marker": False,
            },
            edit_options={"edit": False, "remove": False},
        ).add_to(draw_map)
        drawn = st_folium(
            draw_map, height=300, key="event_draw", returned_objects=["last_active_drawing"]
        )
        if drawn and drawn.get("last_active_drawing") and st.button("Use drawn area"):
            try:
                st.session_state.event_aoi = AOI.from_geojson(drawn["last_active_drawing"])
                st.rerun()
            except (ValueError, KeyError, TypeError) as exc:
                st.error(f"Invalid area: {exc}")
        st.caption(
            "The selected event remains Piura 2017. Areas outside available coverage may need additional processing."
        )
    key = json.dumps(aoi.geojson(), sort_keys=True)
    if st.button("ANALYSE FLOOD EVENT", type="primary"):
        st.session_state.pop("event_result", None)
        try:
            with st.spinner(
                "Selecting observations, checking coverage and analysing surface-water change…"
            ):
                path = analyse_event(cfg.root, aoi, event)
            st.session_state.event_result = {"aoi_key": key, "path": str(path)}
        except (OSError, ValueError, KeyError) as exc:
            st.error(f"Analysis unavailable: {exc}")
    saved = st.session_state.get("event_result")
    if not saved or saved["aoi_key"] != key:
        m = folium.Map(location=[aoi.geometry.centroid.y, aoi.geometry.centroid.x], zoom_start=10)
        folium.GeoJson(
            aoi.geojson(), style_function=lambda _: {"color": "#334155", "fillOpacity": 0.05}
        ).add_to(m)
        west, south, east, north = aoi.geometry.bounds
        m.fit_bounds([[south, west], [north, east]])
        st_folium(m, height=470, use_container_width=True, key="event_aoi", returned_objects=[])
        st.info(
            "Analyse this event to view real satellite-derived water layers. Existing compatible processing is reused; no remote jobs are launched by this page."
        )
        return
    path = Path(saved["path"])
    result = json.loads(path.read_text(encoding="utf-8"))
    st.warning(result["confidence"])
    columns = st.columns(3)
    columns[0].metric("Probable new inundation", f"{result['probable_flooded_area_ha']:,.0f} ha")
    columns[1].metric("Valid land coverage", f"{result['coverage_fraction']:.1%}")
    columns[2].metric("Event date", "27 Mar 2017")
    st.caption(
        "Observation dates: "
        + result["selection"]["before"]["datetime"][:10]
        + " → "
        + result["selection"]["during"]["datetime"][:10]
        + ". Area is an experimental estimate over common valid coverage, not the total event footprint."
    )
    layer = st.radio("View", ["Before", "During", "Flood footprint"], horizontal=True)
    names = {"Before": "baseline-water", "During": "during", "Flood footprint": "flood"}
    descriptions = {
        "Before": "Historical water baseline · persistent and seasonal water in 2013–2015",
        "During": "Surface water during ongoing/remaining inundation · April 4",
        "Flood footprint": "Experimental new inundation on historically non-water land · ocean excluded",
    }
    st.write(descriptions[layer])
    m = folium.Map(
        location=[aoi.geometry.centroid.y, aoi.geometry.centroid.x],
        zoom_start=10,
        tiles="OpenStreetMap",
    )
    folium.GeoJson(
        aoi.geojson(),
        name="Area of interest",
        style_function=lambda _: {"color": "#334155", "weight": 2, "fillOpacity": 0},
    ).add_to(m)
    if layer == "Flood footprint":
        folium.raster_layers.ImageOverlay(
            str(path.parent / "baseline-water.png"),
            result["bounds"],
            name="Historical water",
            opacity=0.7,
        ).add_to(m)
    folium.raster_layers.ImageOverlay(
        str(path.parent / f"{names[layer]}.png"), result["bounds"], name=layer, opacity=0.9
    ).add_to(m)
    for label, coords in [
        ("Piura", [-5.1945, -80.6328]),
        ("Catacaos", [-5.2667, -80.675]),
        ("La Unión", [-5.403, -80.742]),
    ]:
        folium.Marker(
            coords,
            tooltip=label,
            icon=folium.DivIcon(
                html=f'<b style="color:#183142;background:white;padding:2px">{label}</b>'
            ),
        ).add_to(m)
    m.fit_bounds(result["bounds"])
    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(
        m, height=590, use_container_width=True, key="event_result_" + layer, returned_objects=[]
    )
    st.caption(
        "Blue: historical water. Cyan: April 4 water. Orange-red: probable new inundation on land. Transparent areas can be dry, excluded or unknown. Basemap requires internet."
    )
    st.caption(
        "Historical baseline → January 10 optical → March 11 radar → March 27 escalation → March 31 optical → April 4 continuing inundation. No peak footprint is established."
    )
    impact_package = show_impact(cfg.root, path.parent, result)
    st.download_button(
        "Download complete analysis",
        (impact_package or (path.parent / "analysis.zip")).read_bytes(),
        file_name=f"floodlab-{result['analysis_id']}.zip",
        mime="application/zip",
        type="primary",
    )
    with st.expander("Evidence / timeline"):
        st.write(result["optical"]["status"])
        if "usable_pair_ha" in result["optical"]:
            st.caption(
                f"Optical comparison covers {result['optical']['usable_pair_ha']:,.0f} ha of land. Optical and radar observations are four days apart; disagreement can reflect changing water as well as classification error."
            )
        evidence_map = folium.Map(tiles="OpenStreetMap")
        for code in [1, 2, 3, 4]:
            folium.raster_layers.ImageOverlay(
                str(path.parent / f"evidence-{code}.png"),
                result["bounds"],
                name=result["evidence_classes"][str(code)],
            ).add_to(evidence_map)
        for name, label in [
            ("before", "March 11 observed water"),
            ("s2-water", "March 31 optical water"),
            ("baseline-uncertain", "Uncertain baseline"),
        ]:
            folium.raster_layers.ImageOverlay(
                str(path.parent / f"{name}.png"), result["bounds"], name=label, show=False
            ).add_to(evidence_map)
        if (path.parent / "rivers.geojson").exists():
            folium.GeoJson(
                str(path.parent / "rivers.geojson"),
                name="Mapped rivers",
                show=False,
                style_function=lambda _: {"color": "#2466a3", "weight": 1},
            ).add_to(evidence_map)
        for station in result["gauges"].get("stations", []):
            folium.Marker(
                [station["latitude"], station["longitude"]],
                tooltip=station["name"] + " · discovery only, no hydrograph",
            ).add_to(evidence_map)
        evidence_map.fit_bounds(result["bounds"])
        folium.LayerControl(collapsed=False).add_to(evidence_map)
        if st.checkbox("Show evidence map"):
            st_folium(
                evidence_map,
                height=420,
                use_container_width=True,
                key="evidence_map",
                returned_objects=[],
            )
        st.caption(
            "Green: supporting observations; amber: radar only / optical missing; red: disagreement; purple: optical only. These are evidence states, not probabilities."
        )
        st.dataframe(result["timeline"], hide_index=True)
        st.write("Gauge observations: " + result["gauges"]["status"].replace("_", " "))
    with st.expander("Independent evidence comparison"):
        comp = result["comparison"]
        st.write(comp["status"])
        if "areas_ha" in comp:
            st.dataframe(
                [
                    {"Category": k.replace("_", " ").title(), "Area (ha)": v}
                    for k, v in comp["areas_ha"].items()
                ],
                hide_index=True,
            )
            st.write(comp["limitations"])
            reference_map = folium.Map(tiles="OpenStreetMap")
            for name in ["agreement", "possible_omission", "possible_commission"]:
                folium.raster_layers.ImageOverlay(
                    str(path.parent / f"{name}.png"),
                    result["bounds"],
                    name=name.replace("_", " ").title(),
                ).add_to(reference_map)
            reference_map.fit_bounds(result["bounds"])
            folium.LayerControl(collapsed=False).add_to(reference_map)
            if st.checkbox("Show comparison map"):
                st_folium(
                    reference_map,
                    height=380,
                    use_container_width=True,
                    key="reference_comparison",
                    returned_objects=[],
                )
            st.caption(
                "Green: agreement; purple: possible omission; amber: possible commission. These are map differences, not confirmed errors or accuracy metrics."
            )
    with st.expander("Advanced / Scientific Details"):
        st.write(event["interpretation"])
        for evidence in event["evidence"]:
            st.markdown(f"[{evidence['title']}]({evidence['url']}) — {evidence['finding']}")
        st.json(result)
        st.download_button(
            "Download provenance", path.read_bytes(), file_name="floodlab-event-provenance.json"
        )
        st.download_button(
            "Download flood polygons",
            (path.parent / "flood.geojson").read_bytes(),
            file_name="probable-flood.geojson",
        )
        st.download_button(
            "Download flood raster",
            (path.parent / "flood.tif").read_bytes(),
            file_name="probable-flood.tif",
        )
