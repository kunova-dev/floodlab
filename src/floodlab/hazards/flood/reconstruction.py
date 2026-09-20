"""v0.4 terrestrial multi-evidence reconstruction; v0.3 retained as comparison."""

import csv
import json
import shutil
import zipfile
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

import numpy as np
import rasterio
from PIL import Image, ImageDraw
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from scipy.ndimage import distance_transform_edt
from shapely.geometry import box

from floodlab import __version__
from floodlab.eo_core.context import aligned, read_sources, vector_mask
from floodlab.eo_core.gauges import validate_gauge_observations
from floodlab.eo_core.mask_io import export_mask, preview, vectorize
from floodlab.eo_core.pair_jobs import sha256_file, write_json

from .engine import cleanup, to_db, water_mask
from .event import compare_reference
from .evidence import baseline_classes, evidence_classes
from .workflow import analyse_event

CLASSES = {
    0: "No new flood evidence on historically non-water land",
    1: "S1 + S2 supporting evidence (dates differ)",
    2: "S1 evidence; S2 unavailable",
    3: "S1 evidence; S2 disagreement (dates differ)",
    4: "S2 evidence without corresponding S1 evidence",
    5: "Historical persistent/recurrent water",
    6: "Ocean excluded",
    7: "Uncertain baseline or invalid observation",
}


def reconstruct(root, aoi, event):
    settings = json.loads((root / "config/v04.json").read_text(encoding="utf-8"))
    if len(set(settings["baseline_years"])) < 2 or any(
        not isinstance(y, int) for y in settings["baseline_years"]
    ):
        raise ValueError("At least two distinct historical baseline years are required")
    if (
        not all(np.isfinite(settings[k]) for k in ["sar_water_db", "sar_drop_db"])
        or settings["sar_drop_db"] >= 0
    ):
        raise ValueError("Invalid finite SAR thresholds")
    if type(settings["min_pixels"]) is not int or settings["min_pixels"] < 1:
        raise ValueError("Invalid component cleanup size")
    if (
        settings["optical_max_pair_days"] < 0
        or not 0 <= settings["optical_min_usable_fraction"] <= 1
    ):
        raise ValueError("Invalid optical pairing parameters")
    folder = root / "data/cache/v04"
    sources = read_sources(folder, settings["baseline_years"])
    if not box(*settings["bbox"]).buffer(1e-8).covers(aoi.geometry):
        raise ValueError("AOI exceeds prepared scientific context; prepare matching context first")
    if any(year >= int(event["before_end"][:4]) for year in settings["baseline_years"]):
        raise ValueError("Historical baseline must precede the event year")
    legacy_path = analyse_event(root, aoi, event)
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    inputs = [root / name for name in legacy["input_rasters"]]
    with rasterio.open(inputs[0]) as src, rasterio.open(inputs[1]) as other:
        profile = src.profile.copy()
        a = src.read(1, masked=True)
        b = other.read(1, masked=True)
    inside = geometry_mask(
        [transform_geom("EPSG:4326", profile["crs"], aoi.geojson()["geometry"])],
        out_shape=a.shape,
        transform=profile["transform"],
        invert=True,
    )
    land = vector_mask(folder / sources["land"]["file"], profile) & inside
    rawvalid = (
        inside
        & ~np.ma.getmaskarray(a)
        & ~np.ma.getmaskarray(b)
        & np.isfinite(a.data)
        & np.isfinite(b.data)
        & (a.data > 0)
        & (b.data > 0)
    )
    valid = rawvalid & land
    if not land.any() or valid.sum() / land.sum() < 0.8:
        raise ValueError("Insufficient valid terrestrial coverage")
    history = [
        aligned(folder / sources[f"water-{year}"]["file"], profile).filled(0)
        for year in settings["baseline_years"]
    ]
    occurrence = (
        aligned(folder / sources["occurrence"]["file"], profile).filled(255)
        if "occurrence" in sources
        else None
    )
    baseline = baseline_classes(history, land, occurrence)
    before = valid & water_mask(to_db(a.data), settings["sar_water_db"])
    during = valid & water_mask(to_db(b.data), settings["sar_water_db"])
    delta = to_db(b.data) - to_db(a.data)
    unclean = during & ~before & (delta <= settings["sar_drop_db"])
    s1 = cleanup(unclean, settings["min_pixels"])
    final = cleanup(unclean & (baseline == 1), settings["min_pixels"])
    area = abs(profile["transform"].a * profile["transform"].e)
    ha = lambda m: round(float(np.count_nonzero(m) * area / 10000), 6)
    with rasterio.open(legacy_path.parent / "flood.tif") as src:
        old = src.read(1) == 1
    optical = {
        "status": "Sentinel-2 evidence unavailable/insufficient",
        "reason": "No verified optical product",
    }
    s2 = None
    s2valid = None
    s2during = np.zeros_like(valid)
    s2during_valid = np.zeros_like(valid)
    if (folder / "optical.json").exists():
        try:
            optical = json.loads((folder / "optical.json").read_text(encoding="utf-8"))
            arrays = []
            for role in ["before", "during"]:
                item = optical["periods"][role]
                path = folder / item["file"]
                if (
                    not path.resolve().is_relative_to(folder.resolve())
                    or sha256_file(path) != item["sha256"]
                ):
                    raise ValueError("Optical integrity failure")
                arrays.append(aligned(path, profile).filled(255))
            s2valid = (arrays[0] != 255) & (arrays[1] != 255) & valid
            s2 = (arrays[1] == 1) & (arrays[0] == 0) & s2valid
            s2during_valid = (arrays[1] != 255) & land
            s2during = (arrays[1] == 1) & s2during_valid
            optical["usable_terrestrial_pair_fraction"] = float(s2valid.sum() / land.sum())
            optical["usable_pair_ha"] = ha(s2valid)
            optical["during_usable_ha"] = ha(s2during_valid)
            optical["during_water_ha"] = ha(s2during)
            optical["during_excluded_ha"] = ha(land & ~s2during_valid)
            gap = abs(
                (
                    datetime.fromisoformat(optical["periods"]["during"]["date"])
                    - datetime.fromisoformat(legacy["selection"]["during"]["datetime"][:10])
                ).days
            )
            optical["s1_s2_gap_days"] = gap
            if gap > settings["optical_max_pair_days"]:
                s2valid[:] = False
                optical["status"] = (
                    "Sentinel-2 evidence unavailable/insufficient for temporal pairing"
                )
            elif s2valid.any():
                optical["status"] = (
                    "Limited clear-pixel evidence; insufficient AOI-wide optical coverage"
                    if optical["usable_terrestrial_pair_fraction"]
                    < settings["optical_min_usable_fraction"]
                    else "Available on cloud-screened common pixels; temporally unmatched observations"
                )
            else:
                optical["status"] = "Sentinel-2 evidence unavailable/insufficient"
        except (OSError, ValueError, KeyError, TypeError, rasterio.errors.RasterioError) as exc:
            optical = {
                "status": "Sentinel-2 evidence unavailable/insufficient",
                "reason": type(exc).__name__,
            }
            s2 = None
            s2valid = None
            s2during[:] = False
            s2during_valid[:] = False
    evidence = evidence_classes(final, baseline, valid, s2, s2valid)
    output = root / "outputs/analyses" / str(uuid4())
    output.mkdir(parents=True, exist_ok=False)

    def mask(name, data, domain=valid, color=(244, 77, 40, 210)):
        values = export_mask(output / f"{name}.tif", data, domain, profile)
        return preview(output / f"{name}.png", values, profile, color)

    bounds = mask("flood", final)
    mask("s1-evidence", s1)
    mask("before", before, color=(35, 115, 215, 180))
    mask("during", during, color=(20, 160, 205, 180))
    mask("land", land, inside)
    mask("baseline-water", np.isin(baseline, [2, 3]), land, color=(60, 85, 190, 185))
    mask("baseline-uncertain", baseline == 4, land, color=(140, 140, 140, 160))
    mask("s1-uncertain-baseline", s1 & (baseline == 4), valid)
    mask(
        "s2-evidence",
        np.zeros_like(valid) if s2 is None else s2,
        np.zeros_like(valid) if s2valid is None else s2valid,
        color=(95, 55, 200, 190),
    )
    mask("s2-water", s2during, s2during_valid, color=(30, 150, 190, 180))
    for name, values in [("baseline-classes", baseline), ("evidence-agreement", evidence)]:
        pr = profile.copy()
        pr.update(count=1, dtype="uint8", nodata=255, compress="deflate")
        with rasterio.open(output / f"{name}.tif", "w", **pr) as dst:
            dst.write(np.where(inside, values, 255).astype("uint8"), 1)
    for code in [1, 2, 3, 4]:
        mask(
            f"evidence-{code}",
            evidence == code,
            inside,
            color={
                1: (45, 160, 80, 200),
                2: (244, 150, 40, 200),
                3: (200, 45, 70, 200),
                4: (130, 70, 210, 200),
            }[code],
        )
    polygon_count = vectorize(
        output / "flood.geojson", final, profile["transform"], profile["crs"], area
    )
    comparison = {"status": "Reference unavailable", "accuracy_metrics": None}
    refpath = root / "data/cache/references/indeci-piura2017.geojson"
    if refpath.exists():
        # Match v0.3's repair/clip-before-projection convention for comparability.
        ref = vector_mask(refpath, profile, aoi.geometry)
        layers = compare_reference(final, ref, valid)
        for name, m in layers.items():
            mask(
                name,
                m,
                color={
                    "agreement": (45, 160, 80, 200),
                    "possible_omission": (150, 70, 200, 180),
                    "possible_commission": (250, 150, 30, 200),
                }[name],
            )
        omission = layers["possible_omission"]
        # Mutually exclusive attribution sequence, not established physical causes.
        buckets = {}
        remaining = omission.copy()
        for label, test in [
            ("historical_water", np.isin(baseline, [2, 3])),
            ("uncertain_baseline", baseline == 4),
            ("water_already_on_earlier_date", before),
            ("not_dark_on_later_date", ~during),
            ("insufficient_drop", delta > settings["sar_drop_db"]),
        ]:
            take = remaining & test
            buckets[label] = ha(take)
            remaining &= ~take
        buckets["cleanup_or_remaining"] = ha(remaining)
        comparison = {
            "status": "Descriptive differences on valid land; timing/completeness unknown",
            "areas_ha": {k: ha(m) for k, m in layers.items()},
            "reference_sha256": sha256_file(refpath),
            "reference": legacy["comparison"].get("reference"),
            "accuracy_metrics": None,
            "possible_omission_breakdown_ha": buckets,
            "reference_offshore_ha": ha(ref & inside & ~land),
            "limitations": "Buckets describe classification conditions, not proven causes. Vegetation, urban scattering, shallow water and reference timing cannot be attributed from two SAR images alone.",
        }
    context = {}
    if "rivers" in sources:
        riverpath = folder / sources["rivers"]["file"]
        river = vector_mask(riverpath, profile)
        distance = distance_transform_edt(
            ~river, sampling=(abs(profile["transform"].e), profile["transform"].a)
        )
        context["river_distance_m"] = {
            "median": float(np.median(distance[final])) if final.any() and river.any() else None,
            "p90": float(np.percentile(distance[final], 90))
            if final.any() and river.any()
            else None,
            "interpretation": "Distance to mapped local reaches only; not a flood filter or proof of connection.",
        }
        shutil.copyfile(riverpath, output / "rivers.geojson")
    if "dem" in sources:
        dem = (
            aligned(folder / sources["dem"]["file"], profile, False)
            .filled(np.nan)
            .astype("float32")
        )
        y, x = np.gradient(dem, abs(profile["transform"].e), profile["transform"].a)
        slope = np.degrees(np.arctan(np.hypot(x, y)))
        for name, values in [("dem", dem), ("slope", slope)]:
            pr = profile.copy()
            pr.update(count=1, dtype="float32", nodata=np.nan, compress="deflate")
            with rasterio.open(output / f"{name}.tif", "w", **pr) as dst:
                dst.write(np.where(land, values, np.nan).astype("float32"), 1)
        context["terrain"] = {
            "flood_elevation_median_m": float(np.nanmedian(dem[final])) if final.any() else None,
            "flood_slope_median_degrees": float(np.nanmedian(slope[final]))
            if final.any()
            else None,
            "limitation": "DSM context only. No HAND, flow routing or terrain exclusions.",
        }
    try:
        gauges = json.loads((root / "config/piura-gauges.json").read_text(encoding="utf-8"))
        validate_gauge_observations(gauges.get("observations", []))
    except (OSError, ValueError, TypeError, KeyError):
        gauges = {
            "status": "unavailable",
            "observations": [],
            "reason": "No usable, provenance-complete local gauge observations",
        }
    sensitivity = []
    for t in [-20.0, -18.0, -16.0]:
        for drop in [-2.0, -3.0, -4.0]:
            candidate = (
                valid
                & (baseline == 1)
                & water_mask(to_db(b.data), t)
                & ~water_mask(to_db(a.data), t)
                & (delta <= drop)
            )
            sensitivity.append(
                {
                    "water_db": t,
                    "drop_db": drop,
                    "area_ha": ha(cleanup(candidate, settings["min_pixels"])),
                }
            )
    assert not (final & ~land).any()
    metrics = {
        "total_aoi_ha": ha(inside),
        "terrestrial_aoi_ha": ha(land),
        "ocean_excluded_ha": ha(inside & ~land),
        "v03_flood_ha": ha(old),
        "v03_offshore_flood_ha": ha(old & inside & ~land),
        "land_only_s1_candidate_ha": ha(s1),
        "coastline_cleanup_additional_ha": round(ha(old & land) - ha(s1), 6),
        "baseline_cleanup_additional_ha": round(ha(s1 & (baseline == 1)) - ha(final), 6),
        "revised_land_only_flood_ha": ha(final),
        "historical_water_s1_candidates_ha": ha(s1 & np.isin(baseline, [2, 3])),
        "uncertain_baseline_s1_candidates_ha": ha(s1 & (baseline == 4)),
        "during_water_already_observed_before_ha": ha(during & before),
        "during_water_on_historical_water_ha": ha(during & np.isin(baseline, [2, 3])),
        "before_water_ha": ha(before),
        "during_water_ha": ha(during),
        "valid_land_fraction": float(valid.sum() / land.sum()),
        "ocean_flood_pixels": int((final & ~land).sum()),
    }
    if refpath.exists():
        omitted = layers["possible_omission"]
        rows, cols = np.indices(omitted.shape)
        comparison["possible_omission_quadrants_ha"] = {
            label: ha(omitted & part)
            for label, part in [
                ("northwest", (rows < omitted.shape[0] / 2) & (cols < omitted.shape[1] / 2)),
                ("northeast", (rows < omitted.shape[0] / 2) & (cols >= omitted.shape[1] / 2)),
                ("southwest", (rows >= omitted.shape[0] / 2) & (cols < omitted.shape[1] / 2)),
                ("southeast", (rows >= omitted.shape[0] / 2) & (cols >= omitted.shape[1] / 2)),
            ]
        }
        comparison["quadrants_definition"] = (
            "Grid midpoint split in EPSG:32717; descriptive location only"
        )
        if "dem" in sources and omitted.any():
            comparison["omission_median_elevation_m"] = float(np.nanmedian(dem[omitted]))
            comparison["omission_median_slope_degrees"] = float(np.nanmedian(slope[omitted]))
        if "rivers" in sources and river.any() and omitted.any():
            comparison["omission_median_river_distance_m"] = float(np.median(distance[omitted]))
    timeline = (
        [
            {
                "sensor": "S1",
                "datetime": x["datetime"],
                "role": "catalogue observation, not processed peak evidence",
            }
            for x in json.loads((root / "data/cache/openeo/pair-candidates.json").read_text())[
                "acquisitions"
            ]
        ]
        if (root / "data/cache/openeo/pair-candidates.json").exists()
        else []
    )
    for item in timeline:
        for role in ["before", "during"]:
            selected = legacy.get("selection", {}).get(role, {})
            if item["datetime"] == selected.get("datetime"):
                item["role"] = (
                    "processed earlier observation, not normal-water proof"
                    if role == "before"
                    else "processed continuing/residual inundation, not peak"
                )
    if event.get("event_date"):
        timeline.append(
            {
                "sensor": "Event chronology",
                "datetime": event["event_date"],
                "role": "documented escalation; no satellite peak extent established",
            }
        )
    for role, p in optical.get("periods", {}).items():
        if p.get("date"):
            timeline.append(
                {
                    "sensor": "S2",
                    "datetime": p["date"],
                    "role": role + " cloud-screened optical observation",
                }
            )
    report = {
        **legacy,
        "analysis_id": output.name,
        "aoi_sha256": sha256(json.dumps(aoi.geojson(), sort_keys=True).encode()).hexdigest(),
        "grid": {
            "crs": str(profile["crs"]),
            "transform": list(profile["transform"]),
            "width": profile["width"],
            "height": profile["height"],
            "pixel_area_m2": area,
        },
        "before_water_ha": ha(before),
        "during_water_ha": ha(during),
        "version": __version__,
        "created_utc": datetime.now(UTC).isoformat(),
        "status": "DRAFT",
        "sources": sources,
        "settings": settings,
        "metrics": metrics,
        "probable_flooded_area_ha": ha(final),
        "coverage_fraction": metrics["valid_land_fraction"],
        "comparison": comparison,
        "optical": optical,
        "context": context,
        "gauges": gauges,
        "timeline": sorted(timeline, key=lambda x: x["datetime"]),
        "baseline": {
            "years": settings["baseline_years"],
            "classes": {
                0: "ocean",
                1: "historically non-water (all annual maps or explicit pre-event occurrence=0)",
                2: "seasonal/recurrent water in any year",
                3: "persistent water in all configured annual maps",
                4: "uncertain/incomplete history",
            },
            "areas_ha": {str(c): ha(inside & (baseline == c)) for c in range(5)},
            "limitation": "Historical annual water classification, not a March climatology or multi-date SAR backscatter baseline; 2016-early2017 change remains possible.",
        },
        "evidence_classes": CLASSES,
        "evidence_area_ha": {str(c): ha(inside & (evidence == c)) for c in CLASSES},
        "sensitivity_area_ha": sensitivity,
        "bounds": bounds,
        "polygon_count": polygon_count,
        "v03_comparison_provenance": str(legacy_path.relative_to(root)),
        "output_sha256": {},
        "scientific_layers": {
            "observation": "Recorded S1 backscatter and cloud-screened S2 reflectance",
            "classification": "SAR change and MNDWI masks",
            "context": "Historical water, coastline, rivers, DSM and gauge discovery",
            "interpretation": "Experimental new inundation over historically non-water land",
        },
        "limitations": legacy.get("limitations", [])
        + [
            "Coastline is historical; zero ocean pixels is relative to GSHHG, not perfect coastline truth.",
            "Seasonal-water expansion and unknown-baseline candidates remain separate; conservative headline excludes them.",
            "No gauge hydrograph, validated accuracy, peak extent or calibrated probability is claimed.",
        ],
    }
    # Package a reusable context extract, source metadata and auditable tabular summaries.
    context_output = output / "context_sources"
    context_output.mkdir()
    for entry in sources.values():
        shutil.copyfile(folder / entry["file"], context_output / entry["file"])
    for name in ["optical.json", "sentinel-2-l2a-search.json", "s2-before.tif", "s2-during.tif"]:
        if (folder / name).exists():
            shutil.copyfile(folder / name, context_output / name)
    report["method"] = {
        **legacy["method"],
        "land_domain": "GSHHG L1 pixel-center rasterization; inland lakes retained",
        "baseline_rule": "Final candidates require class 1 (non-water in every configured pre-event annual map, or explicit 1984-2015 occurrence=0 where annual history is incomplete)",
        "sensitivity": sensitivity,
        "source_lineage_warning": "Requested Sentinel-1 product IDs are retained; backend input product identity was not independently verified.",
    }
    report["confidence"] = "EXPERIMENTAL LAND-ONLY ESTIMATE — REQUIRES VALIDATION"
    report["input_sha256"] = {str(p.relative_to(root)): sha256_file(p) for p in inputs}
    timeline.extend(
        [
            {"sensor": "Historical water", "datetime": str(y), "role": "pre-event annual baseline"}
            for y in settings["baseline_years"]
        ]
    )
    report["timeline"] = sorted(timeline, key=lambda x: x["datetime"])

    (output / "README.md").write_text(
        "# FloodLab experimental scientific product\n\nBinary layers: 0 = no detection within usable domain, 1 = detection, 255 = excluded/unknown. Ocean is excluded from every terrestrial water/flood layer. Baseline/evidence categorical codes are in provenance.json. All derived GeoTIFFs share the recorded metric grid; GeoJSON is WGS84. PNGs are geographic mask previews, not true-colour imagery. context_sources contains native source extracts and their original checksums. source raster URLs and input hashes allow reproduction but the large original SAR rasters are retained in the local processing cache, not duplicated here. checksums.json covers every other package payload except itself; ZIP checksum is recorded separately by validation. This analysis directory is append-only by convention and never overwritten by FloodLab; filesystem permissions do not enforce archival immutability.\n",
        encoding="utf-8",
    )
    write_json(output / "sources.json", sources)
    write_json(output / "gauges.json", gauges)
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        writer.writerows(metrics.items())
    images = [
        Image.open(output / f"{n}.png").convert("RGBA") for n in ["before", "during", "flood"]
    ]
    canvas = Image.new("RGB", (images[0].width * 3, images[0].height + 40), "white")
    draw = ImageDraw.Draw(canvas)
    for i, (im, label) in enumerate(
        zip(images, ["Earlier observation", "During observation", "Land-only probable inundation"])
    ):
        canvas.paste(im, (i * im.width, 40), im)
        draw.text((i * im.width + 10, 10), label, fill="black")
    canvas.save(output / "comparison.png")
    (output / "methodology.md").write_text(
        "# Experimental land-only reconstruction\n\nNo statistical accuracy claim. See provenance.json for all assumptions, thresholds, input hashes and reference limitations.\n\n"
        + json.dumps(
            {
                "metrics": metrics,
                "baseline": report["baseline"],
                "optical_status": optical["status"],
                "comparison": comparison,
                "sensitivity": sensitivity,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    vector = json.loads((output / "flood.geojson").read_text())
    vector_area = sum(f["properties"]["area_ha"] for f in vector["features"])
    if abs(vector_area - ha(final)) > area / 10000:
        raise ValueError("Raster/vector area mismatch")
    report["checks"] = {
        "zero_ocean_flood_pixels": True,
        "vector_area_ha": vector_area,
        "area_tolerance_ha": area / 10000,
    }
    report["output_sha256"] = {
        p.relative_to(output).as_posix(): sha256_file(p) for p in output.rglob("*") if p.is_file()
    }
    write_json(output / "provenance.json", report)
    checks = {
        p.relative_to(output).as_posix(): sha256_file(p) for p in output.rglob("*") if p.is_file()
    }
    write_json(output / "checksums.json", checks)
    with zipfile.ZipFile(output / "analysis.zip", "x", zipfile.ZIP_DEFLATED) as archive:
        for p in output.rglob("*"):
            if p.is_file() and p.name != "analysis.zip":
                archive.write(p, p.relative_to(output).as_posix())
    return output / "provenance.json"
