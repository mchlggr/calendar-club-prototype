"""Tests for agent prompt integrity."""

from api.agents.clarifying import CLARIFYING_AGENT_INSTRUCTIONS, clarifying_agent
from api.agents.search import SEARCH_AGENT_INSTRUCTIONS, search_agent


class TestClarifyingAgentPrompt:
    """Test ClarifyingAgent prompt content."""

    def test_prompt_includes_grounding_rules(self):
        """Prompt should include grounding rules."""
        assert "CRITICAL RULES" in CLARIFYING_AGENT_INSTRUCTIONS
        assert (
            "No Fabrication" in CLARIFYING_AGENT_INSTRUCTIONS
            or "NEVER invent" in CLARIFYING_AGENT_INSTRUCTIONS
        )

    def test_prompt_includes_location_default(self):
        """Prompt should specify default location."""
        assert "Columbus" in CLARIFYING_AGENT_INSTRUCTIONS

    def test_prompt_includes_temporal_interpretation(self):
        """Prompt should guide temporal interpretation."""
        assert "this weekend" in CLARIFYING_AGENT_INSTRUCTIONS
        assert "Friday" in CLARIFYING_AGENT_INSTRUCTIONS

    def test_agent_has_correct_model(self):
        """Agent should use gpt-4o."""
        assert clarifying_agent.model == "gpt-4o"

    def test_agent_has_output_type(self):
        """Agent should have SearchProfile output type."""
        assert clarifying_agent.output_type is not None


class TestSearchAgentPrompt:
    """Test SearchAgent prompt content."""

    def test_prompt_includes_source_attribution(self):
        """Prompt should require source attribution."""
        assert "source" in SEARCH_AGENT_INSTRUCTIONS.lower()
        assert "demo" in SEARCH_AGENT_INSTRUCTIONS.lower()

    def test_prompt_includes_zero_result_handling(self):
        """Prompt should handle zero results."""
        assert (
            "empty" in SEARCH_AGENT_INSTRUCTIONS.lower()
            or "no events" in SEARCH_AGENT_INSTRUCTIONS.lower()
        )

    def test_prompt_prohibits_fabrication(self):
        """Prompt should prohibit making up events."""
        assert (
            "NEVER" in SEARCH_AGENT_INSTRUCTIONS
            or "never" in SEARCH_AGENT_INSTRUCTIONS.lower()
        )
        assert (
            "fabricat" in SEARCH_AGENT_INSTRUCTIONS.lower()
            or "invent" in SEARCH_AGENT_INSTRUCTIONS.lower()
        )

    def test_agent_has_tools(self):
        """Agent should have search and refine tools."""
        tool_names = [tool.name for tool in search_agent.tools]
        assert "search_events" in tool_names
        assert "refine_results" in tool_names

    def test_agent_has_correct_model(self):
        """Agent should use gpt-4o."""
        assert search_agent.model == "gpt-4o"
