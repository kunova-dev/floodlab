"""Validated TOML configuration. Relative paths resolve against the repository root."""

import logging
import math
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Config:
    """Operational configuration independent of the working directory."""

    root: Path
    values: dict

    def path(self, value: str) -> Path:
        return (self.root / value).resolve()


def load_config(path: Path) -> Config:
    """Load configuration and reject invalid operational parameters."""
    with path.open("rb") as stream:
        values = tomllib.load(stream)
    catalogue = values["catalogue"]
    endpoint = urlparse(catalogue["endpoint"])
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
    ):
        raise ValueError("Catalogue endpoint must use HTTPS")
    if not catalogue["collection"] or not 1 <= catalogue["max_items"] <= 1000:
        raise ValueError("Set a collection and max_items between 1 and 1000")
    demo = values["demo"]
    if date.fromisoformat(demo["start"]) > date.fromisoformat(demo["end"]):
        raise ValueError("Start date must precede end date")
    flood, history = values["flood"], values["history"]
    if not all(math.isfinite(flood[k]) for k in ("water_db", "drop_db")):
        raise ValueError("Thresholds must be finite")
    if flood["drop_db"] >= 0:
        raise ValueError("Change threshold must be negative")
    integers = (catalogue["max_items"], flood["min_pixels"], history["gap_days"])
    if any(type(value) is not int for value in integers):
        raise ValueError("Item limits, component sizes and grouping days must be integers")
    if flood["min_pixels"] < 1 or history["gap_days"] < 0:
        raise ValueError("Invalid cleanup or grouping parameters")
    if (
        not all(math.isfinite(history[k]) for k in ("anomaly_multiplier", "minimum_excess"))
        or history["anomaly_multiplier"] < 0
        or history["minimum_excess"] <= 0
    ):
        raise ValueError("Invalid anomaly parameters")
    if values["logging"]["level"] not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise ValueError("Unknown logging level")
    for key in ("cache", "uploads", "outputs"):
        if not values["paths"][key]:
            raise ValueError(f"Missing path: {key}")
    logging.basicConfig(level=values["logging"]["level"])
    return Config(path.resolve().parent.parent, values)
