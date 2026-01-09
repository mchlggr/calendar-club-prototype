"""ICS calendar export service."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from icalendar import Calendar, Event
from pydantic import BaseModel


class CalendarEvent(BaseModel):
    """Event data for calendar export."""

    title: str
    start: datetime
    end: Optional[datetime] = None
    description: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None


def create_ics_event(event: CalendarEvent) -> str:
    """Create an ICS string for a single event."""
    cal = Calendar()
    cal.add("prodid", "-//Calendar Club//calendarclub.dev//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")

    ics_event = Event()
    ics_event.add("summary", event.title)
    ics_event.add("dtstart", event.start)

    if event.end:
        ics_event.add("dtend", event.end)
    else:
        # Default to 1 hour duration if no end time
        ics_event.add("dtend", event.start + timedelta(hours=1))

    if event.description:
        ics_event.add("description", event.description)

    if event.location:
        ics_event.add("location", event.location)

    if event.url:
        ics_event.add("url", event.url)

    # Add unique identifier
    uid = f"{event.start.isoformat()}-{event.title.replace(' ', '-').lower()}@calendarclub.dev"
    ics_event.add("uid", uid)

    # Add timestamp
    ics_event.add("dtstamp", datetime.now(timezone.utc))

    cal.add_component(ics_event)
    return cal.to_ical().decode("utf-8")


def create_ics_multiple(events: list[CalendarEvent]) -> str:
    """Create an ICS string for multiple events."""
    cal = Calendar()
    cal.add("prodid", "-//Calendar Club//calendarclub.dev//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")

    for event in events:
        ics_event = Event()
        ics_event.add("summary", event.title)
        ics_event.add("dtstart", event.start)

        if event.end:
            ics_event.add("dtend", event.end)
        else:
            ics_event.add("dtend", event.start + timedelta(hours=1))

        if event.description:
            ics_event.add("description", event.description)

        if event.location:
            ics_event.add("location", event.location)

        if event.url:
            ics_event.add("url", event.url)

        uid = f"{event.start.isoformat()}-{event.title.replace(' ', '-').lower()}@calendarclub.dev"
        ics_event.add("uid", uid)
        ics_event.add("dtstamp", datetime.now(timezone.utc))

        cal.add_component(ics_event)

    return cal.to_ical().decode("utf-8")
