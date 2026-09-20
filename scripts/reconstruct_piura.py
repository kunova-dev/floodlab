"""Create a new immutable v0.4 product from verified local evidence; no remote jobs."""

import json
from pathlib import Path

from floodlab.eo_core.aoi import AOI
from floodlab.hazards.flood.reconstruction import reconstruct


def main():
    root = Path(__file__).resolve().parents[1]
    event = json.loads((root / "config/piura2017-event.json").read_text(encoding="utf-8"))
    path = reconstruct(root, AOI.read(root / "config/aoi/piura2017.geojson"), event)
    print(path, flush=True)
    report = json.loads(path.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {k: report[k] for k in ["metrics", "evidence_area_ha", "context", "comparison"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
