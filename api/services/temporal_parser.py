"""
Temporal Parser for natural language date expressions.

Parses expressions like 'next Thursday', 'this weekend', 'tomorrow night'
into structured date ranges for discovery queries.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import dateparser
from pydantic import BaseModel
from zoneinfo import ZoneInfo

# Day name to weekday number (Monday=0, Sunday=6)
_DAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


class TemporalResult(BaseModel):
    """Result of parsing a temporal expression."""

    success: bool
    start: str | None = None
    end: str | None = None
    explanation: str
    original_phrase: str
    needs_clarification: bool = False
    question: str | None = None


class TemporalParser:
    """
    Parse natural language temporal expressions into structured date ranges.

    Uses dateparser library with custom handlers for common range expressions
    like 'this weekend', 'tomorrow night', 'tonight'.
    """

    def __init__(self, user_timezone: str = "America/New_York") -> None:
        self.tz = ZoneInfo(user_timezone)
        self.settings: dict[str, Any] = {
            "PREFER_DATES_FROM": "future",
            "TIMEZONE": user_timezone,
            "RETURN_AS_TIMEZONE_AWARE": True,
        }

        # Custom handlers for range expressions
        self._range_handlers: dict[str, Callable[[], TemporalResult]] = {
            "this weekend": self._parse_weekend,
            "the weekend": self._parse_weekend,
            "weekend": self._parse_weekend,
            "tomorrow night": self._parse_tomorrow_night,
            "tonight": self._parse_tonight,
            "this evening": self._parse_tonight,
        }

    def parse(self, user_input: str) -> TemporalResult:
        """
        Parse temporal expression, return structured result with explanation.

        Args:
            user_input: Natural language date/time expression

        Returns:
            TemporalResult with parsed dates and human-readable explanation
        """
        user_input_lower = user_input.lower().strip()

        # Try custom range handlers first
        for phrase, handler in self._range_handlers.items():
            if phrase in user_input_lower:
                return handler()

        # Try "next <day>" pattern
        next_day_result = self._parse_next_day(user_input_lower)
        if next_day_result:
            return next_day_result

        # Fall back to dateparser for other expressions
        result = dateparser.parse(user_input, settings=self.settings)

        if result:
            return TemporalResult(
                success=True,
                start=result.isoformat(),
                end=None,
                explanation=f"Interpreted as {result.strftime('%A, %B %d at %I:%M %p %Z')}",
                original_phrase=user_input,
            )

        # If parsing failed, request clarification
        return TemporalResult(
            success=False,
            explanation=f'Could not understand "{user_input}"',
            original_phrase=user_input,
            needs_clarification=True,
            question=f'Could you be more specific about "{user_input}"? For example, "this Saturday" or "tomorrow at 7pm".',
        )

    def _parse_weekend(self) -> TemporalResult:
        """Parse 'this weekend' as Friday 4pm - Sunday 11:59pm."""
        now = datetime.now(self.tz)
        days_until_friday = (4 - now.weekday()) % 7
        if days_until_friday == 0 and now.hour >= 16:
            # It's Friday after 4pm, use next weekend
            days_until_friday = 7

        friday = (now + timedelta(days=days_until_friday)).replace(
            hour=16, minute=0, second=0, microsecond=0
        )
        sunday = friday + timedelta(days=2)
        sunday = sunday.replace(hour=23, minute=59, second=59)

        return TemporalResult(
            success=True,
            start=friday.isoformat(),
            end=sunday.isoformat(),
            explanation=f"Interpreted 'this weekend' as {friday.strftime('%A %I:%M %p')} through {sunday.strftime('%A %I:%M %p')}",
            original_phrase="this weekend",
        )

    def _parse_tomorrow_night(self) -> TemporalResult:
        """Parse 'tomorrow night' as tomorrow 6pm - midnight."""
        now = datetime.now(self.tz)
        tomorrow = (now + timedelta(days=1)).replace(
            hour=18, minute=0, second=0, microsecond=0
        )
        midnight = tomorrow.replace(hour=23, minute=59, second=59)

        return TemporalResult(
            success=True,
            start=tomorrow.isoformat(),
            end=midnight.isoformat(),
            explanation=f"Interpreted 'tomorrow night' as {tomorrow.strftime('%A')} 6:00 PM to midnight",
            original_phrase="tomorrow night",
        )

    def _parse_tonight(self) -> TemporalResult:
        """Parse 'tonight' as today 6pm - midnight."""
        now = datetime.now(self.tz)
        start = now.replace(hour=18, minute=0, second=0, microsecond=0)
        if now.hour >= 18:
            # Already evening, start from now
            start = now.replace(second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)

        return TemporalResult(
            success=True,
            start=start.isoformat(),
            end=end.isoformat(),
            explanation=f"Interpreted 'tonight' as {start.strftime('%I:%M %p')} to midnight",
            original_phrase="tonight",
        )

    def _parse_next_day(self, user_input: str) -> TemporalResult | None:
        """Parse 'next <day>' pattern, e.g., 'next Thursday'."""
        # Match "next <day>" pattern
        match = re.search(r"\bnext\s+(\w+)", user_input)
        if not match:
            return None

        day_name = match.group(1).lower()
        if day_name not in _DAY_NAMES:
            return None

        target_weekday = _DAY_NAMES[day_name]
        now = datetime.now(self.tz)
        current_weekday = now.weekday()

        # Calculate days until the target day
        # "next <day>" always means the occurrence in the next week
        days_until = (target_weekday - current_weekday) % 7
        if days_until == 0:
            # Same day, go to next week
            days_until = 7
        elif days_until <= (6 - current_weekday):
            # Target is later this week, add 7 for "next"
            days_until += 7

        target_date = (now + timedelta(days=days_until)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        return TemporalResult(
            success=True,
            start=target_date.isoformat(),
            end=target_date.replace(hour=23, minute=59, second=59).isoformat(),
            explanation=f"Interpreted 'next {day_name.title()}' as {target_date.strftime('%A, %B %d')}",
            original_phrase=f"next {day_name}",
        )
