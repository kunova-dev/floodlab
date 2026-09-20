"""Complete public Earth Search inventories; no tokens or paid processing."""

import json
from datetime import UTC, datetime

import requests

from .pair_jobs import write_json


def cached_search(path, collection, bbox, interval=None):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    url = "https://earth-search.aws.element84.com/v1/search"
    query = {"collections": collection, "bbox": ",".join(map(str, bbox)), "limit": 100}
    if interval:
        query["datetime"] = interval
    features = []
    seen = set()
    params = query
    while url:
        if url in seen:
            raise ValueError("Repeated STAC page; refusing truncated inventory")
        seen.add(url)
        response = requests.get(url, params=params, timeout=90)
        response.raise_for_status()
        page = response.json()
        features.extend(page["features"])
        link = next((link for link in page.get("links", []) if link.get("rel") == "next"), None)
        if link and link.get("method", "GET") != "GET":
            raise ValueError("Unsupported STAC pagination method")
        url = link["href"] if link else None
        params = None
    result = {
        "type": "FeatureCollection",
        "features": features,
        "links": [],
        "query": query,
        "checked_utc": datetime.now(UTC).isoformat(),
        "provider": "https://earth-search.aws.element84.com/v1",
        "pagination_complete": True,
    }
    write_json(path, result)
    return result
