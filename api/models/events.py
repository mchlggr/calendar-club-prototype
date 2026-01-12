"""Event-related models for search results and refinement."""

from pydantic import BaseModel, Field

from api.models.search import EventFeedback


class EventResult(BaseModel):
    """An event from search results."""

    id: str
    title: str
    date: str = Field(description="ISO 8601 datetime string")
    location: str
    category: str
    description: str
    is_free: bool
    price_amount: int | None = None
    distance_miles: float
    url: str | None = None


class RefinementInput(BaseModel):
    """Input for refine_results tool."""

    feedback: list[EventFeedback] = Field(description="User feedback on events")


class RefinementOutput(BaseModel):
    """Output from refine_results tool."""

    events: list[EventResult]
    explanation: str
    source: str = Field(
        default="refined", description="Data source: 'refined' or 'unavailable'"
    )


class SearchResult(BaseModel):
    """Result from search_events tool."""

    events: list[EventResult]
    source: str = Field(
        description="Data source(s): 'luma', 'eventbrite', 'luma+eventbrite', or 'unavailable'"
    )
    message: str | None = Field(
        default=None, description="User-facing message about data source"
    )
