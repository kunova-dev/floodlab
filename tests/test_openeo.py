"""Deterministic backend and raster tests: no remote credits or authentication."""

import json
import shutil
from dataclasses import replace
from unittest.mock import MagicMock

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

from floodlab.eo_core.aoi import AOI
from floodlab.eo_core.catalogue import Acquisition
from floodlab.eo_core.openeo_backend import (
    BackendSettings,
    OpenEOBackend,
    process_graph,
    validate_capabilities,
)
from floodlab.eo_core.pair_jobs import create_plan, execute_plan, runtime_root
from floodlab.eo_core.pairs import assess_pair, candidate_pairs
from floodlab.eo_core.raster import align_to_reference, pair_qc, preview_pair, raster_qc


@pytest.fixture
def scene():
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [[-80.9, -5.5], [-80.5, -5.5], [-80.5, -5.1], [-80.9, -5.1], [-80.9, -5.5]]
        ],
    }
    aoi = AOI.from_geojson(geometry)
    first = Acquisition(
        "test-before",
        "sentinel-1-grd",
        "2017-03-11T23:43:11.173270Z",
        "sentinel-1b",
        "ascending",
        91,
        ["VV", "VH"],
        "IW",
        {},
        geometry,
    )
    return aoi, first, replace(first, id="test-later", datetime="2017-04-04T23:43:11.844763Z")


@pytest.fixture
def capabilities():
    processes = [
        {"id": p}
        for p in ("load_collection", "resample_spatial", "filter_spatial", "save_result", "eq")
    ]
    processes.append(
        {
            "id": "sar_backscatter",
            "parameters": [
                {"name": "coefficient", "schema": {"enum": ["sigma0-ellipsoid"]}},
                {"name": "elevation_model"},
                {"name": "noise_removal"},
            ],
        }
    )
    return {
        "endpoint": "https://example.org/openeo/1.2/",
        "capabilities": {"api_version": "1.2.0", "backend_version": "test"},
        "collection": {
            "id": "SENTINEL1_GRD",
            "cube:dimensions": {"bands": {"type": "bands", "values": ["VV", "VH"]}},
            "summaries": {
                "sat:orbit_state": ["ascending", "descending"],
                "sar:instrument_mode": ["IW"],
            },
        },
        "dem": {"id": "COPERNICUS_30"},
        "processes": processes,
        "formats": {"GTiff": {}},
        "oidc": {"providers": [{"id": "test"}]},
    }


def write_raster(path, values=None, shift=0):
    values = (
        np.array([[0.01, 0.02], [0.03, 0.04]], dtype="float32")
        if values is None
        else np.asarray(values, dtype="float32")
    )
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype="float32",
        crs="EPSG:32717",
        transform=Affine(20, 0, 500000 + shift, 0, -20, 9400000),
        nodata=-9999,
    ) as dst:
        dst.write(values, 1)
        dst.set_band_description(1, "VV")
    return path


def test_capability_validation(capabilities):
    validate_capabilities(capabilities, BackendSettings())
    capabilities["processes"] = [
        p for p in capabilities["processes"] if p["id"] != "sar_backscatter"
    ]
    with pytest.raises(ValueError, match="lacks required"):
        validate_capabilities(capabilities, BackendSettings())


@pytest.mark.parametrize(
    "field,value",
    [
        ("coefficient", "gamma0-terrain"),
        ("resolution_m", 0),
        ("endpoint", "https://u:p@example.org"),
        ("minimum_valid_fraction", float("nan")),
    ],
)
def test_settings_invalid(field, value):
    with pytest.raises(ValueError):
        BackendSettings(**{field: value})


def test_band_dem_coefficient_rejection(capabilities):
    capabilities["dem"]["id"] = "wrong"
    with pytest.raises(ValueError):
        validate_capabilities(capabilities, BackendSettings())
    capabilities["dem"]["id"] = "COPERNICUS_30"
    capabilities["processes"][-1]["parameters"][0]["schema"]["enum"] = []
    with pytest.raises(ValueError):
        validate_capabilities(capabilities, BackendSettings())


def test_authentication_state_and_submission():
    connection = MagicMock()
    connection.validate_process_graph.return_value = []
    backend = OpenEOBackend(BackendSettings(), connection)
    assert backend.state == "NOT AUTHENTICATED"
    with pytest.raises(PermissionError):
        backend.submit({}, "test")
    backend.authenticate()
    assert backend.state == "READY"
    connection.authenticate_oidc_device.assert_called_once_with(
        store_refresh_token=False, max_poll_time=300
    )
    backend.submit({}, "test")
    connection.create_job.assert_called_once()
    connection.authenticate_oidc_device.side_effect = RuntimeError("private-token-not-to-log")
    with pytest.raises(RuntimeError):
        backend.authenticate()
    assert backend.state == "NOT AUTHENTICATED"


def test_graph_rejected_before_submit():
    connection = MagicMock()
    connection.validate_process_graph.return_value = [{"code": "Unsupported"}]
    backend = OpenEOBackend(BackendSettings(), connection)
    backend.authenticated = True
    with pytest.raises(ValueError):
        backend.submit({}, "test")
    connection.create_job.assert_not_called()


def test_pair_compatibility(scene):
    aoi, a, b = scene
    result = assess_pair(a, b, aoi)
    assert result.compatible and result.coverage["common"] == pytest.approx(1)
    assert "independent" in result.timing
    for bad in [
        replace(b, relative_orbit=40),
        replace(b, orbit="descending"),
        replace(b, instrument_mode=None),
        replace(b, polarizations=["VH"]),
        replace(b, datetime=a.datetime),
    ]:
        assert not assess_pair(a, bad, aoi).compatible
    assert len(candidate_pairs([b, a], aoi)) == 1


def test_pair_coverage_rejection(scene):
    aoi, a, b = scene
    b = replace(b, geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]})
    assert not assess_pair(a, b, aoi).compatible


def test_explicit_graph_and_lineage_warning(scene, capabilities):
    aoi, a, _ = scene
    graph, provenance = process_graph(a, aoi, BackendSettings(), capabilities)
    assert graph["sar"]["arguments"]["coefficient"] == "sigma0-ellipsoid"
    assert graph["sar"]["arguments"]["elevation_model"] == "COPERNICUS_30"
    assert graph["grid"]["arguments"]["projection"] == 32717
    assert graph["grid"]["arguments"]["method"] == "bilinear"
    assert graph["load"]["arguments"]["temporal_extent"] == [
        "2017-03-11T23:43:11Z",
        "2017-03-11T23:43:12Z",
    ]
    assert "sat:relative_orbit" not in graph["load"]["arguments"]["properties"]
    assert any("relative-orbit" in w for w in provenance["warnings"])
    assert sum(node["process_id"] == "sar_backscatter" for node in graph.values()) == 1


def test_qc_and_preview(tmp_path):
    first = write_raster(tmp_path / "first.tif", [[0.01, -9999], [np.nan, 0]])
    second = write_raster(tmp_path / "second.tif")
    qc = raster_qc(first)
    assert qc["bands"][0]["valid_fraction"] == 0.25
    assert qc["bands"][0]["nodata_fraction"] == 0.25
    assert qc["bands"][0]["nonfinite_count"] == 1
    assert qc["bands"][0]["nonpositive_unmasked_count"] == 1
    pair = pair_qc(first, second)
    assert pair["grid_compatible"]
    assert pair["common_valid_fraction"] == 0.25
    assert pair["status"] == "QC WARNING"
    images, limits = preview_pair(first, second)
    assert images[0].shape == (2, 2, 4) and images[0][0, 1, 3] == 0
    assert limits[0] < limits[1]


def test_explicit_grid_alignment(tmp_path):
    first = write_raster(tmp_path / "first.tif")
    second = write_raster(tmp_path / "second.tif", shift=20)
    assert not pair_qc(first, second)["grid_compatible"]
    output = tmp_path / "aligned.tif"
    record = align_to_reference(first, second, output)
    assert record["method"] == "bilinear"
    assert pair_qc(first, output)["grid_compatible"]
    assert pair_qc(first, output)["common_valid_fraction"] == 0.5
    with pytest.raises(ValueError):
        align_to_reference(first, second, output)


def test_all_invalid_qc(tmp_path):
    path = write_raster(tmp_path / "invalid.tif", np.full((2, 2), -9999))
    assert raster_qc(path)["bands"][0]["min"] is None
    assert pair_qc(path, path)["status"] == "QC WARNING"
    with pytest.raises(ValueError):
        preview_pair(path, path)


def mock_backend(capabilities, source):
    backend = MagicMock()
    backend.authenticated = False
    backend.capabilities.return_value = capabilities
    job = MagicMock()
    job.job_id = "synthetic-job"
    job.status.return_value = "finished"
    result = job.get_results.return_value
    result.get_metadata.return_value = {"assets": {"backscatter.tif": {"type": "image/tiff"}}}
    result.download_file.side_effect = lambda target, key: shutil.copyfile(source, target)
    backend.submit.return_value = job
    backend.connection.job.return_value = job
    return backend


def test_execution_and_provenance(tmp_path, scene, capabilities):
    aoi, a, b = scene
    plan = create_plan(tmp_path, a, b, aoi, BackendSettings())
    source = write_raster(tmp_path / "fixture.tif")
    backend = mock_backend(capabilities, source)
    state = execute_plan(plan, tmp_path, backend)
    assert (
        state["state"] == "QC WARNING"
    )  # unverified source lineage, even when numerical QC passes
    provenance = json.loads((plan.parent / "provenance.json").read_text())
    assert provenance["comparison_qc"]["status"] == "QC PASS"
    assert provenance["outputs"]["earlier"]["expected_catalogue_id"] == "test-before"
    assert not provenance["outputs"]["earlier"]["source_identity_verified"]
    assert provenance["configuration"]["coefficient"] == "sigma0-ellipsoid"
    assert len(provenance["outputs"]["earlier"]["sha256"]) == 64
    assert "private-token" not in json.dumps(provenance)
    assert not (plan.parent / "worker.lock").exists()
    execute_plan(plan, tmp_path, backend)
    assert backend.submit.call_count == 2  # completed plans do not submit again


def test_failure_redaction_and_unauthenticated_state(tmp_path, scene, capabilities):
    aoi, a, b = scene
    plan = create_plan(tmp_path, a, b, aoi, BackendSettings())
    assert json.loads((plan.parent / "state.json").read_text())["state"] == "NOT AUTHENTICATED"
    backend = mock_backend(capabilities, write_raster(tmp_path / "fixture.tif"))
    backend.authenticate.side_effect = RuntimeError("private-token-secret")
    state = execute_plan(plan, tmp_path, backend)
    assert state["state"] == "FAILED"
    assert "private-token-secret" not in (plan.parent / "state.json").read_text()
    backend.submit.assert_not_called()


def test_timeout_resume_uses_saved_job(tmp_path, scene, capabilities):
    aoi, a, b = scene
    plan = create_plan(tmp_path, a, b, aoi, BackendSettings(max_wait_seconds=1))
    backend = mock_backend(capabilities, write_raster(tmp_path / "fixture.tif"))
    backend.submit.return_value.status.return_value = "running"
    clock = iter([0, 2]).__next__
    state = execute_plan(plan, tmp_path, backend, clock=clock)
    assert state["state"] == "PROCESSING" and "earlier" in state["jobs"]
    backend.submit.return_value.status.return_value = "finished"
    execute_plan(plan, tmp_path, backend)
    assert backend.submit.call_count == 2  # earlier resumed; only later added


def test_runtime_path_guard(tmp_path):
    with pytest.raises(ValueError):
        runtime_root(tmp_path, BackendSettings(cache="../outside"))


def test_remote_failure_preserves_diagnostic(tmp_path, scene, capabilities):
    aoi, a, b = scene
    plan = create_plan(tmp_path, a, b, aoi, BackendSettings())
    backend = mock_backend(capabilities, write_raster(tmp_path / "fixture.tif"))
    job = backend.submit.return_value
    job.status.return_value = "error"
    job.logs.return_value = [
        {"message": "NoDataAvailable: no scenes matched https://example.org/?token=private"}
    ]
    state = execute_plan(plan, tmp_path, backend)
    assert state["state"] == "FAILED"
    assert "NoDataAvailable" in state["message"]
    assert "private" not in state["message"]
    assert (plan.parent / "job-errors.json").exists()
    assert backend.submit.call_count == 1
    job.start.assert_not_called()


def test_diagnose_never_submits_or_starts(tmp_path, scene, capabilities):
    from floodlab.eo_core.pair_jobs import diagnose_plan, write_json

    aoi, a, b = scene
    plan = create_plan(tmp_path, a, b, aoi, BackendSettings())
    original = {"state": "FAILED", "jobs": {"earlier": "existing-job"}}
    write_json(plan.parent / "state.json", original)
    backend = mock_backend(capabilities, write_raster(tmp_path / "fixture.tif"))
    job = backend.connection.job.return_value
    job.status.return_value = "error"
    job.logs.return_value = [{"message": "Backend reported an error"}]
    report = diagnose_plan(plan, tmp_path, backend)
    assert report["jobs"]["earlier"]["status"] == "error"
    backend.submit.assert_not_called()
    job.start.assert_not_called()
    assert json.loads((plan.parent / "state.json").read_text()) == original


def test_diagnostic_redaction():
    from floodlab.eo_core.diagnostics import redact_message

    text = redact_message(
        'Bearer abcdef password="secret word" access_token=hidden https://example.org/signed?x=y eyJabc.def.ghi'
    )
    for secret in ("abcdef", "secret word", "hidden", "example.org", "eyJabc"):
        assert secret not in text


def test_diagnostic_log_failure_preserves_status():
    from floodlab.eo_core.diagnostics import inspect_job

    job = MagicMock()
    job.job_id = "existing-job"
    job.status.return_value = "error"
    job.logs.side_effect = RuntimeError("sensitive-message")
    report = inspect_job(job)
    assert report["status"] == "error"
    assert report["logs_unavailable"] == "RuntimeError"
    assert "sensitive-message" not in json.dumps(report)


def test_resource_options_reach_job_submission():
    connection = MagicMock()
    connection.validate_process_graph.return_value = []
    options = {
        "python-memory": "8G",
        "executor-memory": "2G",
        "executor-memoryOverhead": "2G",
        "executor-cores": 1,
        "task-cpus": 1,
        "max-executors": 2,
    }
    backend = OpenEOBackend(BackendSettings(job_options=options), connection)
    backend.authenticated = True
    backend.submit({"graph": "test"}, "resource retry")
    assert connection.create_job.call_args.kwargs["job_options"] == options
    assert backend.settings.to_dict()["job_options"] == options


@pytest.mark.parametrize(
    "options",
    [
        {"python-memory": "disable"},
        {"executor-cores": 2, "task-cpus": 1},
        {"max-executors": 0},
        {"soft-errors": 1},
        {"python-memory": 8},
    ],
)
def test_invalid_resource_options(options):
    with pytest.raises(ValueError):
        BackendSettings(job_options=options)


def test_resource_retry_preserves_evidence_and_science(tmp_path, scene, capabilities):
    from floodlab.eo_core.pair_jobs import create_resource_retry, write_json

    aoi, a, b = scene
    original = create_plan(tmp_path, a, b, aoi, BackendSettings())
    state_path = original.parent / "state.json"
    write_json(state_path, {"state": "FAILED", "jobs": {"earlier": "failed-job"}})
    before_plan, before_state = original.read_bytes(), state_path.read_bytes()
    retry = create_resource_retry(original, tmp_path, {"python-memory": "8G", "max-executors": 2})
    assert original.read_bytes() == before_plan and state_path.read_bytes() == before_state
    saved = json.loads(retry.read_text())
    assert saved["retry_of"]["jobs"]["earlier"] == "failed-job"
    assert json.loads((retry.parent / "state.json").read_text())["jobs"] == {}
    new_settings = BackendSettings(**saved["configuration"])
    assert (
        process_graph(a, aoi, new_settings, capabilities)[0]
        == process_graph(a, aoi, BackendSettings(), capabilities)[0]
    )
    assert saved["earlier"] == json.loads(before_plan)["earlier"]
    assert saved["later"] == json.loads(before_plan)["later"]
    assert saved["aoi"] == json.loads(before_plan)["aoi"]


def test_interrupted_download_resume_without_resubmission(tmp_path, scene, capabilities):
    from requests.exceptions import ChunkedEncodingError

    aoi, a, b = scene
    plan = create_plan(tmp_path, a, b, aoi, BackendSettings())
    source = write_raster(tmp_path / "fixture.tif")
    backend = mock_backend(capabilities, source)
    result = backend.submit.return_value.get_results.return_value

    def interrupted(target, key):
        if target.name == "later.download":
            target.write_bytes(b"incomplete")
            raise ChunkedEncodingError("signed-url-secret")
        shutil.copyfile(source, target)

    result.download_file.side_effect = interrupted
    state = execute_plan(plan, tmp_path, backend, sleep=lambda _: None)
    assert state["state"] == "FAILED"
    assert "later download" in state["message"]
    assert "signed-url-secret" not in state["message"]
    assert result.download_file.call_count == 4
    assert not (plan.parent / "later.tif").exists()
    assert (plan.parent / "earlier.receipt.json").exists()
    result.download_file.reset_mock()
    result.download_file.side_effect = lambda target, key: shutil.copyfile(source, target)
    state = execute_plan(plan, tmp_path, backend, sleep=lambda _: None)
    assert state["state"] == "QC WARNING"
    assert backend.submit.call_count == 2
    backend.connection.job.return_value.start.assert_not_called()
    result.download_file.assert_called_once()
    assert result.download_file.call_args.kwargs["target"].name == "later.download"


def test_download_retry_replaces_partial_and_checks_cache(tmp_path):
    from requests.exceptions import ChunkedEncodingError

    from floodlab.eo_core.pair_jobs import download_raster

    source = write_raster(tmp_path / "fixture.tif")
    target = tmp_path / "earlier.tif"
    job = MagicMock()
    job.job_id = "finished-job"
    download = job.get_results.return_value.download_file
    attempts = []

    def transfer(target, key):
        assert not target.exists()
        attempts.append(key)
        if len(attempts) == 1:
            target.write_bytes(b"partial")
            raise ChunkedEncodingError("private")
        shutil.copyfile(source, target)

    download.side_effect = transfer
    download_raster(job, "asset.tif", target, sleep=lambda _: None)
    assert target.read_bytes() == source.read_bytes()
    download_raster(job, "asset.tif", target)
    assert len(attempts) == 2
    target.write_bytes(b"corrupt")
    download_raster(job, "asset.tif", target)
    assert len(attempts) == 3
    job.job_id = "different-job"
    download_raster(job, "asset.tif", target)
    assert len(attempts) == 4


def test_permission_failure_preserves_download_for_resume(tmp_path, monkeypatch):
    from floodlab.eo_core.pair_jobs import download_raster

    source = write_raster(tmp_path / "fixture.tif")
    target = tmp_path / "later.tif"
    job = MagicMock()
    job.job_id = "finished"
    download = job.get_results.return_value.download_file
    download.side_effect = lambda target, key: shutil.copyfile(source, target)
    original = type(target).replace

    def locked(self, destination):
        if self.suffix == ".download":
            raise PermissionError("locked")
        return original(self, destination)

    monkeypatch.setattr(type(target), "replace", locked)
    with pytest.raises(PermissionError):
        download_raster(job, "asset.tif", target, sleep=lambda _: None)
    assert target.with_suffix(".pending.json").exists()
    assert target.with_suffix(".download").read_bytes() == source.read_bytes()
    monkeypatch.setattr(type(target), "replace", original)
    download_raster(job, "asset.tif", target)
    download.assert_called_once()
    assert target.read_bytes() == source.read_bytes()


def test_local_recovery_receipt_reconciles_without_download(tmp_path):
    from floodlab.eo_core.pair_jobs import download_raster, sha256_file, write_json

    target = write_raster(tmp_path / "later.tif")
    job = MagicMock()
    job.job_id = "saved-job"
    write_json(
        target.with_suffix(".pending.json"),
        {
            "job_id": job.job_id,
            "asset_key": None,
            "sha256": sha256_file(target),
            "recovery": "local-full-raster-read",
        },
    )
    download_raster(job, "actual-asset.tif", target)
    job.get_results.assert_not_called()
    receipt = json.loads(target.with_suffix(".receipt.json").read_text())
    assert receipt["asset_key"] == "actual-asset.tif"
