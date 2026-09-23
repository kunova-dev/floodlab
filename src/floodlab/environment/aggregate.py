"""Native values remain authoritative; helpers only summarize supplied arrays/geometries."""

import numpy as np


def continuous_summary(values, valid, domain):
    use = np.asarray(valid, bool) & np.asarray(domain, bool) & np.isfinite(values)
    return {"coverage_pixels": int(use.sum()), "mean": float(np.mean(values[use])) if use.any() else None, "median": float(np.median(values[use])) if use.any() else None}


def categorical_summary(values, valid, domain):
    use = np.asarray(valid, bool) & np.asarray(domain, bool)
    classes, counts = np.unique(np.asarray(values)[use], return_counts=True)
    return {"coverage_pixels": int(use.sum()), "classes": {str(key): int(value) for key, value in zip(classes, counts, strict=True)}}
