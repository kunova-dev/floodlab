"""Sensor-sequence temporal products on already analysis-ready observations."""

from dataclasses import dataclass
from datetime import date
from warnings import catch_warnings, filterwarnings

import numpy as np

from .engine import cleanup

WINDOWS = (
    ("BASELINE", "2017-01-01", "2017-03-15"),
    ("ESCALATION", "2017-03-16", "2017-03-24"),
    ("CORE_EVENT", "2017-03-25", "2017-03-31"),
    ("EARLY_RECESSION", "2017-04-01", "2017-04-10"),
    ("RECOVERY", "2017-04-11", "9999-12-31"),
)


@dataclass(frozen=True)
class EventDefinition:
    event_id: str
    event_date: str
    windows: tuple = WINDOWS

    def classify(self, timestamp):
        day = timestamp[:10]
        date.fromisoformat(day)
        for name, start, end in self.windows:
            if start <= day <= end:
                return name
        raise ValueError("Timestamp outside event chronology")


@dataclass(frozen=True)
class AcquisitionSequence:
    mission: str
    relative_orbit: int | None
    orbit_direction: str | None
    mode: str | None
    polarisation: tuple[str, ...]

    @property
    def id(self):
        return "|".join(
            str(value)
            for value in (
                self.mission,
                self.relative_orbit,
                self.orbit_direction,
                self.mode,
                ",".join(self.polarisation),
            )
        )


@dataclass(frozen=True)
class TemporalObservation:
    product_id: str
    timestamp: str
    sequence: AcquisitionSequence
    values_db: np.ndarray
    valid: np.ndarray
    land: np.ndarray
    permanent_water: np.ndarray

    def __post_init__(self):
        if (
            not self.values_db.shape
            == self.valid.shape
            == self.land.shape
            == self.permanent_water.shape
        ):
            raise ValueError("Temporal observation arrays must share a grid")


def group_sequences(acquisitions):
    """Group metadata records; ascending/descending never collapse into one sequence."""
    result = {}
    for item in acquisitions:
        sequence = AcquisitionSequence(
            item["mission"],
            item.get("relative_orbit"),
            item.get("orbit_direction"),
            item.get("acquisition_mode"),
            tuple((item.get("polarisation") or "").split(",")),
        )
        result.setdefault(sequence.id, []).append(item)
    return {
        key: sorted(items, key=lambda item: item["acquisition_datetime"])
        for key, items in result.items()
    }


def baseline_median(observations):
    """Per-pixel median across valid baseline dates; invalid/missing pixels remain NaN."""
    if len(observations) < 2:
        raise ValueError("Temporal baseline requires at least two observations")
    shape = observations[0].values_db.shape
    if any(item.values_db.shape != shape for item in observations):
        raise ValueError("Baseline observations require a shared analysis grid")
    stack = np.stack(
        [np.where(item.valid & item.land, item.values_db, np.nan) for item in observations]
    )
    with catch_warnings():
        filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
        with np.errstate(all="ignore"):
            return np.nanmedian(stack, axis=0), np.sum(np.isfinite(stack), axis=0)


def observed_inundation(
    observation,
    baseline_db,
    baseline_count,
    *,
    water_db=-18.0,
    drop_db=-3.0,
    minimum_baseline=2,
    min_pixels=9,
):
    """Classify a single observed date; unobserved/invalid pixels are never negative evidence."""
    if observation.values_db.shape != baseline_db.shape:
        raise ValueError("Observation and baseline grids differ")
    valid = (
        observation.valid
        & observation.land
        & (baseline_count >= minimum_baseline)
        & np.isfinite(baseline_db)
    )
    water = observation.values_db <= water_db
    drop = observation.values_db - baseline_db <= drop_db
    inundated = cleanup(valid & water & drop & ~observation.permanent_water, min_pixels)
    return inundated, valid


def temporal_products(observations, masks, valid_masks):
    """Union/count products; missing observations stay outside valid counts."""
    if not observations or len(observations) != len(masks) or len(masks) != len(valid_masks):
        raise ValueError("Need matched non-empty observations, masks and valid masks")
    shape = masks[0].shape
    if any(
        mask.shape != shape or valid.shape != shape
        for mask, valid in zip(masks, valid_masks, strict=True)
    ):
        raise ValueError("Temporal products require a shared grid")
    flood_count = np.sum(np.stack(masks), axis=0, dtype="uint16")
    valid_count = np.sum(np.stack(valid_masks), axis=0, dtype="uint16")
    union = flood_count > 0
    fraction = np.divide(
        flood_count, valid_count, out=np.full(shape, np.nan), where=valid_count > 0
    )
    areas = [int(mask.sum()) for mask in masks]
    maximum_index = max(
        range(len(masks)),
        key=lambda index: (
            areas[index],
            observations[index].timestamp,
            observations[index].product_id,
        ),
    )
    return {
        "event_observed_union": union,
        "observed_flood_count": flood_count,
        "valid_observation_count": valid_count,
        "observed_fraction": fraction,
        "maximum_index": maximum_index,
        "maximum_single_date": masks[maximum_index],
    }
