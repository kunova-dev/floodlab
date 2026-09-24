"""Provider-neutral mapped-building enrichment; no hazard processing imports."""

import json
import pickle
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from shapely.geometry import mapping, shape

from .engine import polygon_input

OVERTURE_RELEASE = "2026-08-19.0"
OVERTURE_LICENSE = "ODbL-1.0; feature source licences are retained when supplied"


@dataclass(frozen=True)
class Building:
    """Normalized provider-independent mapped building. Missing source attributes stay None."""

    source_id: str
    geometry: object
    provider: str
    release: str
    subtype: str | None = None
    height_m: float | None = None
    levels: float | None = None
    confidence: float | None = None
    source_metadata: dict | None = None


class BuildingProvider(Protocol):
    provider: str
    release: str

    def retrieve(self, aoi) -> tuple[list[Building], dict]: ...


class OvertureBuildingProvider:
    """AOI-only Overture client adapter with deterministic local subset cache."""

    provider = "Overture Maps Buildings"

    def __init__(self, cache_root, *, release=OVERTURE_RELEASE, executable=None):
        self.release = release
        self.cache_root = Path(cache_root)
        self.executable = executable or str(Path(sys.executable).with_name("overturemaps.exe"))

    def retrieve(self, aoi) -> tuple[list[Building], dict]:
        aoi = polygon_input(aoi)
        digest = sha256((self.provider + self.release + aoi.wkb_hex).encode()).hexdigest()[:24]
        folder = self.cache_root / "overture-buildings" / digest
        output = folder / "buildings.geojson"
        receipt = folder / "provenance.json"
        if receipt.exists():
            meta = json.loads(receipt.read_text(encoding="utf-8"))
            if (folder / "buildings.parquet").exists() and (
                meta.get("status") == "no_data" or meta.get("diagnostic")
            ):
                failed_attempt = next((attempt for attempt in meta.get("attempts", []) if attempt.get("status") == "no_data"), None) or {
                    "method": "overturemaps-cli-stac", "status": "no_data", "diagnostic": meta.get("diagnostic", "No data found")
                }
                meta.update(
                    {
                        "status": "retrieved",
                        "retrieval_path": "duckdb-cloud-geoparquet",
                        "final_retrieval": "DuckDB cloud GeoParquet fallback succeeded",
                        "attempts": [failed_attempt, {"method": "duckdb-cloud-geoparquet", "status": "retrieved"}],
                        "diagnostic": None,
                        "query_method": "DuckDB read_parquet cloud GeoParquet with bbox overlap predicate",
                    }
                )
                receipt.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
                buildings = self._normalized(folder, meta)
                meta["feature_count"] = len(buildings)
                receipt.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
                return buildings, {
                    **meta,
                    "feature_count": len(buildings),
                    "cache_status": "reused",
                }
            if meta.get("status") != "no_data" or meta.get("fallback_checked"):
                cached = (
                    self._normalized(folder, meta)
                    if meta.get("retrieval_path") == "duckdb-cloud-geoparquet"
                    else self._read(output)
                    if output.exists()
                    else []
                )
                meta["feature_count"] = len(cached)
                return cached, {
                    **meta,
                    "cache_status": "reused",
                }
        folder.mkdir(parents=True, exist_ok=True)
        west, south, east, north = aoi.bounds
        command = [
            self.executable,
            "download",
            f"--bbox={west},{south},{east},{north}",
            "-f",
            "geojson",
            "-t",
            "building",
            "-r",
            self.release,
            "-o",
            str(output),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        retrieved_at = datetime.now(UTC).isoformat()
        message = (completed.stderr or completed.stdout).strip()
        if completed.returncode != 0 or not output.exists():
            if "No data found" in message or (completed.returncode == 0 and not output.exists()):
                try:
                    buildings, raw_count = self._duckdb_retrieve(aoi, folder)
                except Exception as exc:
                    raise RuntimeError(f"Overture provider/query unavailable: {exc}") from exc
                if raw_count:
                    meta = self._metadata(
                        aoi,
                        digest,
                        retrieved_at,
                        "retrieved",
                        "DuckDB cloud GeoParquet fallback",
                        raw_count,
                    )
                    meta["retrieval_path"] = "duckdb-cloud-geoparquet"
                    meta["final_retrieval"] = "DuckDB cloud GeoParquet fallback succeeded"
                    meta["attempts"] = [
                        {"method": "overturemaps-cli-stac", "status": "no_data", "diagnostic": message},
                        {"method": "duckdb-cloud-geoparquet", "status": "retrieved", "feature_count": raw_count},
                    ]
                    meta["diagnostic"] = None
                    receipt.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
                    return buildings, meta
                meta = self._metadata(
                    aoi, digest, retrieved_at, "no_data", message or "No output produced", 0
                )
                meta["fallback_checked"] = True
                receipt.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
                return [], meta
            raise RuntimeError(
                f"Overture building retrieval unavailable: {message or completed.returncode}"
            )
        buildings = self._read(output)
        meta = self._metadata(aoi, digest, retrieved_at, "retrieved", None, len(buildings))
        receipt.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")
        return buildings, meta

    def _duckdb_retrieve(self, aoi, folder):
        import duckdb

        parquet = folder / "buildings.parquet"
        connection = duckdb.connect()
        connection.execute("INSTALL httpfs")
        connection.execute("LOAD httpfs")
        connection.execute("SET s3_region='us-west-2'")
        west, south, east, north = aoi.bounds
        query = f"""
            SELECT * FROM read_parquet(
              's3://overturemaps-us-west-2/release/{self.release}/theme=buildings/type=building/*',
              hive_partitioning=1
            )
            WHERE bbox.xmin <= {east} AND bbox.xmax >= {west}
              AND bbox.ymin <= {north} AND bbox.ymax >= {south}
        """
        connection.execute(f"COPY ({query}) TO '{parquet.as_posix()}' (FORMAT PARQUET)")
        count = connection.execute(
            f"SELECT count(*) FROM read_parquet('{parquet.as_posix()}')"
        ).fetchone()[0]
        return self._read_parquet(parquet), count

    def _read_parquet(self, output):
        from pyarrow import parquet
        from shapely import from_wkb

        table = parquet.read_table(output)
        names = set(table.column_names)
        rows = table.to_pylist()
        result = []
        for props in rows:
            geometry = from_wkb(props["geometry"])
            if (
                geometry.is_empty
                or not geometry.is_valid
                or geometry.geom_type not in ("Polygon", "MultiPolygon")
            ):
                continue

            def number(value):
                return float(value) if isinstance(value, (int, float)) and value >= 0 else None

            result.append(
                Building(
                    str(props.get("id") or sha256(geometry.wkb).hexdigest()),
                    geometry,
                    self.provider,
                    self.release,
                    props.get("subtype") or props.get("class"),
                    number(props.get("height")),
                    number(props.get("num_floors") or props.get("levels")),
                    number(props.get("confidence")),
                    props.get("sources") if "sources" in names else None,
                )
            )
        return result

    def _normalized(self, folder, metadata):
        """Persist our deterministic normalized representation once per raw source/schema."""
        raw = folder / "buildings.parquet"
        cache, receipt = (
            folder / "normalized-buildings-v1.pkl",
            folder / "normalized-buildings-v1.json",
        )
        source_hash = sha256(raw.read_bytes()).hexdigest()
        expected = {"schema": 1, "release": self.release, "source_sha256": source_hash}
        if receipt.exists() and cache.exists():
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            if all(saved.get(key) == value for key, value in expected.items()) and sha256(
                cache.read_bytes()
            ).hexdigest() == saved.get("cache_sha256"):
                with cache.open("rb") as stream:
                    return pickle.load(stream)
        buildings = self._read_parquet(raw)
        temporary = cache.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            pickle.dump(buildings, stream, protocol=pickle.HIGHEST_PROTOCOL)
        temporary.replace(cache)
        receipt.write_text(
            json.dumps(
                {
                    **expected,
                    "cache_sha256": sha256(cache.read_bytes()).hexdigest(),
                    "feature_count": len(buildings),
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return buildings

    def _metadata(self, aoi, cache_id, retrieved_at, status, detail, feature_count):
        return {
            "provider": self.provider,
            "release": self.release,
            "license": OVERTURE_LICENSE,
            "retrieved_at": retrieved_at,
            "dataset_reference_date": None,
            "temporal_baseline": "MODERN / CONTEXTUAL BUILT-ENVIRONMENT BASELINE",
            "query_method": "overturemaps download --bbox … -f geojson -t building -r release",
            "aoi_geojson": mapping(aoi),
            "cache_id": cache_id,
            "status": status,
            "diagnostic": detail,
            "feature_count": feature_count,
        }

    def _read(self, output):
        collection = json.loads(output.read_text(encoding="utf-8"))
        result = []
        for feature in collection.get("features", []):
            props = feature.get("properties", {})
            geometry = shape(feature["geometry"])
            if (
                geometry.is_empty
                or not geometry.is_valid
                or geometry.geom_type not in ("Polygon", "MultiPolygon")
            ):
                continue
            source_id = str(
                props.get("id") or props.get("source_id") or sha256(geometry.wkb).hexdigest()
            )

            def number(value):
                return float(value) if isinstance(value, (int, float)) and value >= 0 else None

            result.append(
                Building(
                    source_id,
                    geometry,
                    self.provider,
                    self.release,
                    props.get("subtype") or props.get("class"),
                    number(props.get("height")),
                    number(props.get("num_floors") or props.get("levels")),
                    number(props.get("confidence")),
                    props.get("sources")
                    if isinstance(props.get("sources"), (dict, list))
                    else None,
                )
            )
        return result
