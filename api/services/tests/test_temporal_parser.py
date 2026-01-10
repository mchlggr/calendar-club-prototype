"""Tests for TemporalParser."""

from datetime import datetime

import pytest

from api.services.temporal_parser import TemporalParser, TemporalResult


class TestTemporalParser:
    """Test cases for TemporalParser."""

    @pytest.fixture
    def parser(self) -> TemporalParser:
        """Create a parser with America/New_York timezone."""
        return TemporalParser(user_timezone="America/New_York")

    def test_parse_this_weekend(self, parser: TemporalParser) -> None:
        """Test parsing 'this weekend'."""
        result = parser.parse("this weekend")

        assert result.success is True
        assert result.start is not None
        assert result.end is not None
        assert "weekend" in result.explanation.lower()
        assert "Friday" in result.explanation
        assert "Sunday" in result.explanation

    def test_parse_the_weekend(self, parser: TemporalParser) -> None:
        """Test parsing 'the weekend' (alias)."""
        result = parser.parse("the weekend")

        assert result.success is True
        assert result.start is not None
        assert result.end is not None

    def test_parse_tonight(self, parser: TemporalParser) -> None:
        """Test parsing 'tonight'."""
        result = parser.parse("tonight")

        assert result.success is True
        assert result.start is not None
        assert result.end is not None
        assert "tonight" in result.explanation.lower()
        assert "midnight" in result.explanation.lower()

    def test_parse_this_evening(self, parser: TemporalParser) -> None:
        """Test parsing 'this evening' (alias for tonight)."""
        result = parser.parse("this evening")

        assert result.success is True
        assert result.start is not None
        assert result.end is not None

    def test_parse_tomorrow_night(self, parser: TemporalParser) -> None:
        """Test parsing 'tomorrow night'."""
        result = parser.parse("tomorrow night")

        assert result.success is True
        assert result.start is not None
        assert result.end is not None
        assert "tomorrow night" in result.explanation.lower()
        assert "6:00 PM" in result.explanation

    def test_parse_next_day(self, parser: TemporalParser) -> None:
        """Test parsing 'next Thursday' style expressions."""
        result = parser.parse("next Thursday")

        assert result.success is True
        assert result.start is not None
        assert result.end is not None
        assert "Thursday" in result.explanation

    def test_parse_next_monday(self, parser: TemporalParser) -> None:
        """Test parsing 'next Monday'."""
        result = parser.parse("next Monday")

        assert result.success is True
        assert "Monday" in result.explanation

    def test_parse_dateparser_fallback(self, parser: TemporalParser) -> None:
        """Test that dateparser fallback works for expressions like 'in 3 days'."""
        result = parser.parse("in 3 days")

        assert result.success is True
        assert result.start is not None
        # dateparser should handle this

    def test_parse_unknown_expression(self, parser: TemporalParser) -> None:
        """Test that unknown expressions request clarification."""
        result = parser.parse("some random gibberish")

        assert result.success is False
        assert result.needs_clarification is True
        assert result.question is not None
        assert "gibberish" in result.question

    def test_result_includes_original_phrase(self, parser: TemporalParser) -> None:
        """Test that result always includes the original phrase."""
        result = parser.parse("tonight")
        assert result.original_phrase == "tonight"

        result = parser.parse("this weekend")
        assert result.original_phrase == "this weekend"

    def test_different_timezone(self) -> None:
        """Test parser with different timezone."""
        parser = TemporalParser(user_timezone="America/Los_Angeles")
        result = parser.parse("tonight")

        assert result.success is True
        # Should use Pacific timezone
        assert result.start is not None

    def test_weekend_returns_range(self, parser: TemporalParser) -> None:
        """Test that weekend returns a full date range (start and end)."""
        result = parser.parse("this weekend")

        assert result.start is not None
        assert result.end is not None

        # Parse the dates to verify the range is correct
        start = datetime.fromisoformat(result.start)
        end = datetime.fromisoformat(result.end)

        # Start should be Friday
        assert start.weekday() == 4  # Friday

        # End should be Sunday
        assert end.weekday() == 6  # Sunday

        # End should be 11:59 PM
        assert end.hour == 23
        assert end.minute == 59

    def test_case_insensitive(self, parser: TemporalParser) -> None:
        """Test that parsing is case insensitive."""
        result1 = parser.parse("THIS WEEKEND")
        result2 = parser.parse("This Weekend")
        result3 = parser.parse("this weekend")

        assert result1.success is True
        assert result2.success is True
        assert result3.success is True

    def test_with_extra_whitespace(self, parser: TemporalParser) -> None:
        """Test parsing with extra whitespace."""
        result = parser.parse("  this weekend  ")
        assert result.success is True

    def test_temporal_result_model(self) -> None:
        """Test TemporalResult Pydantic model."""
        result = TemporalResult(
            success=True,
            start="2026-01-09T18:00:00-05:00",
            end="2026-01-09T23:59:59-05:00",
            explanation="Test explanation",
            original_phrase="test",
        )

        assert result.success is True
        assert result.start == "2026-01-09T18:00:00-05:00"
        assert result.needs_clarification is False
        assert result.question is None

    def test_temporal_result_clarification(self) -> None:
        """Test TemporalResult with clarification needed."""
        result = TemporalResult(
            success=False,
            explanation="Could not understand",
            original_phrase="xyz",
            needs_clarification=True,
            question="Could you be more specific?",
        )

        assert result.success is False
        assert result.needs_clarification is True
        assert result.question is not None
