"""Temporal reconstruction semantics are independent of EO download and processing."""

import numpy as np
import pytest

from floodlab.hazards.flood.temporal import (
    AcquisitionSequence,
    EventDefinition,
    TemporalObservation,
    baseline_median,
    group_sequences,
    observed_inundation,
    temporal_products,
)
from floodlab.hazards.flood.temporal_export import binary_export_values, count_export_values


def observation(product_id, timestamp, values, valid=None):
    values = np.asarray(values, dtype=float)
    return TemporalObservation(
        product_id,
        timestamp,
        AcquisitionSequence("SENTINEL-1", 91, "ascending", "IW", ("VV",)),
        values,
        np.ones_like(values, bool) if valid is None else np.asarray(valid, bool),
        np.array([[1, 1, 0]], bool),
        np.array([[0, 0, 0]], bool),
    )


def test_windows_and_sequence_separation():
    event = EventDefinition("fixture", "2017-03-27")
    assert event.classify("2017-03-26T11:00:00Z") == "CORE_EVENT"
    groups = group_sequences(
        [
            {
                "mission": "SENTINEL-1",
                "relative_orbit": 91,
                "orbit_direction": "ascending",
                "acquisition_mode": "IW",
                "polarisation": "VV,VH",
                "acquisition_datetime": "2017-03-23T00:00:00Z",
            },
            {
                "mission": "SENTINEL-1",
                "relative_orbit": 40,
                "orbit_direction": "descending",
                "acquisition_mode": "IW",
                "polarisation": "VV",
                "acquisition_datetime": "2017-03-26T00:00:00Z",
            },
        ]
    )
    assert len(groups) == 2


def test_baseline_partial_coverage_and_temporal_counts():
    baseline, count = baseline_median(
        [
            observation("a", "2017-02-01T00:00:00Z", [[-10, -10, -10]]),
            observation("b", "2017-02-12T00:00:00Z", [[-12, -10, -10]]),
        ]
    )
    event = observation("event", "2017-03-26T00:00:00Z", [[-20, -20, -20]], [[1, 0, 1]])
    flood, valid = observed_inundation(event, baseline, count, min_pixels=1)
    assert flood.tolist() == [[True, False, False]] and valid.tolist() == [[True, False, False]]
    products = temporal_products(
        [event, event],
        [flood, np.array([[False, True, False]])],
        [valid, np.array([[False, True, False]])],
    )
    assert products["event_observed_union"].tolist() == [[True, True, False]]
    assert products["valid_observation_count"].tolist() == [[1, 1, 0]]
    assert np.isnan(products["observed_fraction"][0, 2])
    assert products["maximum_index"] == 0
    union = binary_export_values(products["event_observed_union"], products["valid_observation_count"] > 0)
    maximum = binary_export_values(products["maximum_single_date"], valid)
    assert union.tolist() == [[1, 1, 255]]
    assert maximum.tolist() == [[1, 255, 255]]
    assert count_export_values(products["valid_observation_count"], products["valid_observation_count"] > 0).tolist() == [[1, 1, 65535]]


def test_baseline_requires_multiple_shared_grid_observations():
    one = observation("a", "2017-02-01T00:00:00Z", [[-10, -10, -10]])
    with pytest.raises(ValueError, match="two"):
        baseline_median([one])
