"""Hazard-neutral product access and processing contracts; backends are not implemented."""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from .catalogue import Acquisition


class ProductAccess(Protocol):
    """Resolve authorized access independently from discovery."""

    def resolve(self, acquisition: Acquisition, asset_key: str) -> str: ...


class Preprocessor(Protocol):
    """Future SNAP/openEO/service backend must return documented calibrated products."""

    def prepare(self, observations: list[Acquisition], parameters: dict) -> dict: ...


@dataclass
class ProcessingJob:
    """Serializable preparation manifest, not an executed processing job."""

    observations: list[dict]
    aoi: dict
    source: str
    query: dict
    configuration: dict
    id: str = field(default_factory=lambda: str(uuid4()))
    created_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: str = "0.1.0"
    status: str = "AWAITING_PREPROCESSING"
    assumptions: list[str] = field(
        default_factory=lambda: [
            "Catalogue assets are not evidence of analysis-ready backscatter.",
            "Calibration, terrain correction, co-registration and valid-data masks are required.",
        ]
    )

    def to_dict(self) -> dict:
        return asdict(self)


def readiness(observations: list[Acquisition]) -> dict:
    """Report metadata comparability without asserting scientific readiness."""
    fields = ("orbit", "relative_orbit", "instrument_mode")
    missing = [key for key in fields if any(getattr(x, key) is None for x in observations)]
    differing = [key for key in fields if len({getattr(x, key) for x in observations}) > 1]
    common = (
        set.intersection(*(set(x.polarizations) for x in observations)) if observations else set()
    )
    return {
        "observations": len(observations),
        "missing_metadata": missing,
        "differing_metadata": differing,
        "common_polarizations": sorted(common),
        "paired_candidates": len(observations) >= 2
        and not missing
        and not differing
        and bool(common),
        "processing_status": "AWAITING_PREPROCESSING",
        "confidence": "Not evaluated; metadata checks only",
    }
