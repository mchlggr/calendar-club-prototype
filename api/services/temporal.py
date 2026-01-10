"""
TemporalParser for natural language date/time expressions.

Uses dateparser library with custom handlers for range expressions
like "this weekend", "tonight", "tomorrow night".
"""

from datetime import datetime, timedelta
from typing import Any, Callable, TypedDict, cast
from zoneinfo import ZoneInfo

import dateparser


class TemporalResult(TypedDict, total=False):
    """Result of temporal parsing."""

    success: bool
    start: str | None
    end: str | None
    explanation: str
    original_phrase: str
    needs_clarification: bool
    question: str


class TemporalParser:
    """Parse natural language temporal expressions."""

    def __init__(self, user_timezone: str = "America/New_York"):
        self.tz = ZoneInfo(user_timezone)
        self.settings: dict[str, Any] = {
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": user_timezone,
            "RETURN_AS_TIMEZONE_AWARE": True,
        }

        # Custom handlers for range expressions
        self.range_handlers: dict[str, Callable[[], TemporalResult]] = {
            "this weekend": self._parse_weekend,
            "tomorrow night": self._parse_tomorrow_night,
            "tonight": self._parse_tonight,
        }

    def parse(self, user_input: str) -> TemporalResult:
        """Parse temporal expression, return structured result with explanation."""
        user_input_lower = user_input.lower()

        # Try custom range handlers first
        for phrase, handler in self.range_handlers.items():
            if phrase in user_input_lower:
                return handler()

        # Fall back to dateparser
        result = dateparser.parse(user_input, settings=cast(Any, self.settings))

        if result:
            return {
                "success": True,
                "start": result.isoformat(),
                "end": None,
                "explanation": f"Interpreted as {result.strftime('%A, %B %d at %I:%M %p %Z')}",
                "original_phrase": user_input,
            }

        # Could not parse - needs clarification
        return {
            "success": False,
            "needs_clarification": True,
            "question": f'Could you be more specific about "{user_input}"?',
            "original_phrase": user_input,
        }

    def _parse_weekend(self) -> TemporalResult:
        """Friday 4pm - Sunday 11:59pm."""
        now = datetime.now(self.tz)
        days_until_friday = (4 - now.weekday()) % 7
        if days_until_friday == 0 and now.hour >= 16:
            days_until_friday = 7

        friday = (now + timedelta(days=days_until_friday)).replace(
            hour=16, minute=0, second=0, microsecond=0
        )
        sunday = friday + timedelta(days=2)
        sunday = sunday.replace(hour=23, minute=59, second=59)

        return {
            "success": True,
            "start": friday.isoformat(),
            "end": sunday.isoformat(),
            "explanation": f"Interpreted 'this weekend' as {friday.strftime('%A %I:%M %p')} through {sunday.strftime('%A %I:%M %p')}",
            "original_phrase": "this weekend",
        }

    def _parse_tomorrow_night(self) -> TemporalResult:
        """Tomorrow 6pm - midnight."""
        now = datetime.now(self.tz)
        tomorrow = (now + timedelta(days=1)).replace(
            hour=18, minute=0, second=0, microsecond=0
        )
        midnight = tomorrow.replace(hour=23, minute=59, second=59)

        return {
            "success": True,
            "start": tomorrow.isoformat(),
            "end": midnight.isoformat(),
            "explanation": f"Interpreted 'tomorrow night' as {tomorrow.strftime('%A')} 6:00 PM to midnight",
            "original_phrase": "tomorrow night",
        }

    def _parse_tonight(self) -> TemporalResult:
        """Today 6pm - midnight."""
        now = datetime.now(self.tz)
        start = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now.hour >= 18:
            start = now
        end = now.replace(hour=23, minute=59, second=59)

        return {
            "success": True,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "explanation": f"Interpreted 'tonight' as {start.strftime('%I:%M %p')} to midnight",
            "original_phrase": "tonight",
        }


# Default parser instance
temporal_parser = TemporalParser()
