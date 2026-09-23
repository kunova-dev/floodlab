"""Optional analytical grid, downstream of the primary native hazard footprint."""

import json

import folium
import streamlit as st
from streamlit_folium import st_folium

from floodlab.impact.package import build_impact_package


def show_saved_impact(root):
    st.title("Impact")
    st.write("Use a completed footprint without rerunning satellite processing.")
    reports = sorted(
        (root / "outputs/analyses").glob("*/provenance.json"),
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
            "Optional area aggregation. No buildings, population, exposure or loss estimates. The native footprint remains the scientific product."
        )
        resolution = st.selectbox(
            "Grid detail (H3 resolution)", [6, 7, 8], index=1, key="impact_resolution"
        )
        if st.button("Build Impact Grid"):
            try:
                with st.spinner("Aggregating the completed footprint…"):
                    folder = build_impact_package(
                        source,
                        root / "outputs/impacts",
                        hazard_type="flood",
                        event_date=report["event"]["event_date"],
                        resolution=resolution,
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
        if st.checkbox("Show Impact Grid map"):
            m = folium.Map(tiles="OpenStreetMap")

            def style(feature):
                percent = feature["properties"]["terrestrial_affected_pct"]
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
                    ],
                    aliases=[
                        "H3 cell",
                        "Hazard",
                        "Hazard area (ha)",
                        "Terrestrial area in AOI (ha)",
                        "Affected (%)",
                        "Event date",
                    ],
                    localize=True,
                ),
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
