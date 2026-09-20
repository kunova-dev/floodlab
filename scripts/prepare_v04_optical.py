"""Retrieve optional S2 water evidence through public COG assets, without credentials."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from shapely.geometry import box, shape

from floodlab.eo_core.pair_jobs import sha256_file, write_json
from floodlab.eo_core.public_stac import cached_search
from floodlab.hazards.flood.evidence import optical_water

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/cache/v04"


def main():
    cfg = json.loads((ROOT / "config/v04.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    inventory = cached_search(
        OUT / "sentinel-2-l2a-search.json",
        "sentinel-2-l2a",
        cfg["bbox"],
        cfg["s2_before_window"][0] + "T00:00:00Z/" + cfg["s2_event_window"][1] + "T23:59:59Z",
    )
    if any(x.get("rel") == "next" for x in inventory.get("links", [])):
        raise ValueError("Optical inventory is truncated")
    with rasterio.open(ROOT / cfg["reference_grid"]) as src:
        profile = src.profile.copy()
    report = {
        "status": "insufficient",
        "provider": "Earth Search / public Sentinel-2 L2A COGs",
        "retrieved_utc": datetime.now(UTC).isoformat(),
        "search_sha256": sha256_file(OUT / "sentinel-2-l2a-search.json"),
        "method": "MNDWI > 0 on SCL classes 4/5/6, cloud/shadow/defect/snow excluded with 60 m buffer",
        "threshold": cfg["optical_mndwi"],
        "periods": {},
        "errors": [],
        "limitations": "March 31 optical and April 4 SAR are not simultaneous. Atmospheric correction/cloud masks imperfect; disagreement can be temporal. Public L2A reprocessing product IDs retained.",
    }
    for role, window in [("before", cfg["s2_before_window"]), ("during", cfg["s2_event_window"])]:
        items = [
            f
            for f in inventory["features"]
            if window[0] <= f["properties"]["datetime"][:10] <= window[1]
            and shape(f["geometry"]).intersects(box(*cfg["bbox"]))
        ]
        if not items:
            report["periods"][role] = {"status": "unavailable"}
            continue
        dates = sorted({f["properties"]["datetime"][:10] for f in items})
        date = min(
            dates,
            key=lambda d: np.mean(
                [
                    f["properties"]["eo:cloud_cover"]
                    for f in items
                    if f["properties"]["datetime"].startswith(d)
                ]
            ),
        )
        selected = [f for f in items if f["properties"]["datetime"].startswith(date)]
        water = np.zeros((profile["height"], profile["width"]), bool)
        valid = water.copy()
        records = []
        for item in selected:
            try:
                bands = {}
                with rasterio.Env(
                    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                    GDAL_HTTP_TIMEOUT="45",
                    GDAL_HTTP_MAX_RETRY="2",
                ):
                    for key in ["green", "swir16", "scl"]:
                        asset = item["assets"][key]
                        with (
                            rasterio.open(asset["href"]) as src,
                            WarpedVRT(
                                src,
                                crs=profile["crs"],
                                transform=profile["transform"],
                                width=profile["width"],
                                height=profile["height"],
                                resampling=Resampling.nearest
                                if key == "scl"
                                else Resampling.bilinear,
                                nodata=0,
                            ) as vrt,
                        ):
                            raw = vrt.read(1)
                        spec = asset.get("raster:bands", [{}])[0]
                        bands[key] = (
                            raw
                            if key == "scl"
                            else np.where(
                                raw > 0,
                                raw.astype("float32") * spec.get("scale", 0.0001)
                                + spec.get("offset", 0),
                                np.nan,
                            )
                        )
                w, v = optical_water(
                    bands["green"],
                    bands["swir16"],
                    bands["scl"],
                    cfg["optical_mndwi"],
                    round(cfg["optical_cloud_buffer_m"] / abs(profile["transform"].a)),
                )
                take = v & ~valid
                water[take] = w[take]
                valid |= v
                records.append(
                    {
                        "id": item["id"],
                        "product_id": item["properties"].get("s2:product_uri"),
                        "datetime": item["properties"]["datetime"],
                        "cloud_percent": item["properties"]["eo:cloud_cover"],
                        "valid_grid_pixels": int(v.sum()),
                        "assets": {k: item["assets"][k] for k in ["green", "swir16", "scl"]},
                    }
                )
                print(role, item["id"], int(v.sum()), flush=True)
            except (OSError, ValueError, KeyError, rasterio.errors.RasterioError) as exc:
                report["errors"].append({"id": item["id"], "error_type": type(exc).__name__})
        path = OUT / f"s2-{role}.tif"
        pr = profile.copy()
        pr.update(count=1, dtype="uint8", nodata=255, compress="deflate")
        with rasterio.open(path, "w", **pr) as dst:
            dst.write(np.where(valid, water, 255).astype("uint8"), 1)
        report["periods"][role] = {
            "date": date,
            "status": "available" if valid.any() else "unavailable",
            "file": path.name,
            "sha256": sha256_file(path),
            "scenes": records,
            "valid_grid_pixels": int(valid.sum()),
        }
    report["status"] = (
        "available"
        if all(
            report["periods"].get(r, {}).get("status") == "available" for r in ["before", "during"]
        )
        else "insufficient"
    )
    write_json(OUT / "optical.json", report)


if __name__ == "__main__":
    main()
