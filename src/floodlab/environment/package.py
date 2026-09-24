"""Environmental package export independent of hazard, exposure and impact code."""

import json
import zipfile
from pathlib import Path

from .integrity import sha256_file, write_json


def export_environment_package(folder: Path, *, provenance: dict, summaries: dict, sidecar: dict) -> Path:
    """Write an immutable-style DRAFT package and self-checksum every payload."""
    folder.mkdir(parents=True, exist_ok=False)
    write_json(folder / "provenance.json", provenance)
    write_json(folder / "summaries.json", summaries)
    write_json(folder / "h3-environment.geojson", sidecar)
    checks = {p.name: sha256_file(p) for p in folder.iterdir() if p.is_file()}
    write_json(folder / "checksums.json", checks)
    with zipfile.ZipFile(folder / "environment.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for path in folder.iterdir():
            if path.is_file() and path.name != "environment.zip":
                archive.write(path, path.name)
    zip_checksum = sha256_file(folder / "environment.zip")
    write_json(
        folder / "package.json",
        {
            "schema": "environment-package-v2",
            "package_sha256": zip_checksum,
            "payload_manifest_sha256": sha256_file(folder / "checksums.json"),
            "expected_members": sorted([*checks, "checksums.json"]),
            "status": "DRAFT",
        },
    )
    return folder


def validate_environment_package(folder: Path) -> dict:
    checks = json.loads((folder / "checksums.json").read_text(encoding="utf-8"))
    package = json.loads((folder / "package.json").read_text(encoding="utf-8"))
    for name, expected in checks.items():
        if sha256_file(folder / name) != expected:
            raise ValueError(f"Environmental package checksum mismatch: {name}")
    archive_path = folder / "environment.zip"
    if package.get("package_sha256") != sha256_file(archive_path):
        raise ValueError("Environmental ZIP digest mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Environmental ZIP CRC failure")
        names = set(archive.namelist())
        expected_names = set(package.get("expected_members", [*checks, "checksums.json"]))
        if names != expected_names:
            raise ValueError("Environmental ZIP members differ from package manifest")
        archived = json.loads(archive.read("checksums.json"))
        if archived != checks:
            raise ValueError("Environmental ZIP checksum manifest differs")
        for name, expected in checks.items():
            from hashlib import sha256

            if sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f"Environmental ZIP payload checksum mismatch: {name}")
    if package.get("schema") == "environment-package-v2" and package.get(
        "payload_manifest_sha256"
    ) != sha256_file(folder / "checksums.json"):
        raise ValueError("Environmental payload manifest digest mismatch")
    return {"files": len(checks), "zip_sha256": sha256_file(archive_path)}
