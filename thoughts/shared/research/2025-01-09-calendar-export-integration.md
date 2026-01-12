---
date: 2025-01-09T12:00:00-05:00
researcher: michaelgeiger
git_commit: 57f41c8455cb7ffe52bb756c06d76fbd0a4f3ca6
branch: main
repository: mchlggr/calendar-club-prototype
topic: "Calendar Export & Integration Research for Phase 3"
tags: [research, calendar, ics, webcal, google-calendar, microsoft-graph, fastapi]
status: complete
last_updated: 2025-01-09
last_updated_by: michaelgeiger
---

# Research: Calendar Export & Integration for Calendar Club Phase 3

**Date**: 2025-01-09T12:00:00-05:00
**Researcher**: michaelgeiger
**Git Commit**: 57f41c8455cb7ffe52bb756c06d76fbd0a4f3ca6
**Branch**: main
**Repository**: mchlggr/calendar-club-prototype

## Research Question

Research modern Python approaches for implementing calendar export functionality for Calendar Club Phase 3:
- **MVP**: Downloadable .ics files and webcal subscription feeds
- **Stretch Goal**: Google and Microsoft Calendar API integration for push-to-calendar

Context: FastAPI backend, no payments involved, focus on developer experience.

---

## Executive Summary

For Calendar Club Phase 3, implement a **two-phase approach**:

### Phase 3a (MVP) - ICS Export
1. **Single event download**: Generate .ics files using the **icalendar** library (v6.3.2+)
2. **Webcal subscription feed**: Serve ICS feeds with proper caching headers (ETag, Last-Modified)

### Phase 3b (Stretch) - Calendar API Integration
1. **Google Calendar**: Use `google-api-python-client` + OAuth2, or async `gcal_sync` library
2. **Microsoft Outlook**: Use `msgraph-sdk-python` + MSAL for OAuth2

**Key Finding**: Calendar clients poll subscription feeds infrequently (Google: 12-24+ hours, Outlook: 3-24 hours). For real-time sync, direct API integration is required.

---

## Part 1: Python ICS Generation Libraries

### Recommended: icalendar (v6.3.2+)

The **icalendar** library is the industry standard for RFC 5545-compliant ICS generation in Python.

**Installation:**
```bash
pip install icalendar
```

**Why icalendar:**
- Most mature and actively maintained (since 2005)
- Full RFC 5545 compliance (UID, DTSTAMP, SEQUENCE handling)
- Python 3.8-3.13 support including PyPy
- Uses `zoneinfo` by default (Python 3.9+) for timezone handling
- BSD-2-Clause license

**Alternatives Evaluated:**

| Library | Status | Python Version | Notes |
|---------|--------|----------------|-------|
| **icalendar** | Active (v6.3.2, Nov 2025) | 3.8-3.13 | **Recommended** |
| **ics.py** | Inactive (v0.7.2, July 2022) | 3.6-3.8 | Simpler API but unmaintained |
| **ical** | Active (v12.1.2, Dec 2025) | 3.13+ only | Modern but version requirement too strict |

### Single Event Download Example

```python
from icalendar import Calendar, Event
from datetime import datetime
import zoneinfo
import uuid

def create_event_ics(
    title: str,
    description: str,
    start: datetime,
    end: datetime,
    location: str = "",
    timezone: str = "America/New_York"
) -> bytes:
    """Generate downloadable .ics file for a single event."""

    cal = Calendar()
    cal.add('prodid', '-//Calendar Club//calendarclub.app//')
    cal.add('version', '2.0')

    tz = zoneinfo.ZoneInfo(timezone)
    utc = zoneinfo.ZoneInfo('UTC')

    event = Event()
    event.add('summary', title)
    event.add('description', description)
    event.add('uid', f"{uuid.uuid4()}@calendarclub.app")  # Stable UID
    event.add('dtstamp', datetime.now(utc))  # RFC 5545 required
    event.add('dtstart', start.replace(tzinfo=tz))
    event.add('dtend', end.replace(tzinfo=tz))
    event.add('location', location)
    event.add('sequence', 0)
    event.add('status', 'CONFIRMED')

    cal.add_component(event)
    return cal.to_ical()
```

### FastAPI Endpoint for Event Download

```python
from fastapi import FastAPI, Response
from datetime import datetime

app = FastAPI()

@app.get("/events/{event_id}/download.ics")
async def download_event(event_id: str):
    """Download a single event as .ics file."""

    # Fetch event from database
    event = await get_event_by_id(event_id)

    ics_content = create_event_ics(
        title=event.title,
        description=event.description,
        start=event.start_time,
        end=event.end_time,
        location=event.location
    )

    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{event.slug}.ics"'
        }
    )
```

---

## Part 2: Webcal Subscription Feeds

### How Webcal Works

The `webcal://` URI scheme signals to browsers/apps that a URL should trigger a **calendar subscription** rather than a file download. The actual data transfer uses HTTPS.

**Protocol Conversion:**
- `https://example.com/calendar.ics` → `webcal://example.com/calendar.ics`

### Required HTTP Headers

```python
headers = {
    "Content-Type": "text/calendar; charset=utf-8",
    "Content-Disposition": "inline; filename=calendar.ics",
    "Cache-Control": "max-age=3600, must-revalidate",
    "ETag": generate_etag(calendar_content),
    "Last-Modified": last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT'),
    "Vary": "Accept-Encoding"
}
```

**Why ETag is Critical:**
- Enables `304 Not Modified` responses (bandwidth savings)
- Clients send `If-None-Match` header with cached ETag
- Generate from content hash: `md5(calendar_data).hexdigest()`

### Stable UIDs (Critical for Avoiding Duplicates)

**The #1 cause of duplicate events is changing UIDs on updates.**

```python
import uuid

# CORRECT: Generate once at event creation, never change
uid = f"{uuid.uuid4().hex}@calendarclub.app"

# Event structure with stable UID
event_data = {
    'uid': uid,              # Never change after creation
    'dtstamp': datetime.now(utc),  # Update on every generation
    'sequence': 0,           # Increment on updates
    # ...
}
```

**UID Best Practices (RFC 7986):**
- Use hex-encoded UUID v4
- Append domain: `{uuid}@yourdomain.com`
- Never include PII or internal IDs in UID
- Max 255 characters

### SEQUENCE for Update Semantics

```python
# Initial event
event.add('sequence', 0)

# After first update (time changed, location changed, etc.)
event.add('sequence', 1)

# After second update
event.add('sequence', 2)
```

**When to increment SEQUENCE:**
- Change to date/time (DTSTART, DTEND)
- Change to location
- Change to summary/description
- Status changes (CANCELLED, CONFIRMED)

**When NOT to increment:**
- Updating DTSTAMP alone
- Regenerating the feed without content changes

### Calendar Client Polling Frequencies

| Client | Polling Frequency | User Control |
|--------|------------------|--------------|
| **Google Calendar** | 12-24+ hours | None |
| **Apple Calendar** | Default weekly, configurable to 5 min | Yes |
| **Outlook.com** | Every 3 hours | No |
| **Outlook Desktop** | 3-24 hours | Limited |

**Implication:** Webcal feeds are inherently delayed. For real-time updates, use direct API integration.

### Complete Webcal Feed Endpoint

```python
from fastapi import FastAPI, Response, Request
from icalendar import Calendar, Event
from datetime import datetime
import zoneinfo
import hashlib

app = FastAPI()

def generate_etag(content: str) -> str:
    return f'"{hashlib.md5(content.encode()).hexdigest()}"'

@app.get("/calendar/feed.ics")
async def calendar_subscription_feed(request: Request):
    """
    Webcal subscription feed.
    Subscribe: webcal://yourdomain.com/calendar/feed.ics
    """

    # Check conditional request headers
    if_none_match = request.headers.get('if-none-match')

    # Build calendar
    cal = Calendar()
    cal.add('prodid', '-//Calendar Club//calendarclub.app//')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    cal.add('x-wr-calname', 'Calendar Club Events')
    cal.add('x-wr-timezone', 'America/New_York')
    cal.add('refresh-interval;value=duration', 'PT1H')  # RFC 7986

    # Fetch events from database
    events = await get_upcoming_events()

    tz = zoneinfo.ZoneInfo('America/New_York')
    utc = zoneinfo.ZoneInfo('UTC')

    for event_data in events:
        event = Event()
        event.add('summary', event_data['title'])
        event.add('description', event_data['description'])
        event.add('uid', event_data['uid'])  # Must be stable!
        event.add('dtstamp', datetime.now(utc))
        event.add('dtstart', event_data['start'].replace(tzinfo=tz))
        event.add('dtend', event_data['end'].replace(tzinfo=tz))
        event.add('location', event_data.get('location', ''))
        event.add('sequence', event_data.get('version', 0))
        event.add('status', event_data.get('status', 'CONFIRMED'))
        event.add('url', event_data.get('rsvp_url', ''))
        cal.add_component(event)

    calendar_data = cal.to_ical().decode('utf-8')
    etag = generate_etag(calendar_data)

    # Return 304 if content unchanged
    if if_none_match == etag:
        return Response(status_code=304)

    return Response(
        content=calendar_data,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": "inline; filename=calendar.ics",
            "Cache-Control": "max-age=900, must-revalidate",
            "ETag": etag,
            "Vary": "Accept-Encoding"
        }
    )
```

### Event Deletion in Feeds

Use `STATUS:CANCELLED` instead of removing events:

```python
# Mark as cancelled (keep in feed for 30 days)
event.add('status', 'CANCELLED')
event.add('sequence', previous_sequence + 1)

# After 30 days, remove from feed entirely
```

---

## Part 3: Google Calendar API Integration (Stretch Goal)

### Setup Requirements

1. **Google Cloud Console**: Create project, enable Calendar API
2. **OAuth Consent Screen**: Configure app info, scopes, test users
3. **Credentials**: Create OAuth 2.0 client ID (Web application)

### Required Libraries

```bash
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### OAuth Scopes

| Scope | Access Level |
|-------|-------------|
| `calendar.readonly` | Read events (for conflict detection) |
| `calendar` | Full read/write access |
| `calendar.events` | View and edit events on all calendars |

### OAuth Flow in FastAPI

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
import httpx
import os

app = FastAPI()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8000/auth/google/callback"
SCOPES = ["openid", "email", "https://www.googleapis.com/auth/calendar"]

@app.get("/auth/google/login")
async def google_login():
    """Redirect to Google OAuth consent screen."""
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"response_type=code&"
        f"scope={' '.join(SCOPES)}&"
        f"access_type=offline&"
        f"prompt=consent"
    )
    return RedirectResponse(auth_url)

@app.get("/auth/google/callback")
async def google_callback(code: str, request: Request):
    """Exchange authorization code for tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

        if response.status_code != 200:
            raise HTTPException(400, "Token exchange failed")

        token_data = response.json()

        # Store tokens in database
        # token_data["access_token"], token_data["refresh_token"]

        return {"message": "Successfully connected Google Calendar"}
```

### Creating Events in Google Calendar

```python
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def push_event_to_google(
    access_token: str,
    summary: str,
    start: datetime,
    end: datetime,
    description: str = "",
    location: str = ""
):
    """Create event in user's Google Calendar."""

    credentials = Credentials(token=access_token)
    service = build("calendar", "v3", credentials=credentials)

    event = {
        'summary': summary,
        'description': description,
        'location': location,
        'start': {
            'dateTime': start.isoformat(),
            'timeZone': 'America/New_York',
        },
        'end': {
            'dateTime': end.isoformat(),
            'timeZone': 'America/New_York',
        },
    }

    created_event = service.events().insert(
        calendarId='primary',
        body=event
    ).execute()

    return created_event
```

### Async Alternative: gcal_sync Library

For async FastAPI applications, consider `gcal_sync` (v6.2.0, Jan 2025):

```bash
pip install gcal-sync
```

```python
import aiohttp
from gcal_sync.api import GoogleCalendarService

async def list_events_async(access_token: str):
    async with aiohttp.ClientSession() as session:
        # Custom auth implementation
        service = GoogleCalendarService(auth)
        events = await service.async_list_events(request)
        return events
```

### Rate Limits

- **Daily**: 1,000,000 queries per project
- **Per-minute**: Varies by operation
- **Error code**: `403` or `429` with exponential backoff

---

## Part 4: Microsoft Graph Calendar API (Stretch Goal)

### Setup Requirements

1. **Azure Portal**: Register app in Microsoft Entra (Azure AD)
2. **API Permissions**: Add `Calendars.ReadWrite` delegated permission
3. **Client Secret**: Create in Certificates & secrets

### Required Libraries

```bash
pip install msgraph-sdk msal azure-identity
```

### OAuth Scopes

| Scope | Access Level |
|-------|-------------|
| `Calendars.Read` | Read calendars |
| `Calendars.ReadWrite` | Create, update, delete events |
| `Calendars.ReadWrite.Shared` | Access shared calendars |

### OAuth Flow in FastAPI

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
import msal
import os

app = FastAPI()

CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
TENANT_ID = os.getenv("AZURE_TENANT_ID", "common")
REDIRECT_URI = "http://localhost:8000/auth/microsoft/callback"
SCOPES = ["Calendars.ReadWrite", "User.Read"]

def get_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET
    )

@app.get("/auth/microsoft/login")
async def microsoft_login(request: Request):
    """Redirect to Microsoft OAuth consent screen."""
    msal_app = get_msal_app()
    auth_url = msal_app.get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        state="random_state"
    )
    return RedirectResponse(auth_url)

@app.get("/auth/microsoft/callback")
async def microsoft_callback(code: str, request: Request):
    """Exchange authorization code for tokens."""
    msal_app = get_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code=code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    if "access_token" in result:
        # Store tokens in database
        return {"message": "Successfully connected Microsoft Calendar"}
    else:
        raise HTTPException(400, result.get("error_description", "Auth failed"))
```

### Creating Events via Microsoft Graph

```python
from msgraph import GraphServiceClient
from msgraph.generated.models.event import Event
from msgraph.generated.models.date_time_time_zone import DateTimeTimeZone
from google.oauth2.credentials import Credentials

async def push_event_to_outlook(
    access_token: str,
    summary: str,
    start: datetime,
    end: datetime,
    description: str = "",
    location: str = ""
):
    """Create event in user's Outlook Calendar."""

    # Create credential provider
    class TokenCredential:
        def __init__(self, token):
            self.token = token
        async def get_token(self, *scopes, **kwargs):
            from azure.core.credentials import AccessToken
            return AccessToken(self.token, int(datetime.now().timestamp()) + 3600)

    credential = TokenCredential(access_token)
    graph_client = GraphServiceClient(credentials=credential, scopes=["Calendars.ReadWrite"])

    new_event = Event(
        subject=summary,
        body=ItemBody(content_type=BodyType.Text, content=description),
        start=DateTimeTimeZone(date_time=start.isoformat(), time_zone="Eastern Standard Time"),
        end=DateTimeTimeZone(date_time=end.isoformat(), time_zone="Eastern Standard Time"),
        location=Location(display_name=location) if location else None
    )

    created = await graph_client.me.calendar.events.post(new_event)
    return created
```

### Rate Limits

- HTTP `429` response with `Retry-After` header
- Implement exponential backoff
- Use delta queries instead of polling

---

## Part 5: Comparison - Google vs Microsoft

| Aspect | Google Calendar | Microsoft Graph |
|--------|----------------|-----------------|
| **Registration** | Google Cloud Console | Azure Portal |
| **Auth Library** | google-auth-oauthlib | msal |
| **API SDK** | google-api-python-client | msgraph-sdk-python |
| **Async Support** | Via gcal_sync | Native in SDK |
| **Date Format** | RFC 3339 | ISO 8601 + timezone |
| **Pagination** | `nextPageToken` | `@odata.nextLink` |
| **Filtering** | Query parameters | OData ($filter, $select) |

### Common Pattern for Both

```python
# Abstract interface for multi-provider support
class CalendarProvider:
    async def authenticate(self, auth_code: str) -> dict:
        """Exchange auth code for tokens."""
        raise NotImplementedError

    async def create_event(self, event_data: dict) -> dict:
        """Push event to calendar."""
        raise NotImplementedError

    async def get_free_busy(self, start: datetime, end: datetime) -> list:
        """Get busy periods for conflict detection."""
        raise NotImplementedError

class GoogleCalendarProvider(CalendarProvider):
    # Implementation using google-api-python-client
    pass

class MicrosoftCalendarProvider(CalendarProvider):
    # Implementation using msgraph-sdk-python
    pass
```

---

## Implementation Recommendations

### Phase 3a MVP (Week 1-2)

1. **Add icalendar dependency**: `pip install icalendar`
2. **Implement download endpoint**: `/events/{id}/download.ics`
3. **Implement subscription feed**: `/calendar/feed.ics`
4. **Add webcal:// link generation** in frontend
5. **Ensure stable UIDs** stored with events

### Phase 3b Stretch (Week 3-4)

1. **Google OAuth flow** with token storage
2. **Microsoft OAuth flow** with token storage
3. **"Add to Calendar" button** with provider selection
4. **Token refresh middleware** for both providers

### Database Schema Additions

```sql
-- User calendar connections
CREATE TABLE user_calendar_connections (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    provider VARCHAR(20) NOT NULL,  -- 'google' or 'microsoft'
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_expires_at TIMESTAMP WITH TIME ZONE,
    scope TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Events need stable UIDs
ALTER TABLE events ADD COLUMN calendar_uid VARCHAR(255) UNIQUE;
```

---

## Code References

### Python Libraries
- [icalendar Documentation](https://icalendar.readthedocs.io/)
- [icalendar PyPI](https://pypi.org/project/icalendar/)
- [gcal_sync GitHub](https://github.com/allenporter/gcal_sync)
- [msgraph-sdk-python GitHub](https://github.com/microsoftgraph/msgraph-sdk-python)

### RFC Standards
- [RFC 5545 - iCalendar Specification](https://datatracker.ietf.org/doc/html/rfc5545)
- [RFC 7986 - New Properties for iCalendar](https://datatracker.ietf.org/doc/html/rfc7986)

### Google Calendar
- [Google Calendar API Overview](https://developers.google.com/calendar/api/guides/overview)
- [Python Quickstart](https://developers.google.com/workspace/calendar/api/quickstart/python)
- [OAuth 2.0 for Web Server Apps](https://developers.google.com/identity/protocols/oauth2/web-server)

### Microsoft Graph
- [Microsoft Graph Calendar Overview](https://learn.microsoft.com/en-us/graph/outlook-calendar-concept-overview)
- [msgraph-sdk-python samples](https://github.com/microsoftgraph/msgraph-sdk-python/blob/main/docs/general_samples.md)
- [MSAL for Python](https://learn.microsoft.com/en-us/entra/msal/python/)

### Testing Tools
- [Graph Explorer (Microsoft)](https://developer.microsoft.com/graph/graph-explorer)
- [OAuth 2.0 Playground (Google)](https://developers.google.com/oauthplayground/)

---

## Open Questions

1. **Token Storage**: Should we use encrypted database columns or a secret manager (Vercel environment variables) for OAuth tokens?

2. **Multi-Calendar Support**: Should users be able to connect both Google AND Microsoft accounts simultaneously?

3. **Read-Only vs Write**: The roadmap mentions read-only calendar integration initially. Should the stretch goal skip write operations and focus only on free/busy conflict detection?

4. **Refresh Token Strategy**: How should we handle refresh token expiration (Google tokens expire for apps in "testing" mode after 7 days)?
