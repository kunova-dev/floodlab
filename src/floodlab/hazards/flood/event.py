"""Experimental flood masks and descriptive comparison; no accuracy claim."""

import numpy as np

from .engine import cleanup, otsu_threshold, to_db, water_mask


def classify(before, during, valid, threshold=None, drop_db=-3.0, min_pixels=9):
    if before.shape != during.shape or valid.shape != before.shape:
        raise ValueError("All arrays must share a grid")
    if not np.isfinite(drop_db) or drop_db >= 0 or min_pixels < 1:
        raise ValueError("Require negative finite change threshold and positive mapping unit")
    valid = valid & np.isfinite(before) & np.isfinite(during) & (before > 0) & (during > 0)
    if valid.sum() < 2:
        raise ValueError("Insufficient common valid coverage")
    a, b = to_db(before), to_db(during)
    sample = np.concatenate(
        [
            a[valid][:: max(1, int(valid.sum() / 100000))],
            b[valid][:: max(1, int(valid.sum() / 100000))],
        ]
    )
    otsu = otsu_threshold(sample)
    threshold = -18.0 if threshold is None else float(threshold)
    if not np.isfinite(threshold):
        raise ValueError("Threshold must be finite")
    before_water = valid & water_mask(a, threshold)
    during_water = valid & water_mask(b, threshold)
    flood = cleanup(during_water & ~before_water & ((b - a) <= drop_db), min_pixels)
    sensitivity = []
    for t in (threshold - 2, threshold, threshold + 2):
        for drop in (-2.0, -3.0, -4.0):
            m = cleanup(
                valid & water_mask(b, t) & ~water_mask(a, t) & ((b - a) <= drop), min_pixels
            )
            sensitivity.append({"water_db": t, "drop_db": drop, "pixels": int(m.sum())})
    return {"before": before_water, "during": during_water, "flood": flood, "valid": valid}, {
        "method": "Conservative absolute dark-water candidate AND baseline exclusion AND negative dB change",
        "water_db": threshold,
        "otsu_candidate_db": otsu,
        "threshold_rationale": "Provisional -18 dB open-water screen; not calibrated or validated. Global Otsu evaluated separately because its land/water class identity is unproven.",
        "otsu_flood_pixels": int(
            cleanup(
                valid & water_mask(b, otsu) & ~water_mask(a, otsu) & ((b - a) <= drop_db),
                min_pixels,
            ).sum()
        ),
        "drop_db": drop_db,
        "min_pixels": min_pixels,
        "connectivity": 4,
        "sensitivity": sensitivity,
        "limitations": [
            "Global Otsu is exploratory; bimodality/water-class identity not established.",
            "No terrain-shadow, urban double-bounce, vegetation or land-cover correction.",
            "Earlier observed water is not permanent water. No calibrated confidence score.",
            "Minimum mapping unit suppresses isolated noise and may remove genuine small floods.",
        ],
    }


def compare_reference(flood, reference, valid):
    if flood.shape != reference.shape or valid.shape != flood.shape:
        raise ValueError("Reference must share comparison grid")
    return {
        "agreement": valid & flood & reference,
        "possible_omission": valid & ~flood & reference,
        "possible_commission": valid & flood & ~reference,
    }
