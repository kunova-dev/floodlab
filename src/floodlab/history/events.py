"""Functional candidate grouping; indicators require independently processed observations."""

from dataclasses import dataclass
from datetime import date

import numpy as np


@dataclass(frozen=True)
class Indicator:
    date: date
    fraction: float
    observation_id: str


@dataclass(frozen=True)
class CandidateEvent:
    first_observed: date
    last_observed: date
    peak_observed: date
    peak_fraction: float
    observation_ids: list[str]


def detect_events(
    observations: list[Indicator],
    baseline: list[float],
    gap_days: int = 12,
    anomaly_multiplier: float = 3,
    minimum_excess: float = 0.02,
) -> tuple[float, list[CandidateEvent]]:
    """Median/MAD baseline; group anomalies separated by at most gap_days.

    Dates bound observed anomalies, not true onset/recession. Missing dates do not imply dryness.
    Supply a representative independent baseline rather than silently fitting the event itself.
    """
    values = np.asarray(baseline, dtype=float)
    if values.size < 3 or not np.all(np.isfinite(values) & (values >= 0) & (values <= 1)):
        raise ValueError("Supply at least three valid baseline fractions in [0,1]")
    if (
        gap_days < 0
        or not np.isfinite(anomaly_multiplier)
        or anomaly_multiplier < 0
        or not np.isfinite(minimum_excess)
        or minimum_excess <= 0
    ):
        raise ValueError("Invalid event detection settings")
    if any(not np.isfinite(o.fraction) or not 0 <= o.fraction <= 1 for o in observations):
        raise ValueError("Observation fractions must be in [0,1]")
    if len({o.observation_id for o in observations}) != len(observations):
        raise ValueError("Observation identifiers must be unique")
    median = float(np.median(values))
    threshold = median + max(
        minimum_excess, anomaly_multiplier * 1.4826 * float(np.median(abs(values - median)))
    )
    groups: list[list[Indicator]] = []
    for observation in sorted(observations, key=lambda o: o.date):
        if observation.fraction <= threshold:
            continue
        if not groups or (observation.date - groups[-1][-1].date).days > gap_days:
            groups.append([])
        groups[-1].append(observation)
    events = []
    for group in groups:
        peak = max(group, key=lambda o: o.fraction)
        events.append(
            CandidateEvent(
                group[0].date,
                group[-1].date,
                peak.date,
                peak.fraction,
                [o.observation_id for o in group],
            )
        )
    return threshold, events
