"""Conversation models for LLM-orchestrated discovery chat."""

from pydantic import BaseModel, Field

from .search import SearchProfile


class QuickPickOption(BaseModel):
    """A quick pick option for the user to select."""

    label: str = Field(description="Display text (2-4 words max)")
    value: str = Field(description="Value sent when clicked")


class AgentTurnResponse(BaseModel):
    """Structured response from the clarifying agent."""

    message: str = Field(description="Conversational message (already streamed)")
    quick_picks: list[QuickPickOption] = Field(
        default_factory=list,
        description="Suggested quick picks for the user to select",
    )
    placeholder: str | None = Field(
        default=None,
        description="Suggested placeholder text for the chat input (e.g., 'Tell me more about timing...')",
    )
    ready_to_search: bool = Field(
        default=False,
        description="Whether we have enough info to search for events",
    )
    search_profile: SearchProfile | None = Field(
        default=None,
        description="Built search profile when ready_to_search is True",
    )
