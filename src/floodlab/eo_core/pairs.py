"""Explain acquisition comparability without inferring hazard timing."""

from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import combinations

from pyproj import Geod
from shapely.geometry import shape

from .aoi import AOI
from .catalogue import Acquisition


@dataclass(frozen=True)
class PairAssessment:
    compatible: bool
    reasons: list[str]
    warnings: list[str]
    coverage: dict[str, float]
    bands: list[str]
    timing: str = (
        "Earlier/later only; independent pre-flood/during-flood evidence not incorporated."
    )

    def to_dict(self) -> dict:
        return asdict(self)


def assess_pair(
    earlier: Acquisition,
    later: Acquisition,
    aoi: AOI,
    bands: tuple[str, ...] = ("VV",),
    minimum_coverage: float = 0.8,
) -> PairAssessment:
    """Check geometry overlap using geodesic areas, metadata, order and requested bands."""
    if not 0 < minimum_coverage <= 1 or not bands:
        raise ValueError("Require requested bands and a coverage fraction in (0,1]")
    reasons, warnings, failures = [], [], []
    if earlier.id == later.id or datetime.fromisoformat(earlier.datetime) >= datetime.fromisoformat(
        later.datetime
    ):
        failures.append("Require distinct, chronologically ordered acquisitions")
    for field in ("relative_orbit", "orbit", "instrument_mode"):
        first, second = getattr(earlier, field), getattr(later, field)
        if first is None or second is None or first != second:
            failures.append(f"Missing or mismatched {field}: {first} / {second}")
        else:
            reasons.append(f"Matching {field}: {first}")
    common = set(earlier.polarizations) & set(later.polarizations)
    if not set(bands) <= common:
        failures.append("Requested polarization absent from one or both acquisitions")
    else:
        reasons.append("Shared requested polarization: " + ", ".join(bands))
    geod = Geod(ellps="WGS84")

    def area(geometry):
        return abs(geod.geometry_area_perimeter(geometry)[0]) if not geometry.is_empty else 0.0

    first = aoi.geometry.intersection(shape(earlier.geometry))
    second = aoi.geometry.intersection(shape(later.geometry))
    denominator = area(aoi.geometry)
    if denominator <= 0:
        raise ValueError("AOI has no measurable geodesic area")
    coverage = {
        "earlier": min(1.0, area(first) / denominator),
        "later": min(1.0, area(second) / denominator),
        "common": min(1.0, area(first.intersection(second)) / denominator),
    }
    if coverage["common"] < minimum_coverage:
        failures.append(
            f"Common AOI footprint coverage {coverage['common']:.1%} below {minimum_coverage:.1%}"
        )
    else:
        reasons.append(f"Common AOI footprint coverage {coverage['common']:.1%}")
    if earlier.platform != later.platform or earlier.platform is None:
        warnings.append("Different/unknown platform: review cross-platform radiometry")
    warnings.append(
        "Footprint overlap is not valid-pixel coverage; verify raster QC after processing"
    )
    return PairAssessment(not failures, reasons + failures, warnings, coverage, list(bands))


def candidate_pairs(observations: list[Acquisition], aoi: AOI, **kwargs) -> list[tuple]:
    """Rank compatible pairs by common coverage, same platform, then shortest gap.

    This ranking is technical only, not a flood-date ranking.
    """
    ordered = sorted(observations, key=lambda o: datetime.fromisoformat(o.datetime))
    pairs = [(a, b, assess_pair(a, b, aoi, **kwargs)) for a, b in combinations(ordered, 2)]
    pairs = [p for p in pairs if p[2].compatible]
    return sorted(
        pairs,
        key=lambda p: (
            -round(p[2].coverage["common"], 4),
            p[0].platform != p[1].platform,
            (
                datetime.fromisoformat(p[1].datetime) - datetime.fromisoformat(p[0].datetime)
            ).total_seconds(),
        ),
    )
