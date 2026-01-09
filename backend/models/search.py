"""
Pydantic models for search and discovery workflows.

These models support:
- Phase 1: Clarifying questions -> SearchProfile
- Phase 2: Taste calibration with Yes/No/Maybe ratings
"""

from enum import Enum
from typing import Union

from pydantic import BaseModel, Field


class EventCategory(str, Enum):
    """Event categories for filtering."""

    STARTUP = "startup"
    AI = "ai"
    COMMUNITY = "community"


class TimeOfDay(str, Enum):
    """Time of day preferences."""

    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class DateWindow(BaseModel):
    """Time window for event search."""

    start: str = Field(description="ISO 8601 datetime string")
    end: str = Field(description="ISO 8601 datetime string")
    original_phrase: str = Field(
        description="User's original phrase, e.g., 'this weekend'"
    )


class Constraints(BaseModel):
    """Search constraints from user preferences."""

    free_only: bool
    max_distance_miles: Union[int, None]
    time_of_day: Union[TimeOfDay, None]


class SearchProfile(BaseModel):
    """Structured search profile built from clarifying questions."""

    location: Union[str, None] = None
    date_window: Union[DateWindow, None] = None
    categories: list[EventCategory] = Field(default_factory=list)
    constraints: Union[Constraints, None] = None


class Rating(str, Enum):
    """User rating for event feedback."""

    YES = "yes"
    NO = "no"
    MAYBE = "maybe"


class EventFeedback(BaseModel):
    """User feedback on a specific event."""

    event_id: str
    rating: Rating
    reason: Union[str, None] = None  # "too far", "too expensive", "wrong vibe"
