"""Durable local pair plans, batch-job state, sanitized provenance and raster QC."""

import json
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout

from floodlab import __version__

from .aoi import AOI
from .catalogue import Acquisition
from .diagnostics import inspect_job
from .integrity import sha256_file
from .openeo_backend import BackendSettings, OpenEOBackend, process_graph
from .pairs import assess_pair
from .raster import align_to_reference, pair_qc, raster_qc


def write_json(path: Path, value: dict) -> None:
    """Atomic replacement prevents the UI reading partially written worker state."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def runtime_root(root: Path, settings: BackendSettings) -> Path:
    path = (root / settings.cache).resolve()
    if not any(
        path.is_relative_to((root / folder).resolve()) for folder in ("data/cache", "outputs")
    ):
        raise ValueError("Processing cache must be inside ignored data/cache or outputs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_plan(
    root: Path, earlier: Acquisition, later: Acquisition, aoi: AOI, settings: BackendSettings
) -> Path:
    assessment = assess_pair(earlier, later, aoi, tuple(settings.bands), settings.minimum_coverage)
    if not assessment.compatible:
        raise ValueError("; ".join(assessment.reasons))
    folder = runtime_root(root, settings) / str(uuid4())
    folder.mkdir()
    plan = {
        "schema_version": 1,
        "floodlab_version": __version__,
        "created_utc": datetime.now(UTC).isoformat(),
        "aoi": aoi.geojson(),
        "earlier": earlier.to_dict(),
        "later": later.to_dict(),
        "configuration": settings.to_dict(),
        "pair_assessment": assessment.to_dict(),
        "alignment_policy": "Explicit bilinear resampling to requested UTM grid; if returned grids differ, align later to earlier and retain native rasters.",
        "scientific_status": "DRAFT; no validated flood extent",
    }
    write_json(folder / "plan.json", plan)
    write_json(
        folder / "state.json",
        {
            "state": "NOT AUTHENTICATED",
            "jobs": {},
            "message": "Run the displayed terminal command and complete CDSE device login.",
        },
    )
    return folder / "plan.json"


def load_plan(path: Path, root: Path) -> tuple[dict, BackendSettings]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    settings = BackendSettings(**plan["configuration"])
    if not path.resolve().is_relative_to(runtime_root(root, settings)):
        raise ValueError("Plan must reside in the configured ignored runtime directory")
    assessment = assess_pair(
        Acquisition(**plan["earlier"]),
        Acquisition(**plan["later"]),
        AOI.from_geojson(plan["aoi"]),
        tuple(settings.bands),
        settings.minimum_coverage,
    )
    if not assessment.compatible:
        raise ValueError("Plan contains incompatible observations")
    return plan, settings


def replace_with_retry(source: Path, target: Path, sleep=time.sleep) -> None:
    """Allow transient Windows file locks to clear without repeating a transfer."""
    for attempt in range(5):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            sleep(2**attempt)


def download_raster(job, key: str, target: Path, sleep=time.sleep) -> str:
    """Retry transfers and preserve verified staging files across promotion failures."""
    receipt_path = target.with_suffix(".receipt.json")
    temporary = target.with_suffix(".download")
    pending_path = target.with_suffix(".pending.json")

    def matching(receipt):
        return receipt.get("job_id") == job.job_id and (
            receipt.get("asset_key") == key
            or (
                receipt.get("asset_key") is None
                and receipt.get("recovery") == "local-full-raster-read"
            )
        )

    def promote(checksum):
        replace_with_retry(temporary, target, sleep)
        write_json(receipt_path, {"job_id": job.job_id, "asset_key": key, "sha256": checksum})
        return checksum

    if target.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if matching(receipt) and sha256_file(target) == receipt.get("sha256"):
            return receipt["sha256"]
    if pending_path.exists():
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        if matching(pending):
            # Also recover a successful rename followed by a failed receipt write.
            if target.exists() and sha256_file(target) == pending.get("sha256"):
                write_json(
                    receipt_path,
                    {"job_id": job.job_id, "asset_key": key, "sha256": pending["sha256"]},
                )
                return pending["sha256"]
            if temporary.exists() and sha256_file(temporary) == pending.get("sha256"):
                return promote(pending["sha256"])
    for attempt in range(3):
        temporary.unlink(missing_ok=True)
        try:
            job.get_results().download_file(target=temporary, key=key)
        except (ChunkedEncodingError, ConnectionError, Timeout):
            if attempt == 2:
                raise
            sleep(2 ** (attempt + 1))
            continue
        raster_qc(temporary)  # Read every block before recording a completed transfer.
        checksum = sha256_file(temporary)
        write_json(pending_path, {"job_id": job.job_id, "asset_key": key, "sha256": checksum})
        return promote(checksum)
    raise AssertionError("Unreachable download state")


def execute_plan(
    path: Path,
    root: Path,
    backend: OpenEOBackend | None = None,
    sleep=time.sleep,
    clock=time.monotonic,
) -> dict:
    """Authenticate interactively, submit/resume two jobs, download, QC, and retain provenance.

    Errors are intentionally summarized without raw HTTP messages, tokens or signed URLs.
    Remote jobs are not silently canceled or resubmitted after a local timeout.
    """
    plan, settings = load_plan(path, root)
    folder = path.resolve().parent
    lock = folder / "worker.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(datetime.now(UTC)))
    state_path = folder / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))

    def update(status, message):
        state.update(state=status, message=message, updated_utc=datetime.now(UTC).isoformat())
        write_json(state_path, state)

    try:
        if state["state"] in ("QC PASS", "QC WARNING"):
            return state
        backend = backend or OpenEOBackend(settings)
        state["phase"] = "capability discovery"
        snapshot = backend.capabilities()
        write_json(folder / "capabilities.json", snapshot)
        aoi = AOI.from_geojson(plan["aoi"])
        graphs, requests = {}, {}
        for role in ("earlier", "later"):
            graphs[role], requests[role] = process_graph(
                Acquisition(**plan[role]), aoi, settings, snapshot
            )
        write_json(folder / "graphs.json", graphs)
        update(
            "NOT AUTHENTICATED",
            "Complete CDSE device login in your browser; no password is entered in FloodLab.",
        )
        state["phase"] = "authentication"
        if not backend.authenticated:
            backend.authenticate()
        update(
            "READY", "Authentication succeeded in memory; submitting/resuming reviewed pair jobs."
        )
        deadline = clock() + settings.max_wait_seconds
        results = {}
        for role in ("earlier", "later"):
            state["phase"] = f"{role} processing"
            if role in state["jobs"]:
                job = backend.connection.job(state["jobs"][role])
            else:
                job = backend.submit(
                    graphs[role], f"FloodLab {__version__} {role} {plan[role]['id']}"
                )
                state["jobs"][role] = job.job_id
                update("READY", f"{role} job created; ID saved before start.")
            status = job.status()
            if status == "created":
                job.start()
            update(
                "PROCESSING",
                f"{role} job {job.job_id}; remote processing may consume CDSE credits.",
            )
            while True:
                status = job.status()
                if status == "finished":
                    break
                if status in ("error", "canceled"):
                    diagnostic = inspect_job(job)
                    write_json(folder / "job-errors.json", {role: diagnostic})
                    state["diagnostics"] = "job-errors.json"
                    detail = (
                        diagnostic["errors"][0]["message"]
                        if diagnostic["errors"]
                        else diagnostic.get("note", "Error logs unavailable")
                    )
                    update(
                        "FAILED",
                        f"{role} job {job.job_id} is {status}. {detail} "
                        "Rerunning this plan reuses this terminal job; it does not retry processing. "
                        "Use --diagnose to inspect saved jobs before preparing a corrected plan.",
                    )
                    return state
                if clock() >= deadline:
                    update(
                        "PROCESSING",
                        "Local wait limit reached; remote jobs may continue. Rerun the same command to authenticate and resume without resubmitting saved jobs.",
                    )
                    return state
                sleep(settings.poll_seconds)
            state["phase"] = f"{role} download"
            update(
                "PROCESSING", f"{role} remote job finished; downloading or verifying cached raster."
            )
            result = job.get_results()
            metadata = result.get_metadata()
            assets = metadata.get("assets", {})
            keys = [
                key
                for key, asset in assets.items()
                if "tiff" in asset.get("type", "").lower()
                or key.lower().endswith((".tif", ".tiff"))
            ]
            if len(keys) != 1:
                raise ValueError(
                    "Expected exactly one GeoTIFF per acquisition; inspect results rather than silently mosaic/select"
                )
            target = folder / f"{role}.tif"
            # Only use our fixed target name; never trust a backend asset path as a local filename.
            checksum = download_raster(job, keys[0], target, sleep=sleep)
            properties = metadata.get("properties", {})
            results[role] = {
                "job_id": job.job_id,
                "raster": target.name,
                "sha256": checksum,
                "backend_source_ids": properties.get("source_product_ids", []),
                "backend_temporal_extent": {
                    k: properties.get(k) for k in ("datetime", "start_datetime", "end_datetime")
                },
                "expected_catalogue_id": plan[role]["id"],
                "source_identity_verified": False,
            }
        state["phase"] = "raster QC"
        update(
            "PROCESSED", "Both real job results downloaded; computing native and aligned raster QC."
        )
        first, second = folder / "earlier.tif", folder / "later.tif"
        native = pair_qc(first, second, settings.minimum_valid_fraction)
        if any(native[role]["count"] != len(settings.bands) for role in ("earlier", "later")):
            raise ValueError(
                "Downloaded raster band count differs from the requested polarization count"
            )
        alignment = None
        if not native["grid_compatible"]:
            aligned = folder / "later-aligned.tif"
            # Never overwrite a prior alignment on resume; QC its existing file below.
            if not aligned.exists():
                alignment = align_to_reference(first, second, aligned)
            else:
                alignment = {
                    "method": "bilinear",
                    "output": aligned.name,
                    "warning": "Reused existing alignment from this job directory",
                }
            second = aligned
        final = pair_qc(first, second, settings.minimum_valid_fraction)
        warnings = list(dict.fromkeys(w for req in requests.values() for w in req["warnings"]))
        warnings.extend(final["warnings"])
        warnings.append(
            "Independent flood-date interpretation and scientific accuracy remain unvalidated."
        )
        # Even good numeric coverage cannot verify missing backend source-product lineage.
        overall = "QC WARNING" if warnings else final["status"]
        provenance = {
            "floodlab_version": __version__,
            "processed_utc": datetime.now(UTC).isoformat(),
            "backend": snapshot["endpoint"],
            "backend_version": snapshot["capabilities"].get("backend_version"),
            "capabilities_file": "capabilities.json",
            "plan_file": "plan.json",
            "process_graph_file": "graphs.json",
            "aoi": plan["aoi"],
            "requested_observations": {r: plan[r] for r in ("earlier", "later")},
            "configuration": settings.to_dict(),
            "retry_of": plan.get("retry_of"),
            "processing_requests": requests,
            "outputs": results,
            "native_qc": native,
            "alignment": alignment,
            "comparison_qc": final,
            "display_rasters": [first.name, second.name],
            "warnings": warnings,
            "status": overall,
            "scientific_status": "DRAFT; backscatter only, not a validated flood extent",
        }
        write_json(folder / "provenance.json", provenance)
        state["provenance"] = "provenance.json"
        update(
            overall,
            "Processing completed. Review QC, source-identity warnings and scientific assumptions.",
        )
        return state
    except Exception as exc:  # noqa: BLE001 -- contain remote errors without logging credentials
        update(
            "FAILED",
            f"{type(exc).__name__} during {state.get('phase', 'processing')}"
            + (
                f" (errno={exc.errno}, winerror={getattr(exc, 'winerror', None)})"
                if isinstance(exc, OSError)
                else ""
            )
            + ". "
            "Job IDs are retained. Rerun the same plan to reuse saved jobs and retry downloads; "
            "completed remote jobs are not restarted. Raw remote errors are deliberately not logged.",
        )
        return state
    finally:
        lock.unlink(missing_ok=True)


def diagnose_plan(path: Path, root: Path, backend: OpenEOBackend | None = None) -> dict:
    """Authenticate for read-only access to saved job status/logs; do not change run state."""
    _, settings = load_plan(path, root)
    state = json.loads((path.parent / "state.json").read_text(encoding="utf-8"))
    if not state.get("jobs"):
        return {
            "message": "No remote job IDs saved; there is no remote job to diagnose.",
            "jobs": {},
        }
    backend = backend or OpenEOBackend(settings)
    if not backend.authenticated:
        backend.authenticate()
    report = {"checked_utc": datetime.now(UTC).isoformat(), "mode": "read-only", "jobs": {}}
    for role, job_id in state["jobs"].items():
        report["jobs"][role] = inspect_job(backend.connection.job(job_id))
    write_json(path.parent / "job-errors.json", report)
    return report


def create_resource_retry(path: Path, root: Path, job_options: dict) -> Path:
    """Create an independent resource-only retry; preserve original plan, jobs and evidence."""
    plan, settings = load_plan(path, root)
    state = json.loads((path.parent / "state.json").read_text(encoding="utf-8"))
    if state.get("state") != "FAILED":
        raise ValueError("Prepare a resource retry only for a failed plan")
    if (path.parent / "worker.lock").exists():
        raise ValueError("The original plan still has a worker lock")
    retry_settings = replace(settings, job_options=dict(job_options))
    retry = create_plan(
        root,
        Acquisition(**plan["earlier"]),
        Acquisition(**plan["later"]),
        AOI.from_geojson(plan["aoi"]),
        retry_settings,
    )
    retry_plan = json.loads(retry.read_text(encoding="utf-8"))
    retry_plan["retry_of"] = {
        "plan_id": path.parent.name,
        "jobs": state.get("jobs", {}),
        "reason": "Resource-only retry after diagnosed Orfeo memory allocation failure",
        "previous_job_options": settings.job_options,
    }
    write_json(retry, retry_plan)
    return retry
