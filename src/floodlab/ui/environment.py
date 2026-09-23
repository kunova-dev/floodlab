"""Restrained read-only presentation of DRAFT environmental context."""

import json

import streamlit as st


def show_environment_context(root):
    st.title("Environmental Context")
    packages = sorted((root / "outputs/environment").glob("*/provenance.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not packages:
        st.info("No environmental context package is available.")
        return
    package = packages[0].parent
    provenance = json.loads((package / "provenance.json").read_text(encoding="utf-8"))
    summaries = json.loads((package / "summaries.json").read_text(encoding="utf-8"))
    st.caption("DRAFT contextual data. It is not a hazard classification, exposure, impact or causal model.")
    for variable in provenance["variables"]:
        with st.expander(variable["name"], expanded=False):
            st.write(f"Source: {', '.join(asset['dataset'] for asset in variable['upstream_assets'])}")
            st.write(f"Temporal relationship: {variable['temporal_relationship']}")
            st.write(f"Coverage: {variable['coverage_status']}")
            st.write("Limitations: " + " ".join(variable["limitations"]))
    st.subheader("Native-grid summaries")
    st.json(summaries)
    land_cover = provenance["land_cover"]
    st.info(f"Land cover: {land_cover['coverage_status']} — {land_cover['reason']}")
