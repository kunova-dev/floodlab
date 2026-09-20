"""Pair preparation and local worker status, independent of flood classification."""

import json

import streamlit as st

from floodlab.eo_core.aoi import AOI
from floodlab.eo_core.openeo_backend import BackendSettings
from floodlab.eo_core.pair_jobs import create_plan, runtime_root
from floodlab.eo_core.pairs import candidate_pairs
from floodlab.eo_core.raster import preview_pair


def show_pair_processing(cfg, context: dict) -> None:
    st.subheader("Real backscatter processing · v0.2")
    if "openeo" not in cfg.values:
        st.info("Add an [openeo] configuration to enable pair preparation.")
        return
    try:
        settings = BackendSettings(**cfg.values["openeo"])
        aoi = AOI.from_geojson(context["aoi"])
        candidates = candidate_pairs(
            context["acquisitions"],
            aoi,
            bands=tuple(settings.bands),
            minimum_coverage=settings.minimum_coverage,
        )
    except (ValueError, TypeError, KeyError) as exc:
        st.error(f"Pair configuration could not be validated: {exc}")
        return
    if not candidates:
        st.info(
            "No comparable pair: need two ordered observations with matching orbit/direction/mode, requested bands and sufficient common AOI coverage."
        )
        return
    demo = cfg.values.get("pair_demo", {})
    preferred = next(
        (
            i
            for i, (a, b, _) in enumerate(candidates)
            if a.datetime[:10] == demo.get("earlier") and b.datetime[:10] == demo.get("later")
        ),
        0,
    )
    index = st.selectbox(
        "Comparable pair (earlier → later)",
        range(len(candidates)),
        index=preferred,
        format_func=lambda i: (
            f"{candidates[i][0].datetime[:19]} → {candidates[i][1].datetime[:19]} | orbit {candidates[i][0].relative_orbit} {candidates[i][0].orbit}"
        ),
    )
    earlier, later, assessment = candidates[index]
    st.json(assessment.to_dict(), expanded=False)
    st.caption(
        "Earlier is a candidate baseline; later is a candidate event observation. Independent flood-date evidence has not been incorporated."
    )
    st.caption(
        "Technical ranking uses footprint coverage, platform and time gap; it is not evidence of flood timing. Date preferences are configurable demo hypotheses."
    )
    st.write(
        f"Requested: {settings.coefficient}, {settings.elevation_model}, {', '.join(settings.bands)}, {settings.resolution_m} m."
    )
    st.caption(
        "Explicit bilinear resampling is recorded. If downloaded grids differ, the later raster will be aligned to the earlier grid; native outputs are retained. No flood classification is performed."
    )
    if st.button("Prepare openEO pair plan"):
        try:
            path = create_plan(cfg.root, earlier, later, aoi, settings)
            st.session_state.processing_plan = str(path)
        except (ValueError, OSError) as exc:
            st.error(f"Could not prepare plan: {exc}")
    # Recover matching local runs across app restarts; no authentication material lives here.
    matching = []
    for path in runtime_root(cfg.root, settings).glob("*/plan.json"):
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
            if (
                plan["earlier"]["id"] == earlier.id
                and plan["later"]["id"] == later.id
                and AOI.from_geojson(plan["aoi"]).geometry.equals(aoi.geometry)
            ):
                matching.append(path)
        except (OSError, ValueError, KeyError):
            continue
    if not matching:
        st.info(
            "NOT AUTHENTICATED — prepare a plan, then authenticate in the terminal using CDSE device login."
        )
        return

    def saved_state(path):
        try:
            return json.loads((path.parent / "state.json").read_text(encoding="utf-8")).get(
                "state", "UNKNOWN"
            )
        except (OSError, ValueError):
            return "UNKNOWN"

    completed = {"QC PASS", "QC WARNING"}
    matching = sorted(
        matching,
        key=lambda p: (saved_state(p) in completed, p.stat().st_mtime),
        reverse=True,
    )
    selected = st.selectbox(
        "Saved processing plan",
        matching,
        format_func=lambda p: f"{saved_state(p)} | {p.parent.name}",
    )
    if saved_state(selected) in completed:
        st.success(
            "Processing completed. View the saved rasters below; no login or rerun is needed."
        )
    else:
        if any(saved_state(p) in completed for p in matching):
            st.info(
                "Completed results already exist for this pair. Select a QC PASS or QC WARNING plan to view them without processing again."
            )
        st.code(
            f'.\\.venv\\Scripts\\python.exe scripts/process_pair.py --plan "{selected.relative_to(cfg.root)}"',
            language="powershell",
        )
        st.write(
            "To execute this plan, run the command in a local terminal and complete CDSE device login there. Do not enter credentials in FloodLab."
        )
        st.caption(
            "Execution submits/resumes this plan and can consume CDSE credits. Tokens stay in process memory. Failed terminal jobs require diagnosis, not repeated execution."
        )
    with st.expander("Saved plan resource settings"):
        saved_plan = json.loads(selected.read_text(encoding="utf-8"))
        st.json(saved_plan.get("configuration", {}).get("job_options", {}))
        if saved_plan.get("retry_of"):
            st.json(saved_plan["retry_of"])
    st.button("Refresh processing state")
    try:
        state = json.loads((selected.parent / "state.json").read_text(encoding="utf-8"))
        st.metric("Processing state", state["state"])
        st.write(state.get("message", ""))
        if state.get("jobs"):
            st.json({"remote_job_ids": state["jobs"]})
        provenance_path = selected.parent / "provenance.json"
        if provenance_path.exists() and state["state"] in ("QC PASS", "QC WARNING"):
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            files = [selected.parent / name for name in provenance["display_rasters"]]
            if any(not p.resolve().is_relative_to(selected.parent.resolve()) for p in files):
                raise ValueError("Invalid preview path")
            images, limits = preview_pair(*files)
            columns = st.columns(2)
            for column, image, label in zip(
                columns, images, ["Candidate baseline / earlier", "Candidate event / later"]
            ):
                column.image(
                    image,
                    caption=label + f" · {settings.bands[0]} backscatter (first requested band)",
                    use_container_width=True,
                )
            st.caption(
                f"Shared grayscale {limits[0]:.2f} to {limits[1]:.2f} dB; transparent pixels are invalid. Display downsampling only. Not a flood extent."
            )
            st.json(provenance["comparison_qc"])
            with st.expander("Processing provenance and warnings"):
                st.json(provenance)
            st.download_button(
                "Download processing provenance",
                provenance_path.read_text(encoding="utf-8"),
                file_name="provenance.json",
                mime="application/json",
            )
    except (OSError, ValueError, KeyError) as exc:
        st.error(f"Could not inspect this local run: {exc}")
