"""Typed, provenance-preserving environmental assets and variables."""

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class CoverageStatus(StrEnum):
    VALID = "VALID"
    NO_COVERAGE = "NO_COVERAGE"
    UNAVAILABLE_PROVIDER = "UNAVAILABLE_PROVIDER"
    RETRIEVAL_FAILURE = "RETRIEVAL_FAILURE"
    NOT_OBSERVED = "NOT_OBSERVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TemporalRelationship(StrEnum):
    EVENT_TIME = "EVENT_TIME"
    NEAR_EVENT = "NEAR_EVENT"
    CLIMATOLOGY = "CLIMATOLOGY"
    STATIC = "STATIC"
    MODERN_CONTEXTUAL = "MODERN_CONTEXTUAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EnvironmentalAsset:
    asset_id: str
    provider: str
    dataset: str
    version: str
    checksum: str
    reference_period: str | None
    temporal_relationship: TemporalRelationship
    native_resolution: str | None
    retrieved_utc: str | None
    licence: str | None
    coverage_status: CoverageStatus
    limitations: tuple[str, ...] = ()

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class EnvironmentalVariable:
    variable_id: str
    name: str
    value_kind: str
    units: str | None
    temporal_relationship: TemporalRelationship
    coverage_status: CoverageStatus
    upstream_assets: tuple[EnvironmentalAsset, ...]
    derivation_algorithm: str | None = None
    derivation_version: str | None = None
    parameters: dict = field(default_factory=dict)
    spatial_processing: str | None = None
    temporal_processing: str | None = None
    checksum: str | None = None
    derived_data_checksum: str | None = None
    metadata_checksum: str | None = None
    native_grid: dict | None = None
    nodata_semantics: str | None = None
    limitations: tuple[str, ...] = ()

    def __post_init__(self):
        if self.derivation_algorithm and not self.upstream_assets:
            raise ValueError("Derived environmental variables require upstream assets")
        if (
            self.coverage_status == CoverageStatus.VALID
            and self.temporal_relationship == TemporalRelationship.EVENT_TIME
            and not any(
                asset.temporal_relationship == TemporalRelationship.EVENT_TIME
                for asset in self.upstream_assets
            )
        ):
            raise ValueError("EVENT_TIME cannot be inferred from a non-event asset")

    def to_dict(self):
        value = asdict(self)
        value["upstream_assets"] = [asset.to_dict() for asset in self.upstream_assets]
        return value
