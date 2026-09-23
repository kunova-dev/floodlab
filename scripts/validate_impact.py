"""Check Impact Engine output against its original flood archive."""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from floodlab.eo_core.pair_jobs import sha256_file


def validate(folder):
    provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    features = json.loads((folder / "grid.geojson").read_text(encoding="utf-8"))["features"]
    assert len(features) == provenance["cell_count"]
    assert len({f["properties"]["h3_index"] for f in features}) == len(features)
    assert all(
        0 <= f["properties"]["terrestrial_affected_pct"] <= 100
        for f in features
        if f["properties"]["terrestrial_affected_pct"] is not None
    )
    archive_name = "analysis.zip" if (folder / "analysis.zip").exists() else "impact.zip"
    with zipfile.ZipFile(folder / archive_name) as archive:
        assert archive.testzip() is None
        checks = json.loads(archive.read("checksums.json"))
        for name, digest in checks.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        if archive_name == "analysis.zip":
            source = json.loads(archive.read("impact/source-checksums.json"))
            assert hashlib.sha256(archive.read("provenance.json")).hexdigest() == source["provenance.json"]
            assert hashlib.sha256(archive.read("flood.geojson")).hexdigest() == source["flood.geojson"]
            assert hashlib.sha256(archive.read("land.tif")).hexdigest() == source["land.tif"]
    if archive_name == "impact.zip":
        checks = json.loads((folder / "checksums.json").read_text(encoding="utf-8"))
        for name, digest in checks.items():
            if name != "impact.zip":
                assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest
    return {
        "impact_analysis_id": provenance["analysis_id"],
        "resolution": provenance["resolution"],
        "cell_count": len(features),
        "zip_sha256": sha256_file(folder / archive_name),
        "source_analysis_id": provenance.get("metadata", {}).get("source_analysis_id"),
        "status": "PASS",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    print(json.dumps(validate(parser.parse_args().folder), indent=2))
