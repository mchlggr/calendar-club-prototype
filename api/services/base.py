"""Event source registry infrastructure.

Provides a registry pattern for managing multiple event sources (Eventbrite, Luma, etc.)
with dynamic availability checking and adapter functions.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from api.models import SearchProfile


@dataclass
class EventSource:
    """Represents an event data source.

    Attributes:
        name: Unique identifier for this source (e.g., "eventbrite", "luma")
        fetch_fn: Async function that fetches events given a SearchProfile.
                  Returns list of events (EventResult or similar).
        is_available_fn: Sync function that checks if this source is available
                        (e.g., API key configured). Defaults to always available.
        description: Human-readable description of this source.
    """

    name: str
    fetch_fn: Callable[[SearchProfile], Awaitable[list]]
    is_available_fn: Callable[[], bool] = field(default=lambda: True)
    description: str = ""


class EventSourceRegistry:
    """Registry for managing event sources.

    Provides registration, availability checking, and retrieval of event sources.
    Sources can be conditionally available based on configuration (API keys, etc.).
    """

    def __init__(self) -> None:
        self._sources: dict[str, EventSource] = {}

    def register(self, source: EventSource) -> None:
        """Register an event source.

        Args:
            source: EventSource to register

        Raises:
            ValueError: If a source with this name is already registered
        """
        if source.name in self._sources:
            raise ValueError(f"Source '{source.name}' is already registered")
        self._sources[source.name] = source

    def get(self, name: str) -> EventSource | None:
        """Get a registered source by name.

        Args:
            name: Source name to look up

        Returns:
            EventSource if found, None otherwise
        """
        return self._sources.get(name)

    def get_available(self) -> list[EventSource]:
        """Get all sources that are currently available.

        Returns:
            List of available EventSource instances
        """
        return [s for s in self._sources.values() if s.is_available_fn()]

    def get_all(self) -> list[EventSource]:
        """Get all registered sources regardless of availability.

        Returns:
            List of all registered EventSource instances
        """
        return list(self._sources.values())

    def is_available(self, name: str) -> bool:
        """Check if a source is registered and available.

        Args:
            name: Source name to check

        Returns:
            True if source is registered and available
        """
        source = self._sources.get(name)
        return source is not None and source.is_available_fn()


# Global registry instance
event_registry = EventSourceRegistry()
