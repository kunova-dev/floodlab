"""Deterministic, atomic cache receipts for reusable environmental assets."""

import json
import os
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

SCHEMA_VERSION = "environment-cache-v1"


def canonical_digest(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return sha256(encoded).hexdigest()


def cache_key(*, source_checksum: str, source_version: str, aoi_geojson: dict,
              grid: dict, algorithm: dict, reference_period: str | None) -> str:
    """Identity includes every fact that could make an asset incompatible."""
    return canonical_digest(
        {
            "schema": SCHEMA_VERSION,
            "source_checksum": source_checksum,
            "source_version": source_version,
            "aoi": aoi_geojson,
            "grid": grid,
            "algorithm": algorithm,
            "reference_period": reference_period,
        }
    )


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, path)


def load_receipt(path: Path, key: str) -> dict | None:
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return receipt if receipt.get("cache_key") == key and receipt.get("schema") == SCHEMA_VERSION else None
