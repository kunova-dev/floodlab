"""Gauge discovery with explicit unavailable evidence; never invent a stage-discharge curve."""

from datetime import datetime
from math import isfinite


def validate_gauge_observations(records):
    for record in records:
        required = {
            "station_id",
            "timestamp",
            "value",
            "units",
            "variable",
            "provider",
            "source_url",
            "quality",
        }
        if not required <= record.keys():
            raise ValueError("Incomplete gauge provenance")
        if (
            isinstance(record["value"], bool)
            or not isinstance(record["value"], (int, float))
            or not isfinite(record["value"])
        ):
            raise ValueError("Gauge values must be finite numbers")
        timestamp = datetime.fromisoformat(record["timestamp"])
        if timestamp.tzinfo is None:
            raise ValueError("Gauge timestamps require timezone")
        if record["variable"] not in ("stage", "discharge"):
            raise ValueError("Unknown gauge variable")
        if record["units"] != ("m" if record["variable"] == "stage" else "m3/s"):
            raise ValueError("Gauge units mismatch")
        if record.get("derived_from_stage") and not record.get("rating_curve_source"):
            raise ValueError("Stage-derived discharge requires authoritative rating provenance")
    return records
