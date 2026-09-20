"""Raster QC and explicit pair alignment; never interprets a raster as a flood map."""

from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject, transform_bounds
from shapely.geometry import box


def raster_qc(path: Path) -> dict:
    """Exact validity counts; bounded deterministic samples for robust statistics."""
    with rasterio.open(path) as src:
        bands = []
        for band in range(1, src.count + 1):
            total = valid_count = nodata_count = nonfinite_count = nonpositive_count = 0
            minimum, maximum = None, None
            samples = []
            stride = max(1, int(np.ceil(src.width * src.height / 200000)))
            for _, window in src.block_windows(band):
                data = src.read(band, window=window, masked=True)
                raw = data.data
                mask = np.ma.getmaskarray(data)
                finite = np.isfinite(raw)
                valid = ~mask & finite & (raw > 0)
                total += raw.size
                valid_count += int(valid.sum())
                nodata_count += int(mask.sum())
                nonfinite_count += int((~finite).sum())
                nonpositive_count += int((~mask & finite & (raw <= 0)).sum())
                if valid.any():
                    vals = raw[valid]
                    lo, hi = float(vals.min()), float(vals.max())
                    minimum = lo if minimum is None else min(minimum, lo)
                    maximum = hi if maximum is None else max(maximum, hi)
                # Global regular sample, independent of TIFF block shape.
                rows = np.arange(int(window.row_off), int(window.row_off + window.height))[:, None]
                cols = np.arange(int(window.col_off), int(window.col_off + window.width))[None, :]
                chosen = valid & (((rows * src.width + cols) % stride) == 0)
                samples.extend(raw[chosen].tolist())
            bands.append(
                {
                    "band": band,
                    "description": src.descriptions[band - 1],
                    "valid_fraction": valid_count / total,
                    "nodata_fraction": nodata_count / total,
                    "nonfinite_count": nonfinite_count,
                    "nonpositive_unmasked_count": nonpositive_count,
                    "min": minimum,
                    "max": maximum,
                    "percentiles": dict(
                        zip(["p02", "p50", "p98"], map(float, np.percentile(samples, [2, 50, 98])))
                    )
                    if samples
                    else {},
                    "percentile_sample_count": len(samples),
                }
            )
        return {
            "width": src.width,
            "height": src.height,
            "count": src.count,
            "crs": src.crs.to_string() if src.crs else None,
            "resolution": list(src.res),
            "transform": list(src.transform)[:6],
            "bounds": list(src.bounds),
            "nodata": str(src.nodata),
            "dtype": list(src.dtypes),
            "bands": bands,
            "validity_rule": "Raster mask AND finite AND strictly positive linear power; zero excluded conservatively",
        }


def grid_compatible(first: dict, second: dict) -> bool:
    return (
        bool(first["crs"])
        and first["crs"] == second["crs"]
        and first["width"] == second["width"]
        and first["height"] == second["height"]
        and first["count"] == second["count"]
        and np.allclose(first["transform"], second["transform"], rtol=0, atol=1e-7)
    )


def align_to_reference(reference: Path, source: Path, destination: Path) -> dict:
    """Explicit bilinear warp to reference grid; nonpositive/nodata pixels become NaN."""
    if destination.exists() or destination.resolve() in (reference.resolve(), source.resolve()):
        raise ValueError("Alignment destination must be a new file")
    with rasterio.open(reference) as ref, rasterio.open(source) as src:
        if not ref.crs or not src.crs or src.count != ref.count:
            raise ValueError("Need defined CRS and equal band counts for alignment")
        profile = ref.profile.copy()
        profile.update(dtype="float32", nodata=float("nan"), compress="deflate")
        with rasterio.open(destination, "w", **profile) as dst:
            for band in range(1, src.count + 1):
                data = src.read(band, masked=True).astype("float32").filled(np.nan)
                data[~np.isfinite(data) | (data <= 0)] = np.nan
                reproject(
                    data,
                    rasterio.band(dst, band),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=ref.transform,
                    dst_crs=ref.crs,
                    src_nodata=np.nan,
                    dst_nodata=np.nan,
                    resampling=Resampling.bilinear,
                )
                if src.descriptions[band - 1]:
                    dst.set_band_description(band, src.descriptions[band - 1])
    return {
        "method": "bilinear",
        "reference": reference.name,
        "source": source.name,
        "output": destination.name,
        "nodata": "NaN; nonpositive source values excluded",
        "warning": "Resampling changes values/coverage; inspect both native and aligned QC",
    }


def pair_qc(first: Path, second: Path, minimum_valid_fraction: float = 0.8) -> dict:
    """Report native-grid footprint and valid overlap; no implicit warp."""
    a, b = raster_qc(first), raster_qc(second)
    compatible = grid_compatible(a, b)
    warnings = []
    overlap = None
    if a["crs"] and b["crs"]:
        extent = transform_bounds(b["crs"], a["crs"], *b["bounds"], densify_pts=21)
        reference = box(*a["bounds"])
        overlap = reference.intersection(box(*extent)).area / reference.area
    if not compatible:
        warnings.append("Grids differ: explicit alignment required before pixelwise comparison")
    common = None
    if compatible:
        total = valid = 0
        with rasterio.open(first) as x, rasterio.open(second) as y:
            for _, window in x.block_windows(1):
                p = x.read(window=window, masked=True)
                q = y.read(window=window, masked=True)
                mask = (
                    ~np.ma.getmaskarray(p)
                    & ~np.ma.getmaskarray(q)
                    & np.isfinite(p.data)
                    & np.isfinite(q.data)
                    & (p.data > 0)
                    & (q.data > 0)
                ).all(axis=0)
                total += mask.size
                valid += int(mask.sum())
        common = valid / total
        if common < minimum_valid_fraction:
            warnings.append("Common positive valid coverage below configured minimum")
    for label, qc in [("earlier", a), ("later", b)]:
        if any(band["valid_fraction"] < minimum_valid_fraction for band in qc["bands"]):
            warnings.append(f"{label}: valid coverage below configured minimum")
    return {
        "earlier": a,
        "later": b,
        "grid_compatible": bool(compatible),
        "footprint_overlap_fraction_of_earlier": overlap,
        "common_valid_fraction": common,
        "status": "QC WARNING" if warnings else "QC PASS",
        "warnings": warnings,
    }


def preview_pair(
    first: Path, second: Path, max_size: int = 600
) -> tuple[list[np.ndarray], list[float]]:
    """Downsample for display only; shared 2–98 percent dB grayscale, transparent nodata."""
    images = []
    for path in (first, second):
        with rasterio.open(path) as src:
            scale = min(1.0, max_size / max(src.width, src.height))
            data = src.read(
                1,
                out_shape=(max(1, int(src.height * scale)), max(1, int(src.width * scale))),
                masked=True,
            ).astype(float)
            values = data.filled(np.nan)
            values[(values <= 0) | ~np.isfinite(values)] = np.nan
            images.append(10 * np.log10(values))
    finite = np.concatenate([x[np.isfinite(x)] for x in images])
    if finite.size == 0:
        raise ValueError("No valid positive backscatter to display")
    low, high = map(float, np.percentile(finite, [2, 98]))
    if high <= low:
        high = low + 1
    rendered = []
    for values in images:
        gray = (np.nan_to_num(np.clip((values - low) / (high - low), 0, 1)) * 255).astype("uint8")
        rendered.append(np.dstack([gray, gray, gray, (np.isfinite(values) * 255).astype("uint8")]))
    return rendered, [low, high]
