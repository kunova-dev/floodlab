"""Optional analytical grid, downstream of the primary native hazard footprint."""

import json

import folium
import streamlit as st
from streamlit_folium import st_folium

from floodlab.impact.buildings import OvertureBuildingProvider
from floodlab.impact.package import build_impact_package


def show_saved_impact(root):
    st.title("Impact")
    st.write("Use a completed footprint without rerunning satellite processing.")
    reports = sorted(
        (
            path
            for path in (root / "outputs/analyses").glob("*/provenance.json")
            if "probable_flooded_area_ha" in json.loads(path.read_text(encoding="utf-8"))
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not reports:
        st.info("Complete a Flood Event analysis first.")
        return
    path = st.selectbox("Completed analysis", reports, format_func=lambda p: p.parent.name)
    report = json.loads(path.read_text(encoding="utf-8"))
    st.caption(
        f"Source: {report['analysis_id']} · {report['status']} · native footprint {report['probable_flooded_area_ha']:,.2f} ha"
    )
    package = show_impact(root, path.parent, report)
    if package:
        st.download_button(
            "Download complete analysis",
            package.read_bytes(),
            file_name=f"floodlab-impact-{package.parent.name}.zip",
            mime="application/zip",
        )


def show_impact(root, source, report):
    """Return a derived complete package only after explicit local aggregation."""
    key = str(source)
    with st.expander("Impact Grid"):
        st.caption(
            "Optional impact aggregation. The native footprint remains the scientific product."
        )
        resolution = st.selectbox(
            "Grid detail (H3 resolution)", [6, 7, 8], index=1, key="impact_resolution"
        )
        use_buildings = st.checkbox("Add mapped-building context (Overture Maps)", value=True)
        if st.button("Build Impact Grid"):
            try:
                with st.spinner("Aggregating the completed footprint…"):
                    provider = (
                        OvertureBuildingProvider(root / "data/cache") if use_buildings else None
                    )
                    folder = build_impact_package(
                        source,
                        root / "outputs/impacts",
                        hazard_type="flood",
                        event_date=report["event"]["event_date"],
                        resolution=resolution,
                        building_provider=provider,
                    )
                st.session_state["impact_product"] = {
                    "source": key,
                    "resolution": resolution,
                    "folder": str(folder),
                }
            except (OSError, ValueError, KeyError) as exc:
                st.error(f"Impact aggregation unavailable: {exc}")
        saved = st.session_state.get("impact_product")
        if not saved or saved["source"] != key or saved["resolution"] != resolution:
            return None
        from pathlib import Path

        folder = Path(saved["folder"])
        grid = json.loads((folder / "grid.geojson").read_text(encoding="utf-8"))
        provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
        st.write(
            f"{provenance['cell_count']:,} cells · {provenance['totals']['hazard_area_m2'] / 10000:,.2f} ha of footprint on land"
        )
        st.caption(
            "Percent affected uses only the terrestrial portion inside the AOI. Grey means no terrestrial denominator. Equal-area geometry measurements may differ slightly from native raster hectares."
        )
        building_info = provenance.get("buildings")
        if building_info and building_info.get("status") == "retrieved":
            st.subheader("Built Environment")
            cols = st.columns(4)
            cols[0].metric("Mapped buildings within AOI", building_info["buildings_in_aoi"])
            cols[1].metric(
                "Buildings intersecting observed inundation",
                building_info["buildings_intersecting_hazard"],
            )
            cols[2].metric(
                "Building footprint intersecting inundation",
                f"{building_info['building_hazard_intersection_m2'] / 10000:,.2f} ha",
            )
            cols[3].metric("Buildings with height data", f"{building_info['pct_with_height']:.1f}%")
            st.caption(
                "Modern mapped buildings provide contextual built-environment information only. They must not be interpreted as buildings present in 2017 or as confirmed damage."
            )
        elif building_info:
            st.info(
                "Mapped-building enrichment is unavailable for this AOI; this is not a count of zero buildings. The flood and H3 products are unchanged."
            )
            with st.expander("Advanced / Scientific Details"):
                st.json(building_info)
        if st.checkbox("Show Impact Grid map"):
            m = folium.Map(tiles="OpenStreetMap")

            mode = st.selectbox(
                "H3 map mode",
                ["Hazard coverage", "Building count", "Building footprint intersection"],
            )

            def style(feature):
                props = feature["properties"]
                percent = props["terrestrial_affected_pct"]
                if mode == "Building count":
                    value = props.get("building_count")
                    color = "#94a3b8" if value is None else "#fff7bc" if value == 0 else "#fe9929"
                    return {
                        "color": "#64748b",
                        "weight": 0.5,
                        "fillColor": color,
                        "fillOpacity": 0.5,
                    }
                if mode == "Building footprint intersection":
                    value = props.get("building_hazard_intersection_m2")
                    color = "#94a3b8" if value is None else "#fff7bc" if value == 0 else "#d95f0e"
                    return {
                        "color": "#64748b",
                        "weight": 0.5,
                        "fillColor": color,
                        "fillOpacity": 0.5,
                    }
                color = (
                    "#94a3b8"
                    if percent is None
                    else "#fff7bc"
                    if percent == 0
                    else "#fec44f"
                    if percent < 1
                    else "#fe9929"
                    if percent < 10
                    else "#d95f0e"
                    if percent < 25
                    else "#993404"
                )
                return {"color": "#64748b", "weight": 0.5, "fillColor": color, "fillOpacity": 0.5}

            folium.GeoJson(
                grid,
                name="Impact Grid",
                style_function=style,
                popup=folium.GeoJsonPopup(
                    fields=[
                        "h3_index",
                        "hazard_type",
                        "hazard_area_ha",
                        "terrestrial_area_ha",
                        "terrestrial_affected_pct",
                        "event_date",
                        "building_count",
                        "building_hazard_intersection_m2",
                    ],
                    aliases=[
                        "H3 cell",
                        "Hazard",
                        "Hazard area (ha)",
                        "Terrestrial area in AOI (ha)",
                        "Affected (%)",
                        "Event date",
                        "Unique allocated buildings",
                        "Building intersection (m²)",
                    ],
                    localize=True,
                ),
            ).add_to(m)
            for filename, name, color in [
                ("buildings_aoi.geojson", "Mapped buildings", "#2563eb"),
                (
                    "buildings_intersecting_hazard.geojson",
                    "Buildings intersecting hazard",
                    "#7c3aed",
                ),
            ]:
                candidate = folder / filename
                if candidate.exists():
                    folium.GeoJson(
                        str(candidate),
                        name=name,
                        style_function=lambda _, shade=color: {
                            "color": shade,
                            "weight": 1,
                            "fillOpacity": 0.15,
                        },
                    ).add_to(m)
            folium.GeoJson(
                str(source / "flood.geojson"),
                name="Native footprint",
                style_function=lambda _: {
                    "color": "#f44d28",
                    "weight": 1,
                    "fillColor": "#f44d28",
                    "fillOpacity": 0.8,
                },
            ).add_to(m)
            m.fit_bounds(report["bounds"])
            folium.LayerControl().add_to(m)
            st_folium(
                m,
                height=480,
                use_container_width=True,
                key="impact_map_" + provenance["analysis_id"],
                returned_objects=[],
            )
            st.caption(
                "Grey: no land · pale: 0% · yellow: <1% · orange: 1–10% · dark orange: 10–25% · brown: ≥25%. Orange-red polygons: native footprint."
            )
        st.download_button(
            "Download H3 GeoJSON",
            (folder / "grid.geojson").read_bytes(),
            file_name="impact-grid.geojson",
        )
        return folder / "analysis.zip"
