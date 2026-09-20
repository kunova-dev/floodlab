"""Public capabilities and optional live Piura plan; never authenticate or submit jobs."""

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from floodlab.eo_core.aoi import AOI
from floodlab.eo_core.catalogue import StacCatalogue
from floodlab.eo_core.config import load_config
from floodlab.eo_core.openeo_backend import BackendSettings, OpenEOBackend, process_graph
from floodlab.eo_core.pair_jobs import create_plan, runtime_root, write_json
from floodlab.eo_core.pairs import candidate_pairs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-demo", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "config/piura2017.toml")
    settings = BackendSettings(**cfg.values["openeo"])
    backend = OpenEOBackend(settings)
    snapshot = backend.capabilities()
    cache = runtime_root(root, settings)
    write_json(cache / "public-capabilities.json", snapshot)
    print("Public capability validation passed:", snapshot["endpoint"])
    print(
        "API:",
        snapshot["capabilities"].get("api_version"),
        "Backend:",
        snapshot["capabilities"].get("backend_version"),
    )
    print(
        "Collection:",
        settings.collection,
        "Coefficient:",
        settings.coefficient,
        "DEM:",
        settings.elevation_model,
    )
    print("Authentication:", backend.state, "No jobs submitted.")
    if args.prepare_demo:
        aoi = AOI.read(cfg.path(cfg.values["demo"]["aoi"]))
        cat = cfg.values["catalogue"]
        demo = cfg.values["demo"]
        observations = StacCatalogue(cat["endpoint"], cat["collection"], cat["max_items"]).search(
            aoi, date.fromisoformat(demo["start"]), date.fromisoformat(demo["end"])
        )
        pairs = candidate_pairs(
            observations,
            aoi,
            bands=tuple(settings.bands),
            minimum_coverage=settings.minimum_coverage,
        )
        report = {
            "checked_utc": datetime.now(UTC).isoformat(),
            "catalogue_endpoint": cat["endpoint"],
            "acquisitions": [o.to_dict() for o in observations],
            "pairs": [
                {"earlier": a.id, "later": b.id, "assessment": q.to_dict()} for a, b, q in pairs
            ],
        }
        write_json(cache / "pair-candidates.json", report)
        preference = cfg.values["pair_demo"]
        selected = next(
            (
                (a, b, q)
                for a, b, q in pairs
                if a.datetime[:10] == preference["earlier"]
                and b.datetime[:10] == preference["later"]
            ),
            None,
        )
        if selected is None:
            raise ValueError(
                "Configured demo hypothesis is not in the comparable live inventory; select a different reviewed pair in Flood Lab"
            )
        a, b, q = selected
        path = create_plan(root, a, b, aoi, settings)
        print("Prepared plan:", path)
        print("Earlier:", a.id, "Later:", b.id)
        print("Assessment:", json.dumps(q.to_dict()))
        validation = {}
        for role, obs in [("earlier", a), ("later", b)]:
            graph, _ = process_graph(obs, aoi, settings, snapshot)
            try:
                validation[role] = backend.connection.validate_process_graph(graph)
            except Exception as exc:  # noqa: BLE001 -- public validation is optional, never submit here
                validation[role] = {"unverified": type(exc).__name__}
        write_json(path.parent / "public-graph-validation.json", validation)
        print("Public graph validation:", json.dumps(validation))
        print(
            'Next user action: python scripts/process_pair.py --plan "'
            + str(path.relative_to(root))
            + '"'
        )


if __name__ == "__main__":
    main()
