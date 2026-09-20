"""Fetch and clip public scientific context; no credentials or processing jobs."""

import json
import math
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import rasterio
import requests
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import box

from floodlab.eo_core.pair_jobs import sha256_file, write_json
from floodlab.eo_core.public_stac import cached_search

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/cache/v04"
OUT.mkdir(parents=True, exist_ok=True)
CFG = json.loads((ROOT / "config/v04.json").read_text())
BBOX = CFG["bbox"]
MANIFEST = {}


def download(url, name):
    path = OUT / name
    if not path.exists():
        with requests.get(url, stream=True, timeout=120) as response:
            response.raise_for_status()
            with path.with_suffix(".partial").open("wb") as stream:
                for chunk in response.iter_content(1024 * 1024):
                    stream.write(chunk)
        path.with_suffix(".partial").replace(path)
    return path


def record(name, path, url, **extra):
    MANIFEST[name] = {
        "file": path.name,
        "url": url,
        "sha256": sha256_file(path),
        "retrieved_utc": datetime.now(UTC).isoformat(),
        **extra,
    }


def crop(url, path):
    if not path.exists():
        with rasterio.open(url) as src:
            bounds = transform_bounds("EPSG:4326", src.crs, *BBOX)
            if not (
                src.bounds.left <= bounds[0]
                and src.bounds.bottom <= bounds[1]
                and src.bounds.right >= bounds[2]
                and src.bounds.top >= bounds[3]
            ):
                raise ValueError("AOI crosses source tiles; prepare a mosaic before extraction")
            window = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
            data = src.read(window=window)
            profile = src.profile.copy()
            profile.update(
                width=data.shape[2],
                height=data.shape[1],
                transform=src.window_transform(window),
                compress="deflate",
                driver="GTiff",
            )
            with rasterio.open(path, "w", **profile) as dst:
                dst.write(data)
    return path


def main():
    coasturl = "https://github.com/GenericMappingTools/gshhg-gmt/releases/download/2.3.7/gshhg-shp-2.3.7.zip"
    coast = download(coasturl, "gshhg-shp-2.3.7.zip")
    assert sha256_file(coast) == "8dbbe7e071e77e9e75f2d639239099ebca8d5c16d6a07df8169729d49f15cf41"
    frame = gpd.read_file(
        f"/vsizip/{coast.as_posix()}/GSHHS_shp/f/GSHHS_f_L1.shp", bbox=tuple(BBOX)
    )
    frame.geometry = frame.geometry.intersection(box(*BBOX))
    land = OUT / "land.geojson"
    frame.to_file(land, driver="GeoJSON")
    record(
        "land",
        land,
        coasturl,
        version="2.3.7 full L1",
        archive_sha256=sha256_file(coast),
        license="LGPL",
        limitations="Historical shoreline; full resolution is not 20 m positional accuracy. Coastal change/tides remain uncertain; inland waters remain inside land domain.",
    )
    print("Land extracted", flush=True)
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        GDAL_HTTP_TIMEOUT="60",
        AWS_NO_SIGN_REQUEST="YES",
    ):
        base = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GSWE/YearlyClassification/VER1-0/tiles/"
        with rasterio.open(
            base + "yearlyClassification2015/yearlyClassification2015-0000000000-0000000000.tif"
        ) as first:
            row, col = first.index((BBOX[0] + BBOX[2]) / 2, (BBOX[1] + BBOX[3]) / 2)
            row = (row // 40000) * 40000
            col = (col // 40000) * 40000
        for year in CFG["baseline_years"]:
            url = (
                base
                + f"yearlyClassification{year}/yearlyClassification{year}-{row:010d}-{col:010d}.tif"
            )
            path = crop(url, OUT / f"water-{year}.tif")
            with rasterio.open(path) as src:
                if not (src.bounds.left <= BBOX[0] and src.bounds.right >= BBOX[2] - 0.001):
                    raise ValueError("Baseline tile misses AOI")
            record(
                f"water-{year}",
                path,
                url,
                year=year,
                version="VER1-0",
                license="Copernicus open data; EC JRC/Google",
                classes={"0": "no data", "1": "not water", "2": "seasonal", "3": "permanent"},
                resampling="nearest",
                limitations="Annual classifications do not prove seasonal dry conditions in 2017; 30 m native resolution.",
            )
            print("Baseline", year, flush=True)
        west = math.floor(BBOX[0] / 10) * 10
        north = math.ceil(BBOX[3] / 10) * 10
        lon = f"{abs(west)}{'W' if west < 0 else 'E'}"
        lat = f"{abs(north)}{'S' if north < 0 else 'N'}"
        occurrence_url = f"https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GSWE/Aggregated/VER1-0/occurrence/tiles/occurrence_{lon}_{lat}.tif"
        occurrence = crop(occurrence_url, OUT / "occurrence-1984-2015.tif")
        record(
            "occurrence",
            occurrence,
            occurrence_url,
            version="VER1-0 1984-2015",
            license="Copernicus open data; EC JRC/Google",
            classes={"0": "not water", "1-100": "percent occurrence", "255": "no data"},
            limitations="Used only to resolve history gaps where explicitly mapped not-water (0); unknown remains unknown. Positive occurrence alone does not establish seasonal/permanent water.",
        )
        demitems = cached_search(OUT / "cop-dem-glo-30-search.json", "cop-dem-glo-30", BBOX)[
            "features"
        ]
        demurl = demitems[0]["assets"]["data"]["href"]
        dem = crop(demurl, OUT / "dem.tif")
        record(
            "dem",
            dem,
            demurl,
            product=demitems[0]["id"],
            version="Copernicus GLO-30",
            license="Copernicus DEM licence",
            limitations="DSM, not bare-earth terrain; context only, no HAND or elevation exclusion.",
        )
    url = "https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_sa_shp.zip"
    archive = download(url, "hydrorivers.zip")
    with zipfile.ZipFile(archive) as z:
        shp = next(n for n in z.namelist() if n.endswith(".shp"))
    rivers = gpd.read_file(f"/vsizip/{archive.as_posix()}/{shp}", bbox=tuple(BBOX))
    rivers.geometry = rivers.geometry.intersection(box(*BBOX))
    path = OUT / "rivers.geojson"
    rivers.to_file(path, driver="GeoJSON")
    record(
        "rivers",
        path,
        url,
        version="HydroRIVERS v1.0 South America",
        archive_sha256=sha256_file(archive),
        license="HydroSHEDS licence; Lehner and Grill (2013)",
        limitations="15 arc-second derived network; small channels omitted; proximity is context, never an exclusion.",
    )
    write_json(OUT / "sources.json", MANIFEST)
    print("Hydrographic context", len(rivers), flush=True)


if __name__ == "__main__":
    main()
