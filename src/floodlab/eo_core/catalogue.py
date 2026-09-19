"""Replaceable STAC discovery; no product download or preprocessing."""

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time
from typing import Protocol

from pystac_client import Client
from pystac_client.stac_api_io import StacApiIO
from shapely.geometry import shape

from .aoi import AOI


@dataclass(frozen=True)
class Acquisition:
    id: str
    collection: str
    datetime: str
    platform: str | None
    orbit: str | None
    relative_orbit: int | None
    polarizations: list[str]
    instrument_mode: str | None
    assets: dict
    geometry: dict

    def to_dict(self) -> dict:
        return asdict(self)


def normalize(item: dict) -> Acquisition:
    """Preserve absent metadata as unknown; never infer processing readiness."""
    p = item["properties"]
    timestamp = p.get("datetime") or p.get("start_datetime")
    if not timestamp:
        raise ValueError(f"Item {item['id']} has no acquisition timestamp")
    return Acquisition(
        item["id"],
        item.get("collection", ""),
        timestamp,
        p.get("platform"),
        p.get("sat:orbit_state"),
        p.get("sat:relative_orbit"),
        p.get("sar:polarizations") or [],
        p.get("sar:instrument_mode"),
        item.get("assets", {}),
        item["geometry"],
    )


def query(aoi: AOI, start: date, end: date, collection: str, maximum: int) -> dict:
    """Build a bounded inclusive UTC day query."""
    if start > end or not collection or not 1 <= maximum <= 1000:
        raise ValueError("Invalid date interval, collection, or result limit")
    return {
        "collections": [collection],
        "intersects": aoi.geojson()["geometry"],
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59.999999Z",
        "max_items": maximum,
        "limit": min(maximum, 100),
    }


class Catalogue(Protocol):
    def search(self, aoi: AOI, start: date, end: date) -> list[Acquisition]: ...


class StacCatalogue:
    """CDSE-compatible STAC adapter with bounded waits and runtime collection validation."""

    def __init__(self, endpoint: str, collection: str, maximum: int = 100):
        self.endpoint, self.collection, self.maximum = endpoint, collection, maximum

    def search(self, aoi: AOI, start: date, end: date) -> list[Acquisition]:
        arguments = query(aoi, start, end, self.collection, self.maximum)
        client = Client.open(self.endpoint, stac_io=StacApiIO(timeout=30, max_retries=1))
        client.get_collection(self.collection)  # Fail explicitly for an obsolete identifier.
        results = []
        for item in client.search(**arguments).items_as_dicts():
            acquisition = normalize(item)
            timestamp = datetime.fromisoformat(acquisition.datetime)
            if timestamp.tzinfo is None:
                raise ValueError("Catalogue timestamps must include a timezone")
            lower = datetime.combine(start, time.min, UTC)
            upper = datetime.combine(end, time.max, UTC)
            if lower <= timestamp <= upper and aoi.geometry.intersects(shape(item["geometry"])):
                results.append(acquisition)
        return sorted(results, key=lambda observation: observation.datetime)
