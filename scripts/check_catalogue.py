"""Optional bounded live metadata check; does not download satellite products."""

from datetime import date
from pathlib import Path

from floodlab.eo_core.aoi import AOI
from floodlab.eo_core.catalogue import StacCatalogue
from floodlab.eo_core.config import load_config

if __name__ == "__main__":
    cfg = load_config(Path(__file__).resolve().parents[1] / "config/piura2017.toml")
    settings = cfg.values["catalogue"]
    observations = StacCatalogue(settings["endpoint"], settings["collection"], 3).search(
        AOI.read(cfg.path(cfg.values["demo"]["aoi"])),
        date.fromisoformat(cfg.values["demo"]["start"]),
        date.fromisoformat(cfg.values["demo"]["end"]),
    )
    print(
        f"Live metadata check: {len(observations)} observations returned (cap 3; not a complete timeline)"
    )
    for observation in observations:
        print(observation.id, observation.datetime, observation.polarizations)
