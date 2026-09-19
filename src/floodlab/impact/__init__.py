"""Future exposure intersection contracts; no loss modelling or proprietary data."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AffectedSummary:
    asset_count: int
    asset_ids: list[str]
    provenance: dict


class ImpactAnalyzer(Protocol):
    """Implementations must validate CRS, geometry, overlap semantics and exposure permissions."""

    def intersect(self, flood_geojson: dict, exposure_geojson: dict) -> AffectedSummary: ...
