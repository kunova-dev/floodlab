"""Prepare the exact missing real-data Piura 2017 v0.5c processing plan; never submits jobs."""

import json
from pathlib import Path

from floodlab.eo_core.aoi import AOI
from floodlab.eo_core.catalogue import normalize
from floodlab.eo_core.observation_jobs import create_plan
from floodlab.eo_core.openeo_backend import BackendSettings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    specification = json.loads(
        (root / "config/piura2017-temporal.json").read_text(encoding="utf-8")
    )
    items = json.loads((root / specification["catalogue_diagnostic"]).read_text(encoding="utf-8"))
    by_id = {item["id"]: normalize(item) for item in items}
    missing = [
        product_id
        for product_id in specification["required_product_ids"]
        if product_id not in by_id
    ]
    if missing:
        raise ValueError(
            "Configured products absent from the live catalogue diagnostic: " + ", ".join(missing)
        )
    observations = [by_id[product_id] for product_id in specification["required_product_ids"]]
    # Match the existing reviewed Piura CDSE configuration, including resource settings.
    import tomllib

    settings = BackendSettings(
        **tomllib.loads((root / "config/piura2017.toml").read_text(encoding="utf-8"))["openeo"]
    )
    plan = create_plan(root, observations, AOI.read(root / specification["aoi"]), settings)
    print(plan)
    print(
        f"Reviewed CDSE processing requirement: {len(observations)} single-acquisition batch jobs."
    )
    for item in observations:
        print(f"{item.datetime} | {item.orbit} rel {item.relative_orbit} | {item.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
