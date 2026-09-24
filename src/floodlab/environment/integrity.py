"""Integrity and serialization helpers used by generic environmental execution."""

import json
from hashlib import sha256
from pathlib import Path

import numpy as np

from floodlab.eo_core.integrity import sha256_file as _sha256_file


def sha256_file(path: Path) -> str:
    return _sha256_file(path)


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def array_checksum(values: np.ndarray, valid: np.ndarray) -> str:
    """Checksum deterministic native values plus their validity domain."""
    digest = sha256()
    for item in (np.asarray(values, dtype="float32"), np.asarray(valid, dtype="uint8")):
        digest.update(str(item.shape).encode())
        digest.update(item.tobytes(order="C"))
    return digest.hexdigest()


def metadata_checksum(value: dict) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
