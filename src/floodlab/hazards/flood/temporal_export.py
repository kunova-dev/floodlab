"""Explicit temporal GeoTIFF value semantics independent of classification."""

import numpy as np  # noqa: I001


NOT_OBSERVED_U8 = np.uint8(255)
NOT_OBSERVED_U16 = np.uint16(65535)


def binary_export_values(mask: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """1 inundated, 0 observed-negative, 255 not observed."""
    return np.where(valid, np.asarray(mask, dtype="uint8"), NOT_OBSERVED_U8).astype("uint8")


def count_export_values(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Counts remain unavailable where no usable observation contributed."""
    return np.where(valid, values, NOT_OBSERVED_U16).astype("uint16")
