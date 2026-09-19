"""Array algorithms only: inputs must already be calibrated and co-registered."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy import ndimage


def to_db(power: ArrayLike) -> NDArray:
    """Convert linear power (not amplitude); nonpositive/nonfinite values become NaN."""
    values = np.asarray(power, dtype=float)
    output = np.full(values.shape, np.nan)
    valid = np.isfinite(values) & (values > 0)
    output[valid] = 10 * np.log10(values[valid])
    return output


def water_mask(db: ArrayLike, threshold: float = -17.0) -> NDArray:
    """Experimental low-backscatter classifier, not a universal water detector."""
    if not np.isfinite(threshold):
        raise ValueError("Threshold must be finite")
    values = np.asarray(db, dtype=float)
    return np.isfinite(values) & (values <= threshold)


def change_db(before: ArrayLike, event: ArrayLike) -> NDArray:
    """Event minus pre-event dB; invalid pairs remain NaN."""
    a, b = np.asarray(before, dtype=float), np.asarray(event, dtype=float)
    if a.shape != b.shape:
        raise ValueError("Inputs must share the same grid and shape")
    result = np.full(a.shape, np.nan)
    valid = np.isfinite(a) & np.isfinite(b)
    result[valid] = b[valid] - a[valid]
    return result


def otsu_threshold(db: ArrayLike, bins: int = 128) -> float:
    """Histogram Otsu split; validity depends on a suitable bimodal scene."""
    values = np.asarray(db, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 2 or np.ptp(values) == 0 or bins < 2:
        raise ValueError("Otsu needs variable valid data and at least two bins")
    counts, edges = np.histogram(values, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    weights = np.cumsum(counts)
    sums = np.cumsum(counts * centers)
    denominator = weights[:-1] * (weights[-1] - weights[:-1])
    score = np.full(bins - 1, -np.inf)
    valid = denominator > 0
    score[valid] = (
        sums[-1] * weights[:-1][valid] - sums[:-1][valid] * weights[-1]
    ) ** 2 / denominator[valid]
    return float(edges[np.argmax(score) + 1])


def cleanup(mask: ArrayLike, min_pixels: int = 4) -> NDArray:
    """Remove small 4-connected components without filling invalid pixels."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or min_pixels < 1:
        raise ValueError("Require a 2D mask and positive minimum component size")
    labels, _ = ndimage.label(mask)
    sizes = np.bincount(labels.ravel())
    return mask & (sizes[labels] >= min_pixels)


def pixel_area_m2(
    transform: tuple[float, float, float, float, float, float], *, crs_units: str
) -> float:
    """Area from affine (a,b,c,d,e,f); require projected metre units, never degrees."""
    if crs_units != "metre":
        raise ValueError("Reproject to an appropriate metric CRS or supply geodesic pixel areas")
    a, b, _, d, e, _ = transform
    area = abs(a * e - b * d)
    if not np.isfinite(area) or area <= 0:
        raise ValueError("Invalid affine pixel area")
    return float(area)


def inundated_area(mask: ArrayLike, areas_m2: ArrayLike) -> float:
    """Sum constant or per-pixel metric areas; output square metres."""
    mask, areas = np.asarray(mask, dtype=bool), np.asarray(areas_m2, dtype=float)
    if areas.ndim != 0 and areas.shape != mask.shape:
        raise ValueError("Area grid must match the mask")
    if not np.all(np.isfinite(areas) & (areas > 0)):
        raise ValueError("Pixel areas must be finite and positive")
    return float(np.sum(mask * areas))


@dataclass
class FloodResult:
    mask: NDArray
    observed_derived: dict
    configuration: dict
    assumptions: list[str]
    qc_confidence: dict


def analyze(
    before_db: ArrayLike,
    event_db: ArrayLike,
    areas_m2: ArrayLike,
    water_db: float = -17,
    drop_db: float = -3,
    min_pixels: int = 4,
    permanent_water: ArrayLike | None = None,
) -> FloodResult:
    """Probable new inundation: dark event, dry baseline, negative change, optional exclusion."""
    if not np.isfinite(drop_db) or drop_db >= 0:
        raise ValueError("Require a finite negative change threshold")
    before, event = np.asarray(before_db, dtype=float), np.asarray(event_db, dtype=float)
    delta = change_db(before, event)
    valid = np.isfinite(delta)
    mask = valid & water_mask(event, water_db) & ~water_mask(before, water_db) & (delta <= drop_db)
    if permanent_water is not None:
        exclusion = np.asarray(permanent_water)
        if exclusion.shape != mask.shape or exclusion.dtype != bool:
            raise ValueError("Permanent-water exclusion must be a matching boolean grid")
        mask &= ~exclusion
    mask = cleanup(mask, min_pixels)
    area = inundated_area(mask, areas_m2)
    return FloodResult(
        mask,
        {"probable_new_inundation_m2": area, "pixels": int(mask.sum())},
        {"water_db": water_db, "drop_db": drop_db, "min_pixels": min_pixels},
        [
            "Inputs are calibrated, terrain-corrected dB power on the same grid and polarization.",
            "Comparable orbit geometry; low backscatter can also reflect shadow or smooth soil.",
        ],
        {
            "valid_fraction": float(valid.mean()) if valid.size else 0.0,
            "permanent_water_excluded": permanent_water is not None,
            "confidence": "Experimental; no validated accuracy estimate",
        },
    )
