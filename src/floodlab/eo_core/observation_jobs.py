"""Durable single-observation plans for temporal reconstruction without duplicate jobs."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from floodlab import __version__

from .aoi import AOI
from .catalogue import Acquisition
from .openeo_backend import BackendSettings, OpenEOBackend, process_graph
from .pair_jobs import download_raster, runtime_root, write_json
from .raster import raster_qc


def create_plan(
    root: Path, observations: list[Acquisition], aoi: AOI, settings: BackendSettings
) -> Path:
    """Store a reviewed, immutable plan. It does not authenticate or submit work."""
    if not observations or len({item.id for item in observations}) != len(observations):
        raise ValueError("Temporal plan requires unique observations")
    folder = runtime_root(root, settings) / str(uuid4())
    folder.mkdir()
    plan = {
        "schema_version": 1,
        "kind": "observation-series",
        "floodlab_version": __version__,
        "created_utc": datetime.now(UTC).isoformat(),
        "aoi": aoi.geojson(),
        "observations": [item.to_dict() for item in observations],
        "configuration": settings.to_dict(),
        "scientific_status": "DRAFT; processing produces backscatter observations, not a validated flood extent.",
    }
    write_json(folder / "plan.json", plan)
    write_json(
        folder / "state.json",
        {
            "state": "NOT AUTHENTICATED",
            "jobs": {},
            "message": "Run the displayed command and complete CDSE device login.",
        },
    )
    return folder / "plan.json"


def load_plan(path: Path, root: Path) -> tuple[dict, BackendSettings]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("kind") != "observation-series":
        raise ValueError("Expected an observation-series plan")
    settings = BackendSettings(**plan["configuration"])
    if not path.resolve().is_relative_to(runtime_root(root, settings)):
        raise ValueError("Plan must reside inside the ignored runtime directory")
    if not plan.get("observations"):
        raise ValueError("Observation plan is empty")
    return plan, settings


def execute_plan(
    path: Path, root: Path, backend=None, sleep=time.sleep, clock=time.monotonic
) -> dict:
    """Authenticate once, submit/resume only saved observation jobs, then download/QC each raster."""
    plan, settings = load_plan(path, root)
    folder, state_path = path.parent, path.parent / "state.json"
    lock = folder / "worker.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(datetime.now(UTC).isoformat())
    state = json.loads(state_path.read_text(encoding="utf-8"))

    def update(status, message):
        state.update(state=status, message=message, updated_utc=datetime.now(UTC).isoformat())
        write_json(state_path, state)

    try:
        if state["state"] in ("QC PASS", "QC WARNING"):
            return state
        backend = backend or OpenEOBackend(settings)
        snapshot = backend.capabilities()
        write_json(folder / "capabilities.json", snapshot)
        aoi = AOI.from_geojson(plan["aoi"])
        graphs, requests = {}, {}
        for item in plan["observations"]:
            graphs[item["id"]], requests[item["id"]] = process_graph(
                Acquisition(**item), aoi, settings, snapshot
            )
        write_json(folder / "graphs.json", graphs)
        update(
            "NOT AUTHENTICATED",
            "Complete CDSE device login in your browser; no password is entered in FloodLab.",
        )
        if not backend.authenticated:
            backend.authenticate()
        update(
            "READY",
            "Authentication succeeded in memory; submitting/resuming reviewed observation jobs.",
        )
        deadline, outputs = clock() + settings.max_wait_seconds, {}
        for index, item in enumerate(plan["observations"], start=1):
            product_id = item["id"]
            if product_id in state["jobs"]:
                job = backend.connection.job(state["jobs"][product_id])
            else:
                job = backend.submit(
                    graphs[product_id], f"FloodLab {__version__} temporal {product_id}"
                )
                state["jobs"][product_id] = job.job_id
                update(
                    "READY",
                    f"Observation {index}/{len(plan['observations'])} job ID saved before start.",
                )
            if job.status() == "created":
                job.start()
            update(
                "PROCESSING",
                f"Observation {index}/{len(plan['observations'])} is processing; CDSE credits may be consumed.",
            )
            while job.status() not in ("finished", "error", "canceled"):
                if clock() >= deadline:
                    update(
                        "PROCESSING",
                        "Local wait limit reached; rerun this same plan to resume saved jobs without resubmission.",
                    )
                    return state
                sleep(settings.poll_seconds)
            if job.status() != "finished":
                update(
                    "FAILED",
                    f"Observation {product_id} job {job.job_id} is {job.status()}. Rerunning reuses this terminal job; it does not retry processing.",
                )
                return state
            metadata = job.get_results().get_metadata()
            keys = [
                key
                for key, asset in metadata.get("assets", {}).items()
                if "tiff" in asset.get("type", "").lower()
                or key.lower().endswith((".tif", ".tiff"))
            ]
            if len(keys) != 1:
                raise ValueError("Expected exactly one GeoTIFF per observation")
            target = folder / "observations" / f"{index:02d}.tif"
            target.parent.mkdir(exist_ok=True)
            checksum = download_raster(job, keys[0], target, sleep=sleep)
            outputs[product_id] = {
                "job_id": job.job_id,
                "raster": str(target.relative_to(folder)),
                "sha256": checksum,
                "raster_qc": raster_qc(target),
                "expected_catalogue_id": product_id,
                "source_identity_verified": False,
            }
        warnings = [
            "Exact input product identity is not pinned by openEO load_collection; inspect backend lineage.",
            "These analysis-ready backscatter rasters do not validate a flood footprint.",
        ]
        write_json(
            folder / "provenance.json",
            {
                "processed_utc": datetime.now(UTC).isoformat(),
                "backend": snapshot["endpoint"],
                "plan_file": "plan.json",
                "process_graph_file": "graphs.json",
                "aoi": plan["aoi"],
                "configuration": settings.to_dict(),
                "outputs": outputs,
                "processing_requests": requests,
                "warnings": warnings,
                "status": "QC WARNING",
                "scientific_status": "DRAFT; backscatter observations only, not a validated flood extent.",
            },
        )
        state["provenance"] = "provenance.json"
        update(
            "QC WARNING",
            "All planned observations completed and passed raster readability QC. Review provenance and scientific QC.",
        )
        return state
    except Exception as exc:  # noqa: BLE001
        update(
            "FAILED",
            f"{type(exc).__name__} during processing. Job IDs are retained; raw remote errors are deliberately not logged.",
        )
        return state
    finally:
        lock.unlink(missing_ok=True)
