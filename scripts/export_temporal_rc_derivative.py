"""Create a provenance-linked RC correction for aggregate temporal raster semantics."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import rasterio

from floodlab.eo_core.integrity import sha256_file
from floodlab.eo_core.pair_jobs import write_json
from floodlab.hazards.flood.temporal_export import binary_export_values, count_export_values

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outputs/analyses/3bb5d30e-d3bf-46db-a55c-6c746847d558"


def _read(name):
    with rasterio.open(SOURCE / name) as src:
        values = src.read(1)
        return values, src.profile.copy()


def _write(path, values, profile, dtype, nodata):
    profile.update(count=1, dtype=dtype, nodata=nodata, compress="deflate")
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(values.astype(dtype), 1)


def main():
    valid_count, profile = _read("valid-observation-count.tif")
    union, _ = _read("event-observed-temporal-union.tif")
    maximum, _ = _read("maximum-observed-single-date.tif")
    flood_count, _ = _read("observed-flood-count.tif")
    selected, _ = _read("observed-inundation-2017-03-26.tif")
    valid_any = valid_count > 0
    selected_valid = selected != 255
    output = ROOT / "outputs/analyses" / f"{uuid4()}-rc-temporal-nodata"
    output.mkdir(parents=True)
    _write(output / "event-observed-temporal-union.tif", binary_export_values(union == 1, valid_any), profile, "uint8", 255)
    _write(output / "maximum-observed-single-date.tif", binary_export_values(maximum == 1, selected_valid), profile, "uint8", 255)
    _write(output / "observed-flood-count.tif", count_export_values(flood_count, valid_any), profile, "uint16", 65535)
    _write(output / "valid-observation-count.tif", count_export_values(valid_count, valid_any), profile, "uint16", 65535)
    provenance = {
        "status": "DRAFT RC derivative; export-semantics correction only",
        "created_utc": datetime.now(UTC).isoformat(),
        "derived_from_frozen_analysis": str(SOURCE.relative_to(ROOT)),
        "source_checksums": {name: sha256_file(SOURCE / name) for name in ["event-observed-temporal-union.tif", "maximum-observed-single-date.tif", "valid-observation-count.tif", "observed-flood-count.tif", "observed-inundation-2017-03-26.tif"]},
        "semantics": {"1": "classified inundated", "0": "observed usable and not classified inundated", "255": "NOT OBSERVED / invalid"},
        "area_effect": "No change: source boolean classification masks, authoritative areas, H3 products and impact packages are not recomputed or overwritten.",
    }
    write_json(output / "provenance.json", provenance)
    write_json(output / "checksums.json", {p.name: sha256_file(p) for p in output.iterdir() if p.is_file()})
    print(output)


if __name__ == "__main__":
    main()
