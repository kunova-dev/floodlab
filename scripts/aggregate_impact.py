"""Build H3 impact products from a completed package; no EO processing or network."""

import argparse
import json
from pathlib import Path

from floodlab.impact.package import build_impact_package

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--hazard-type", required=True)
    parser.add_argument("--event-date", required=True)
    parser.add_argument("--resolution", type=int, default=7)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    folder = build_impact_package(
        args.source,
        root / "outputs/impacts",
        hazard_type=args.hazard_type,
        event_date=args.event_date,
        resolution=args.resolution,
    )
    print(folder)
    report = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "analysis_id",
                    "resolution",
                    "cell_count",
                    "affected_cell_count",
                    "totals",
                ]
            },
            indent=2,
        )
    )
