"""Create a DRAFT Piura v0.5e environmental context package from verified static assets."""

import json
from pathlib import Path
from uuid import uuid4

import rasterio

from floodlab.environment.context import (
    load_verified_static_context,
    summarize_continuous_context,
)
from floodlab.environment.h3sidecar import environmental_h3_sidecar
from floodlab.environment.integrity import sha256_file
from floodlab.environment.package import (
    export_environment_package,
    validate_environment_package,
)

ROOT = Path(__file__).resolve().parents[1]


def _latest_temporal() -> Path:
    choices = sorted(
        (ROOT / "outputs/analyses").glob("*/temporal-summary.json"), key=lambda p: p.stat().st_mtime
    )
    if not choices:
        raise FileNotFoundError("A v0.5c temporal summary is required")
    return choices[-1]


def build_environment_provenance(
    *,
    root: Path,
    source: Path,
    temporal: Path,
    aoi_geometry: dict,
    context: dict,
    environment_config: dict,
) -> dict:
    """Build provenance without exporting a package, for deterministic inspection/tests."""
    footprint_files = {
        "maximum_observed_single_date": "maximum-observed-single-date.tif",
        "temporal_union": "event-observed-temporal-union.tif",
    }
    return {
        "milestone": "v0.5e",
        "status": "DRAFT",
        "aoi": aoi_geometry,
        "environment_configuration": environment_config,
        "reference_grid_source": str(source.relative_to(root)),
        "reference_grid_sha256": sha256_file(source),
        "footprint_inputs": {
            label: {
                "path": str((temporal / filename).relative_to(root)),
                "sha256": sha256_file(temporal / filename),
            }
            for label, filename in footprint_files.items()
            if (temporal / filename).exists()
        },
        "assets": [asset.to_dict() for asset in context["assets"]],
        "variables": [variable.to_dict() for variable in context["variables"]],
        "land_cover": {
            "coverage_status": "UNAVAILABLE_PROVIDER",
            "dataset": "ESA CCI Land Cover C3S/CCI v2.1.1 annual 2017",
            "reason": "No verified local subset receipt yet; not substituted with current land cover.",
        },
        "native_derived_arrays_exported": False,
        "limitations": [
            "Environmental context is not hazard classification, exposure, impact, causation, HAND or loss.",
            "Native rasters are authoritative; H3 is a summary sidecar.",
            "Derived-data checksums describe deterministic in-memory native values and validity masks; native derived arrays are not exported in this package.",
        ],
    }


def main() -> Path:
    config = json.loads((ROOT / "config/piura2017-temporal.json").read_text(encoding="utf-8"))
    environment_config = json.loads((ROOT / "config/environment.json").read_text(encoding="utf-8"))
    aoi_feature = json.loads((ROOT / config["aoi"]).read_text(encoding="utf-8"))
    aoi_geometry = aoi_feature["geometry"]
    temporal = _latest_temporal()
    source = temporal.parent / "maximum-observed-single-date.tif"
    if not source.exists():
        source = temporal.parent / "maximum-observed-single-date-inundation.tif"
    with rasterio.open(source) as raster:
        profile = raster.profile.copy()
    context = load_verified_static_context(ROOT, profile, aoi_geometry)
    summaries = {"aoi": summarize_continuous_context(context, context["arrays"]["aoi"])}
    for label, filename in {
        "maximum_observed_single_date": "maximum-observed-single-date.tif",
        "temporal_union": "event-observed-temporal-union.tif",
    }.items():
        path = temporal.parent / filename
        if not path.exists():
            continue
        with rasterio.open(path) as raster:
            observed = raster.read(1) == 1
        summaries[label] = summarize_continuous_context(context, observed)
    standard_resolution = environment_config["standard_event_resolution"]
    sidecar = environmental_h3_sidecar(
        aoi_geometry,
        profile,
        context["arrays"],
        resolution=standard_resolution,
        source_checksums=tuple(asset.checksum for asset in context["assets"]),
        variable_checksums=tuple(
            variable.derived_data_checksum for variable in context["variables"]
        ),
        variable_metadata_checksums=tuple(
            context["variable_metadata_checksums"][variable.variable_id]
            for variable in context["variables"]
        ),
        related_resolutions=tuple(environment_config["optional_overview_resolutions"]),
    )
    provenance = build_environment_provenance(
        root=ROOT,
        source=source,
        temporal=temporal.parent,
        aoi_geometry=aoi_geometry,
        context=context,
        environment_config=environment_config,
    )
    output = ROOT / "outputs/environment" / str(uuid4())
    export_environment_package(output, provenance=provenance, summaries=summaries, sidecar=sidecar)
    validate_environment_package(output)
    return output


if __name__ == "__main__":
    print(main())
