"""Build Piura v0.5c products solely from completed cached observations; never contacts CDSE."""

import csv
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.warp import transform_geom

from floodlab.eo_core.context import vector_mask
from floodlab.eo_core.mask_io import export_mask, vectorize
from floodlab.eo_core.pair_jobs import sha256_file, write_json
from floodlab.hazards.flood.engine import to_db
from floodlab.hazards.flood.temporal import (
    AcquisitionSequence,
    TemporalObservation,
    baseline_median,
    observed_inundation,
    temporal_products,
)
from floodlab.impact.engine import analyse_impact

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/cache/openeo/38e5094e-1eb7-48ca-bd66-b2f2d5ae39f4"
LEGACY = ROOT / "data/cache/openeo/1aa75169-0fca-435b-b97e-8abb27a0d86f"
REFERENCE = ROOT / "outputs/analyses/855dc008-898e-42ea-9dba-7aa46ee4b587"


def read_db(path):
    with rasterio.open(path) as src:
        values = src.read(1)
        valid = (src.read_masks(1) > 0) & np.isfinite(values) & (values > 0)
        return to_db(values), valid, src.profile


def polygon(mask, profile):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": transform_geom(profile["crs"], "EPSG:4326", geometry),
                "properties": {},
            }
            for geometry, value in shapes(
                mask.astype("uint8"), mask=mask, transform=profile["transform"]
            )
            if value == 1
        ],
    }


def main():
    plan = json.loads((CACHE / "plan.json").read_text(encoding="utf-8"))
    processing = json.loads((CACHE / "provenance.json").read_text(encoding="utf-8"))
    legacy = json.loads((REFERENCE / "provenance.json").read_text(encoding="utf-8"))
    with rasterio.open(REFERENCE / "land.tif") as src:
        land, profile = src.read(1) == 1, src.profile
    with rasterio.open(REFERENCE / "baseline-classes.tif") as src:
        permanent = np.isin(src.read(1), [2, 3])
    sequence = {
        "ascending": AcquisitionSequence("sentinel-1b", 91, "ascending", "IW", ("VV",)),
        "descending": AcquisitionSequence("sentinel-1", 40, "descending", "IW", ("VV",)),
    }
    entries = []
    cached = {
        "2017-03-11": (
            LEGACY / "earlier.tif",
            {
                "id": "S1B_IW_GRDH_1SDV_20170311T234311_20170311T234336_004667_008247_7495_COG",
                "datetime": "2017-03-11T23:43:11Z",
            },
        ),
        "2017-04-04": (
            LEGACY / "later.tif",
            {
                "id": "S1B_IW_GRDH_1SDV_20170404T234311_20170404T234336_005017_008C6C_B798_COG",
                "datetime": "2017-04-04T23:43:11Z",
            },
        ),
    }
    for index, item in enumerate(plan["observations"], start=1):
        cached[item["datetime"][:10]] = (CACHE / "observations" / f"{index:02d}.tif", item)
    for day in sorted(cached):
        path, item = cached[day]
        values, valid, _ = read_db(path)
        entries.append(
            TemporalObservation(
                item.get("id", f"legacy-{day}"),
                item.get("datetime", day + "T00:00:00Z"),
                sequence[
                    "ascending"
                    if day in {"2017-02-03", "2017-02-27", "2017-03-11", "2017-03-23", "2017-04-04"}
                    else "descending"
                ],
                values,
                valid,
                land,
                permanent,
            )
        )
    by_day = {item.timestamp[:10]: item for item in entries}
    baseline_days = {
        "ascending": ["2017-02-03", "2017-02-27", "2017-03-11"],
        "descending": ["2017-01-19", "2017-02-12", "2017-02-24"],
    }
    baselines = {}
    for name, days in baseline_days.items():
        baselines[name] = baseline_median([by_day[day] for day in days])
    event_days = ["2017-03-20", "2017-03-23", "2017-03-26", "2017-04-04", "2017-04-13"]
    masks, valids, rows = [], [], []
    area = abs(profile["transform"].a * profile["transform"].e) / 10000
    for day in event_days:
        observation = by_day[day]
        stream = (
            "ascending" if observation.sequence.orbit_direction == "ascending" else "descending"
        )
        mask, valid = observed_inundation(observation, *baselines[stream], min_pixels=9)
        masks.append(mask)
        valids.append(valid)
        rows.append(
            {
                "date": day,
                "sequence": stream,
                "platform": "sentinel-1a" if day == "2017-03-26" else "sentinel-1b",
                "observed_inundation_ha": round(float(mask.sum() * area), 2),
                "valid_terrestrial_ha": round(float(valid.sum() * area), 2),
            }
        )
    products = temporal_products([by_day[day] for day in event_days], masks, valids)
    output = ROOT / "outputs/analyses" / str(uuid4())
    output.mkdir(parents=True)
    for name, (base, count) in baselines.items():
        pr = profile.copy()
        pr.update(count=1, dtype="float32", nodata=np.nan, compress="deflate")
        with rasterio.open(output / f"baseline-{name}-db.tif", "w", **pr) as dst:
            dst.write(base.astype("float32"), 1)
    for day, mask, valid in zip(event_days, masks, valids, strict=True):
        export_mask(output / f"observed-inundation-{day}.tif", mask, valid, profile)
        vectorize(
            output / f"observed-inundation-{day}.geojson",
            mask,
            profile["transform"],
            profile["crs"],
            area * 10000,
        )
    for name, values, dtype, nodata in [
        ("maximum-observed-single-date", products["maximum_single_date"], "uint8", 255),
        ("event-observed-temporal-union", products["event_observed_union"], "uint8", 255),
        ("observed-flood-count", products["observed_flood_count"], "uint16", 65535),
        ("valid-observation-count", products["valid_observation_count"], "uint16", 65535),
        ("observation-frequency", products["observed_fraction"], "float32", np.nan),
    ]:
        pr = profile.copy()
        pr.update(count=1, dtype=dtype, nodata=nodata, compress="deflate")
        with rasterio.open(output / f"{name}.tif", "w", **pr) as dst:
            dst.write(values.astype(dtype), 1)
    for name, values in [
        ("maximum-observed-single-date", products["maximum_single_date"]),
        ("event-observed-temporal-union", products["event_observed_union"]),
    ]:
        vectorize(
            output / f"{name}.geojson", values, profile["transform"], profile["crs"], area * 10000
        )
    ref = vector_mask(ROOT / "data/cache/references/indeci-piura2017.geojson", profile)
    comparison = {
        "status": "descriptive only; no accuracy score",
        "temporal_union": {
            "agreement_ha": round(float((products["event_observed_union"] & ref).sum() * area), 2),
            "reference_only_ha": round(
                float((~products["event_observed_union"] & ref & land).sum() * area), 2
            ),
            "satellite_only_ha": round(
                float((products["event_observed_union"] & ~ref).sum() * area), 2
            ),
        },
    }
    land_geometry = polygon(land, profile)
    impact_checks = {}
    for name, values in [
        ("single-date", products["maximum_single_date"]),
        ("maximum", products["maximum_single_date"]),
        ("temporal-union", products["event_observed_union"]),
    ]:
        result = analyse_impact(
            polygon(values, profile),
            plan["aoi"],
            "flood",
            "2017-03-27",
            land=land_geometry,
            resolution=6,
        )
        impact_checks[name] = {
            "compatible": True,
            "hazard_area_m2": result.provenance["totals"]["hazard_area_m2"],
        }
    summary = {
        "status": "DRAFT; experimental observed inundation, not validated flood extent",
        "legacy_pair_ha": legacy["metrics"]["revised_land_only_flood_ha"],
        "baselines": baseline_days,
        "per_date": rows,
        "maximum_observed_single_date": rows[products["maximum_index"]],
        "temporal_union_ha": round(float(products["event_observed_union"].sum() * area), 2),
        "frequency": {
            "once_ha": round(float((products["observed_flood_count"] == 1).sum() * area), 2),
            "repeated_ha": round(float((products["observed_flood_count"] >= 2).sum() * area), 2),
            "not_observed_pixels": int((products["valid_observation_count"] == 0).sum()),
        },
        "indeci": comparison,
        "impact_contract": impact_checks,
        "s2": legacy.get("optical", {}),
        "limitations": [
            "Ascending and descending sequences are classified separately; their masks are unioned only as event observations.",
            "March 26 S1A/S1B comparability QC is documented separately; no empirical correction was applied.",
            "OpenEO source identity is expected catalogue identity, not backend-verified lineage.",
        ],
    }
    with (output / "temporal-summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    write_json(output / "temporal-summary.json", summary)
    write_json(
        output / "provenance.json",
        {
            "created_utc": datetime.now(UTC).isoformat(),
            "analysis_id": output.name,
            "processing_plan": str(CACHE / "plan.json"),
            "processing_provenance": str(CACHE / "provenance.json"),
            "configuration": {
                "water_db": -18,
                "drop_db": -3,
                "min_pixels": 9,
                "land_mask": "v0.4 preserved",
                "permanent_water": "v0.4 baseline classes 2/3 preserved",
            },
            "summary": summary,
            "source_checksums": {
                key: value["sha256"] for key, value in processing["outputs"].items()
            },
        },
    )
    (output / "REPORT.md").write_text(
        "# Piura v0.5c temporal reconstruction\n\n" + json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    checks = {
        p.relative_to(output).as_posix(): sha256_file(p) for p in output.rglob("*") if p.is_file()
    }
    write_json(output / "checksums.json", checks)
    with zipfile.ZipFile(output / "analysis.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for path in output.rglob("*"):
            if path.is_file() and path.name != "analysis.zip":
                archive.write(path, path.relative_to(output))
    print(output)


if __name__ == "__main__":
    main()
