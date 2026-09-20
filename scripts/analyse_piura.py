"""Reproduce the Piura event locally from verified cached processing; no remote jobs."""

import json
from pathlib import Path

from floodlab.eo_core.aoi import AOI
from floodlab.hazards.flood.workflow import analyse_event


def main():
    root = Path(__file__).resolve().parents[1]
    event = json.loads((root / "config/piura2017-event.json").read_text(encoding="utf-8"))
    result = analyse_event(root, AOI.read(root / "config/aoi/piura2017.geojson"), event)
    print(result)
    report = json.loads(result.read_text(encoding="utf-8"))
    print(report["confidence"])
    print(f"Probable new inundation: {report['probable_flooded_area_ha']:.2f} ha")


if __name__ == "__main__":
    main()
