"""Tests for orchestrator agent."""

from api.agents.orchestrator import (
    ORCHESTRATOR_INSTRUCTIONS_TEMPLATE,
    RefineInput,
    RefineResult,
    SimilarInput,
    SimilarResult,
    orchestrator_agent,
)
from api.models import EventResult


class TestOrchestratorAgent:
    """Test orchestrator agent configuration."""

    def test_agent_has_correct_model(self):
        """Agent should use gpt-4o."""
        assert orchestrator_agent.model == "gpt-4o"

    def test_agent_has_tools(self):
        """Agent should have search, refine, and similar tools."""
        tool_names = [tool.name for tool in orchestrator_agent.tools]
        assert "search_events" in tool_names
        assert "refine_results" in tool_names
        assert "find_similar" in tool_names

    def test_agent_has_output_type(self):
        """Agent should have OrchestratorResponse output type."""
        assert orchestrator_agent.output_type is not None


class TestOrchestratorPrompt:
    """Test orchestrator prompt content."""

    def test_prompt_includes_search_all_sources(self):
        """Prompt should emphasize searching all sources."""
        assert "ALL enabled event sources" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE
        assert "do not select sources" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE.lower()

    def test_prompt_includes_no_fabrication(self):
        """Prompt should include no fabrication rules."""
        assert "NEVER invent" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE

    def test_prompt_includes_phases(self):
        """Prompt should describe all phases."""
        assert "Clarification" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE
        assert "Search" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE
        assert "Refinement" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE

    def test_prompt_includes_grounding_rules(self):
        """Prompt should include grounding rules."""
        assert "CRITICAL RULES" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE
        assert "DO NOT List Events" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE
        assert "No Fabrication" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE

    def test_prompt_includes_response_format(self):
        """Prompt should describe response format."""
        assert "RESPONSE FORMAT" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE
        assert "message" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE
        assert "quick_picks" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE
        assert "events" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE

    def test_prompt_includes_no_results_handling(self):
        """Prompt should describe how to handle no results."""
        assert "No Results" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE or "no events" in ORCHESTRATOR_INSTRUCTIONS_TEMPLATE.lower()


class TestRefineInputModel:
    """Test RefineInput model validation."""

    def test_valid_refine_input_free_only(self):
        """Test RefineInput with free_only filter."""
        input_data = RefineInput(
            filter_type="free_only",
            free_only=True,
        )
        assert input_data.filter_type == "free_only"
        assert input_data.free_only is True

    def test_valid_refine_input_category(self):
        """Test RefineInput with category filter."""
        input_data = RefineInput(
            filter_type="category",
            categories=["ai", "startup"],
        )
        assert input_data.filter_type == "category"
        assert input_data.categories == ["ai", "startup"]

    def test_valid_refine_input_time(self):
        """Test RefineInput with time filter."""
        input_data = RefineInput(
            filter_type="time",
            after_time="2026-01-15T18:00:00",
            before_time="2026-01-15T23:59:59",
        )
        assert input_data.filter_type == "time"
        assert input_data.after_time == "2026-01-15T18:00:00"


class TestRefineResultModel:
    """Test RefineResult model validation."""

    def test_valid_refine_result(self):
        """Test RefineResult construction."""
        events = [
            EventResult(
                id="evt-001",
                title="Test Event",
                date="2026-01-10T18:00:00",
                location="Test Venue",
                category="ai",
                description="Test description",
                is_free=True,
                distance_miles=2.5,
            )
        ]
        result = RefineResult(
            events=events,
            original_count=5,
            filtered_count=1,
            explanation="Filtered to free events only",
        )
        assert len(result.events) == 1
        assert result.original_count == 5
        assert result.filtered_count == 1


class TestSimilarInputModel:
    """Test SimilarInput model validation."""

    def test_valid_similar_input(self):
        """Test SimilarInput construction."""
        input_data = SimilarInput(
            reference_event_id="evt-001",
            reference_title="AI Meetup",
            reference_category="ai",
            exclude_ids=["evt-001", "evt-002"],
            limit=5,
        )
        assert input_data.reference_event_id == "evt-001"
        assert input_data.reference_category == "ai"
        assert len(input_data.exclude_ids) == 2

    def test_similar_input_with_url(self):
        """Test SimilarInput with reference URL."""
        input_data = SimilarInput(
            reference_event_id="evt-001",
            reference_title="AI Meetup",
            reference_category="ai",
            reference_url="https://example.com/event/123",
        )
        assert input_data.reference_url == "https://example.com/event/123"


class TestSimilarResultModel:
    """Test SimilarResult model validation."""

    def test_valid_similar_result(self):
        """Test SimilarResult construction."""
        events = [
            EventResult(
                id="evt-003",
                title="Similar Event",
                date="2026-01-10T18:00:00",
                location="Test Venue",
                category="ai",
                description="Test description",
                is_free=True,
                distance_miles=2.5,
            )
        ]
        result = SimilarResult(
            events=events,
            reference_event_id="evt-001",
            similarity_basis="category:ai, keywords:['meetup', 'ai']",
        )
        assert len(result.events) == 1
        assert result.reference_event_id == "evt-001"
        assert "ai" in result.similarity_basis
