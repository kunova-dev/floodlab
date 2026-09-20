"""CDSE openEO discovery and process graphs, with explicit in-memory OIDC authentication."""

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import openeo

from .aoi import AOI
from .catalogue import Acquisition


@dataclass(frozen=True)
class BackendSettings:
    endpoint: str = "https://openeo.dataspace.copernicus.eu"
    collection: str = "SENTINEL1_GRD"
    coefficient: str = "sigma0-ellipsoid"
    elevation_model: str = "COPERNICUS_30"
    bands: tuple[str, ...] = ("VV",)
    resolution_m: int = 20
    resampling: str = "bilinear"
    cache: str = "data/cache/openeo"
    minimum_coverage: float = 0.8
    minimum_valid_fraction: float = 0.8
    poll_seconds: int = 20
    max_wait_seconds: int = 7200
    job_options: dict = field(default_factory=dict)

    def __post_init__(self):
        url = urlparse(self.endpoint)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query:
            raise ValueError("Require a credential-free HTTPS backend URL")
        if self.coefficient != "sigma0-ellipsoid" or self.resampling != "bilinear":
            raise ValueError(
                "This implementation supports sigma0-ellipsoid and explicit bilinear resampling"
            )
        if not self.bands or not set(self.bands) <= {"VV", "VH"}:
            raise ValueError("Request VV and/or VH")
        if (
            not 10 <= self.resolution_m <= 1000
            or not 1 <= self.poll_seconds <= 60
            or self.max_wait_seconds < 1
        ):
            raise ValueError("Invalid resolution or polling limits")
        if not 0 < self.minimum_coverage <= 1 or not 0 < self.minimum_valid_fraction <= 1:
            raise ValueError("Coverage thresholds must be in (0,1]")

        memory_keys = {"executor-memory", "executor-memoryOverhead", "python-memory"}
        count_keys = {"executor-cores", "task-cpus", "max-executors"}
        if not isinstance(self.job_options, dict):
            raise TypeError("job_options must be a mapping")
        if not set(self.job_options) <= memory_keys | count_keys:
            raise ValueError("Unsupported resource job option")
        for key, value in self.job_options.items():
            if key in memory_keys:
                if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*[mMgG]", value):
                    raise ValueError(f"{key} must be a positive memory size such as 8G")
            elif type(value) is not int or value < 1:
                raise ValueError(f"{key} must be a positive integer")
        if self.job_options.get("executor-cores", 1) != self.job_options.get("task-cpus", 1):
            raise ValueError("Use one task per executor: executor-cores must equal task-cpus")

    def to_dict(self) -> dict:
        return asdict(self)


def discover(connection, settings: BackendSettings) -> dict:
    """Public discovery of actual collection/process/DEM/format/OIDC support."""
    return {
        "endpoint": connection.root_url,
        "capabilities": connection.capabilities().capabilities,
        "collection": connection.describe_collection(settings.collection),
        "dem": connection.describe_collection(settings.elevation_model),
        "processes": connection.list_processes(),
        "formats": connection.list_output_formats(),
        "oidc": connection.get("/credentials/oidc").json(),
    }


def validate_capabilities(snapshot: dict, settings: BackendSettings) -> None:
    """Fail closed when required advertised capabilities are absent."""
    processes = {p["id"]: p for p in snapshot["processes"]}
    required = {
        "load_collection",
        "sar_backscatter",
        "resample_spatial",
        "filter_spatial",
        "save_result",
        "eq",
    }
    if not required <= processes.keys():
        raise ValueError(
            "Backend lacks required processes: " + ", ".join(sorted(required - processes.keys()))
        )
    if (
        snapshot["collection"]["id"] != settings.collection
        or snapshot["dem"]["id"] != settings.elevation_model
    ):
        raise ValueError("Collection or DEM identity does not match configuration")
    dimensions = snapshot["collection"].get("cube:dimensions", {})
    bands = next((d.get("values", []) for d in dimensions.values() if d.get("type") == "bands"), [])
    if not set(settings.bands) <= set(bands):
        raise ValueError("Requested polarization not advertised by collection")
    params = {p["name"]: p for p in processes["sar_backscatter"]["parameters"]}
    if not {"coefficient", "elevation_model", "noise_removal"} <= params.keys():
        raise ValueError("SAR parameter support not advertised")
    if settings.coefficient not in params["coefficient"]["schema"].get("enum", []):
        raise ValueError("Requested backscatter coefficient not advertised")
    if "GTiff" not in snapshot["formats"]:
        raise ValueError("GTiff output not advertised")
    summaries = snapshot["collection"].get("summaries", {})
    if not {"sat:orbit_state", "sar:instrument_mode"} <= summaries.keys():
        raise ValueError("Orbit/mode filters not advertised")
    if not snapshot.get("oidc", {}).get("providers"):
        raise ValueError("OIDC providers not advertised")


class OpenEOBackend:
    """No credential cache reads/writes; OIDC device login is explicit in the terminal."""

    def __init__(self, settings: BackendSettings, connection=None):
        self.settings = settings
        self.connection = (
            connection
            if connection is not None
            else openeo.connect(settings.endpoint, default_timeout=30)
        )
        self.authenticated = False

    @property
    def state(self) -> str:
        return "READY" if self.authenticated else "NOT AUTHENTICATED"

    def authenticate(self) -> None:
        self.authenticated = False
        self.connection.authenticate_oidc_device(store_refresh_token=False, max_poll_time=300)
        self.connection.describe_account()  # Do not print account details or tokens.
        self.authenticated = True

    def capabilities(self) -> dict:
        snapshot = discover(self.connection, self.settings)
        validate_capabilities(snapshot, self.settings)
        return snapshot

    def submit(self, graph: dict, title: str):
        if not self.authenticated:
            raise PermissionError("Authenticate with the terminal OIDC workflow first")
        errors = self.connection.validate_process_graph(graph)
        if errors:
            raise ValueError("Backend process graph validation returned errors; no job submitted")
        return self.connection.create_job(
            graph, title=title, validate=False, job_options=dict(self.settings.job_options)
        )


def process_graph(
    observation: Acquisition, aoi: AOI, settings: BackendSettings, snapshot: dict
) -> tuple[dict, dict]:
    """One acquisition-start second, advertised orbit/mode filters, explicit SAR processing.

    This is a catalogue-constrained request, not a claim of exact source-product pinning.
    Backend filtering and source lineage require verification after execution.
    """
    validate_capabilities(snapshot, settings)
    timestamp = datetime.fromisoformat(observation.datetime).astimezone(UTC).replace(microsecond=0)
    extent = [
        timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        (timestamp + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    ]
    west, south, east, north = aoi.geometry.bounds
    lat, lon = aoi.geometry.centroid.y, aoi.geometry.centroid.x
    if not -80 <= lat <= 84:
        raise ValueError(
            "Automatic UTM processing currently requires AOI latitude between -80 and 84"
        )
    epsg = (32600 if lat >= 0 else 32700) + min(60, max(1, int((lon + 180) // 6) + 1))

    def predicate(value):
        return {
            "process_graph": {
                "match": {
                    "process_id": "eq",
                    "arguments": {"x": {"from_parameter": "value"}, "y": value},
                    "result": True,
                }
            }
        }

    # Use the values actually advertised by the backend, not a hard-coded case convention.
    summaries = snapshot["collection"]["summaries"]
    advertised = next(
        (v for v in summaries["sat:orbit_state"] if v.lower() == observation.orbit.lower()), None
    )
    if advertised is None or observation.instrument_mode not in summaries["sar:instrument_mode"]:
        raise ValueError("Selected orbit/mode not advertised")
    properties = {
        "sat:orbit_state": predicate(advertised),
        "sar:instrument_mode": predicate(observation.instrument_mode),
    }
    warnings = [
        "Exact input product identity is not pinned by openEO load_collection; expected STAC ID is a candidate until backend lineage is verified.",
        "One-second acquisition-start interval may yield no data if backend timestamps differ; do not silently widen it.",
        "Zero is conservatively excluded: CDSE documents ambiguity between thermal-noise removal and nodata.",
    ]
    if "sat:relative_orbit" in summaries:
        properties["sat:relative_orbit"] = predicate(observation.relative_orbit)
    else:
        warnings.append(
            "Backend does not advertise relative-orbit filtering; narrow time and direction constrain the request, but actual input relative orbit remains unverified."
        )
    graph = {
        "load": {
            "process_id": "load_collection",
            "arguments": {
                "id": settings.collection,
                "spatial_extent": {
                    "west": west,
                    "south": south,
                    "east": east,
                    "north": north,
                    "crs": "EPSG:4326",
                },
                "temporal_extent": extent,
                "bands": list(settings.bands),
                "properties": properties,
            },
        },
        "sar": {
            "process_id": "sar_backscatter",
            "arguments": {
                "data": {"from_node": "load"},
                "coefficient": settings.coefficient,
                "elevation_model": settings.elevation_model,
                "noise_removal": True,
            },
        },
        "grid": {
            "process_id": "resample_spatial",
            "arguments": {
                "data": {"from_node": "sar"},
                "resolution": settings.resolution_m,
                "projection": epsg,
                "method": settings.resampling,
            },
        },
        "clip": {
            "process_id": "filter_spatial",
            "arguments": {"data": {"from_node": "grid"}, "geometries": aoi.geojson()["geometry"]},
        },
        "save": {
            "process_id": "save_result",
            "arguments": {"data": {"from_node": "clip"}, "format": "GTiff"},
            "result": True,
        },
    }
    return graph, {
        "requested_temporal_extent": extent,
        "requested_crs": f"EPSG:{epsg}",
        "requested_resolution_m": settings.resolution_m,
        "resampling": settings.resampling,
        "coefficient": settings.coefficient,
        "units": "linear power",
        "orthorectification": "Requested CDSE sar_backscatter with "
        + settings.elevation_model
        + "; execution unverified until job completes",
        "warnings": warnings,
    }
