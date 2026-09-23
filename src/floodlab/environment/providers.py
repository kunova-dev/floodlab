"""Contracts for environmental providers; providers do not know hazards or exposure."""

from collections.abc import Protocol

from .model import EnvironmentalAsset, EnvironmentalVariable


class EnvironmentalProvider(Protocol):
    provider_id: str

    def describe(self) -> tuple[EnvironmentalAsset, ...]:
        """Return assets even when unavailable, with an explicit coverage state."""

    def variables(self) -> tuple[EnvironmentalVariable, ...]:
        """Return observed or derived variables with complete lineage."""
