"""Output models for the orchestrator agent."""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.models.events import EventResult


class QuickPick(BaseModel):
    """A quick pick option for the user to select."""

    label: str = Field(description="Display text (2-4 words max)")
    value: str = Field(description="Value sent when clicked")


class OrchestratorResponse(BaseModel):
    """Structured response from the orchestrator agent."""

    message: str = Field(description="Conversational message to show the user")
    quick_picks: list[QuickPick] = Field(
        default_factory=list, description="Suggested quick picks [{label, value}]"
    )
    placeholder: str | None = Field(
        default=None, description="Placeholder text for chat input"
    )
    events: list[EventResult] = Field(
        default_factory=list,
        description="Events to display (from search or refinement)",
    )
    phase: str = Field(
        default="clarifying",
        description="Current phase: clarifying, searching, presenting, refining",
    )
