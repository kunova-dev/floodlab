"""Independent optical evidence; cloudy and missing data are never dry observations."""

import numpy as np
from scipy.ndimage import binary_dilation


def optical_water(green, swir, scl, threshold=0.0, cloud_buffer_pixels=3):
    if green.shape != swir.shape or scl.shape != green.shape:
        raise ValueError("Optical bands must share a grid")
    cloud = np.isin(scl, [1, 3, 8, 9, 10, 11])
    if cloud_buffer_pixels:
        cloud = binary_dilation(cloud, iterations=cloud_buffer_pixels)
    valid = (
        np.isin(scl, [4, 5, 6])
        & ~cloud
        & np.isfinite(green)
        & np.isfinite(swir)
        & (green > 0)
        & (swir > 0)
    )
    index = np.full(green.shape, np.nan, dtype="float32")
    np.divide(green - swir, green + swir, out=index, where=valid)
    return valid & (index > threshold), valid


def baseline_classes(history, land, occurrence=None):
    """0 ocean, 1 historically non-water, 2 recurrent/seasonal, 3 persistent, 4 uncertain."""
    history = np.asarray(history)
    if history.ndim != 3 or history.shape[1:] != land.shape or history.shape[0] < 2:
        raise ValueError("A multi-observation baseline on the common grid is required")
    if not np.isin(history, [0, 1, 2, 3, 255]).all():
        raise ValueError("Unknown water-history class")
    baseline = np.full(land.shape, 4, dtype="uint8")
    complete = np.isin(history, [1, 2, 3]).all(axis=0)
    baseline[complete & (history == 1).all(axis=0)] = 1
    baseline[np.isin(history, [2, 3]).any(axis=0)] = 2
    baseline[complete & (history == 3).all(axis=0)] = 3
    if occurrence is not None:
        if (
            occurrence.shape != land.shape
            or not np.isin(occurrence, list(range(101)) + [255]).all()
        ):
            raise ValueError("Invalid historical occurrence grid")
        baseline[(baseline == 4) & (occurrence == 0)] = 1
    baseline[~land] = 0
    return baseline


def evidence_classes(s1, baseline, valid, s2=None, s2_valid=None):
    """Evidence labels, not calibrated probabilities; missing optical remains unknown."""
    if any(x.shape != s1.shape for x in [baseline, valid]):
        raise ValueError("Evidence grids differ")
    out = np.full(s1.shape, 7, dtype="uint8")
    out[valid & (baseline == 1)] = 0
    out[valid & np.isin(baseline, [2, 3])] = 5
    out[baseline == 0] = 6
    out[valid & s1 & (baseline == 1)] = 2
    if s2 is not None and s2_valid is not None:
        if s2.shape != s1.shape or s2_valid.shape != s1.shape:
            raise ValueError("Optical grid differs")
        eligible = valid & s2_valid & (baseline == 1)
        out[eligible & s1 & s2] = 1
        out[eligible & s1 & ~s2] = 3
        out[eligible & ~s1 & s2] = 4
    return out
