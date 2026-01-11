"""
Base infrastructure for event source registry.

Provides a registry pattern for pluggable event sources (Eventbrite, Exa, etc.)
that can be queried in parallel during event search.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EventSource:
    """
    Represents a pluggable event source.

    Each source has a name, a search function, and an optional
    function to check if it's enabled (has API key configured).
    """

    name: str
    """Unique identifier for this source (e.g., 'eventbrite', 'exa')"""

    search_fn: Callable[..., Awaitable[list[Any]]]
    """Async function that searches for events. Should accept a SearchProfile."""

    is_enabled_fn: Callable[[], bool] | None = None
    """Optional function to check if source is configured/enabled."""

    priority: int = 100
    """Lower priority sources are queried first. Default is 100."""

    description: str = ""
    """Human-readable description of this source."""

    def is_enabled(self) -> bool:
        """Check if this event source is enabled and configured."""
        if self.is_enabled_fn is None:
            return True
        return self.is_enabled_fn()


@dataclass
class EventSourceRegistry:
    """
    Registry for event sources.

    Event sources can be registered and then queried in parallel
    during event search operations.

    Usage:
        registry = EventSourceRegistry()
        registry.register(EventSource(
            name="eventbrite",
            search_fn=eventbrite_search,
            is_enabled_fn=lambda: bool(settings.eventbrite_api_key),
        ))

        # Get all enabled sources
        sources = registry.get_enabled_sources()
    """

    _sources: dict[str, EventSource] = field(default_factory=dict)

    def register(self, source: EventSource) -> None:
        """
        Register an event source.

        Args:
            source: EventSource to register

        Raises:
            ValueError: If a source with the same name is already registered
        """
        if source.name in self._sources:
            raise ValueError(f"Event source '{source.name}' is already registered")

        self._sources[source.name] = source
        logger.info("Registered event source: %s", source.name)

    def unregister(self, name: str) -> bool:
        """
        Unregister an event source by name.

        Args:
            name: Name of the source to unregister

        Returns:
            True if source was unregistered, False if not found
        """
        if name in self._sources:
            del self._sources[name]
            logger.info("Unregistered event source: %s", name)
            return True
        return False

    def get(self, name: str) -> EventSource | None:
        """Get a specific event source by name."""
        return self._sources.get(name)

    def get_all(self) -> list[EventSource]:
        """Get all registered sources, sorted by priority."""
        return sorted(self._sources.values(), key=lambda s: s.priority)

    def get_enabled(self) -> list[EventSource]:
        """Get all enabled sources, sorted by priority."""
        return [s for s in self.get_all() if s.is_enabled()]

    def get_names(self) -> list[str]:
        """Get names of all registered sources."""
        return list(self._sources.keys())

    def __len__(self) -> int:
        """Return number of registered sources."""
        return len(self._sources)

    def __contains__(self, name: str) -> bool:
        """Check if a source is registered."""
        return name in self._sources


# Global registry instance
_registry: EventSourceRegistry | None = None


def get_event_source_registry() -> EventSourceRegistry:
    """
    Get the global event source registry.

    Returns:
        The singleton EventSourceRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = EventSourceRegistry()
    return _registry


def register_event_source(source: EventSource) -> None:
    """
    Convenience function to register a source with the global registry.

    Args:
        source: EventSource to register
    """
    get_event_source_registry().register(source)
