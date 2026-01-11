"""
Microsoft Graph Calendar integration for Outlook sync.

Provides OAuth2 authentication via MSAL and calendar operations
using the Microsoft Graph API.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
import msal
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Microsoft Graph API endpoints
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_CALENDAR_ENDPOINT = f"{GRAPH_API_BASE}/me/calendar/events"

# Required scopes for calendar access
CALENDAR_SCOPES = [
    "Calendars.ReadWrite",
    "User.Read",
]


class OutlookEvent(BaseModel):
    """Event data for Outlook calendar."""

    id: str | None = None
    title: str
    start: datetime
    end: datetime | None = None
    description: str | None = None
    location: str | None = None
    url: str | None = None
    is_all_day: bool = False
    time_zone: str = "UTC"


class TokenInfo(BaseModel):
    """OAuth token information."""

    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    id_token: str | None = None


class MSGraphAuth:
    """
    Microsoft Authentication Library (MSAL) wrapper for OAuth2 flows.

    Supports:
    - Authorization code flow (web apps)
    - Token refresh

    Required environment variables:
    - MSGRAPH_CLIENT_ID: Azure AD application (client) ID
    - MSGRAPH_CLIENT_SECRET: Azure AD client secret
    - MSGRAPH_TENANT_ID: Azure AD tenant ID (or 'common' for multi-tenant)
    - MSGRAPH_REDIRECT_URI: OAuth redirect URI
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        tenant_id: str | None = None,
        redirect_uri: str | None = None,
    ):
        self.client_id = client_id or os.getenv("MSGRAPH_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("MSGRAPH_CLIENT_SECRET", "")
        self.tenant_id = tenant_id or os.getenv("MSGRAPH_TENANT_ID", "common")
        self.redirect_uri = redirect_uri or os.getenv(
            "MSGRAPH_REDIRECT_URI", "http://localhost:3000/auth/callback"
        )

        self._app: msal.ConfidentialClientApplication | None = None

    def _get_app(self) -> msal.ConfidentialClientApplication:
        """Get or create the MSAL application instance."""
        if self._app is None:
            if not self.client_id or not self.client_secret:
                raise ValueError(
                    "MSGRAPH_CLIENT_ID and MSGRAPH_CLIENT_SECRET must be configured"
                )

            authority = f"https://login.microsoftonline.com/{self.tenant_id}"
            self._app = msal.ConfidentialClientApplication(
                client_id=self.client_id,
                client_credential=self.client_secret,
                authority=authority,
            )
        return self._app

    def get_auth_url(self, state: str | None = None) -> str:
        """
        Get the authorization URL for the OAuth2 flow.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            Authorization URL to redirect the user to
        """
        app = self._get_app()
        auth_url = app.get_authorization_request_url(
            scopes=CALENDAR_SCOPES,
            redirect_uri=self.redirect_uri,
            state=state,
        )
        return auth_url

    def exchange_code(self, code: str) -> TokenInfo:
        """
        Exchange an authorization code for tokens.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            TokenInfo with access token and optional refresh token
        """
        app = self._get_app()
        result = app.acquire_token_by_authorization_code(
            code=code,
            scopes=CALENDAR_SCOPES,
            redirect_uri=self.redirect_uri,
        )

        if "error" in result:
            raise ValueError(
                f"Token exchange failed: {result.get('error_description', result.get('error'))}"
            )

        expires_at = None
        if "expires_in" in result:
            expires_at = datetime.now(timezone.utc).replace(
                microsecond=0
            ) + __import__("datetime").timedelta(seconds=result["expires_in"])

        return TokenInfo(
            access_token=result["access_token"],
            refresh_token=result.get("refresh_token"),
            expires_at=expires_at,
            id_token=result.get("id_token"),
        )

    def refresh_token(self, refresh_token: str) -> TokenInfo:
        """
        Refresh an access token using a refresh token.

        Args:
            refresh_token: The refresh token

        Returns:
            TokenInfo with new access token
        """
        app = self._get_app()
        result = app.acquire_token_by_refresh_token(
            refresh_token=refresh_token,
            scopes=CALENDAR_SCOPES,
        )

        if "error" in result:
            raise ValueError(
                f"Token refresh failed: {result.get('error_description', result.get('error'))}"
            )

        expires_at = None
        if "expires_in" in result:
            expires_at = datetime.now(timezone.utc).replace(
                microsecond=0
            ) + __import__("datetime").timedelta(seconds=result["expires_in"])

        return TokenInfo(
            access_token=result["access_token"],
            refresh_token=result.get("refresh_token", refresh_token),
            expires_at=expires_at,
            id_token=result.get("id_token"),
        )


class OutlookCalendarClient:
    """
    Client for Microsoft Graph Calendar API.

    Provides methods to create, read, update, and delete
    calendar events in a user's Outlook calendar.
    """

    def __init__(self, access_token: str):
        """
        Initialize the calendar client.

        Args:
            access_token: OAuth2 access token with calendar permissions
        """
        self.access_token = access_token
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _event_to_graph_format(self, event: OutlookEvent) -> dict[str, Any]:
        """Convert OutlookEvent to Microsoft Graph API format."""
        # Format datetime for Graph API
        start_dt = event.start
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        end_dt = event.end
        if end_dt is None:
            # Default to 1 hour duration
            end_dt = start_dt + __import__("datetime").timedelta(hours=1)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        graph_event: dict[str, Any] = {
            "subject": event.title,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": event.time_zone,
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": event.time_zone,
            },
            "isAllDay": event.is_all_day,
        }

        if event.description:
            graph_event["body"] = {
                "contentType": "text",
                "content": event.description,
            }

        if event.location:
            graph_event["location"] = {
                "displayName": event.location,
            }

        if event.url:
            # Add URL to description if body exists, otherwise create body
            url_text = f"\n\nMore info: {event.url}"
            if "body" in graph_event:
                graph_event["body"]["content"] += url_text
            else:
                graph_event["body"] = {
                    "contentType": "text",
                    "content": url_text.strip(),
                }

        return graph_event

    def _graph_to_event(self, data: dict[str, Any]) -> OutlookEvent:
        """Convert Microsoft Graph API response to OutlookEvent."""
        start_data = data.get("start", {})
        end_data = data.get("end", {})

        start_dt = datetime.fromisoformat(
            start_data.get("dateTime", "").replace("Z", "+00:00")
        )
        end_dt = datetime.fromisoformat(
            end_data.get("dateTime", "").replace("Z", "+00:00")
        )

        description = None
        if data.get("body"):
            description = data["body"].get("content", "")

        location = None
        if data.get("location"):
            location = data["location"].get("displayName")

        return OutlookEvent(
            id=data.get("id"),
            title=data.get("subject", "Untitled Event"),
            start=start_dt,
            end=end_dt,
            description=description,
            location=location,
            is_all_day=data.get("isAllDay", False),
            time_zone=start_data.get("timeZone", "UTC"),
        )

    async def create_event(self, event: OutlookEvent) -> OutlookEvent:
        """
        Create an event in the user's Outlook calendar.

        Args:
            event: Event to create

        Returns:
            Created event with ID populated
        """
        client = await self._get_client()

        graph_event = self._event_to_graph_format(event)
        response = await client.post(GRAPH_CALENDAR_ENDPOINT, json=graph_event)

        if response.status_code == 401:
            raise ValueError("Access token expired or invalid")

        response.raise_for_status()

        created_data = response.json()
        logger.info("Created Outlook event: %s", created_data.get("id"))

        return self._graph_to_event(created_data)

    async def create_events(self, events: list[OutlookEvent]) -> list[OutlookEvent]:
        """
        Create multiple events in the user's Outlook calendar.

        Args:
            events: List of events to create

        Returns:
            List of created events with IDs populated
        """
        created = []
        for event in events:
            try:
                created_event = await self.create_event(event)
                created.append(created_event)
            except Exception as e:
                logger.error("Failed to create event '%s': %s", event.title, e)

        return created

    async def list_events(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 50,
    ) -> list[OutlookEvent]:
        """
        List events from the user's Outlook calendar.

        Args:
            start_date: Filter events starting after this date
            end_date: Filter events ending before this date
            limit: Maximum number of events to return

        Returns:
            List of calendar events
        """
        client = await self._get_client()

        params: dict[str, Any] = {
            "$top": limit,
            "$orderby": "start/dateTime",
        }

        # Build filter for date range
        filters = []
        if start_date:
            start_str = start_date.isoformat()
            filters.append(f"start/dateTime ge '{start_str}'")
        if end_date:
            end_str = end_date.isoformat()
            filters.append(f"end/dateTime le '{end_str}'")

        if filters:
            params["$filter"] = " and ".join(filters)

        response = await client.get(GRAPH_CALENDAR_ENDPOINT, params=params)

        if response.status_code == 401:
            raise ValueError("Access token expired or invalid")

        response.raise_for_status()

        data = response.json()
        events = [self._graph_to_event(item) for item in data.get("value", [])]

        logger.info("Retrieved %d Outlook events", len(events))
        return events

    async def get_event(self, event_id: str) -> OutlookEvent | None:
        """
        Get a specific event by ID.

        Args:
            event_id: The event ID

        Returns:
            OutlookEvent if found, None otherwise
        """
        client = await self._get_client()

        response = await client.get(f"{GRAPH_CALENDAR_ENDPOINT}/{event_id}")

        if response.status_code == 404:
            return None
        if response.status_code == 401:
            raise ValueError("Access token expired or invalid")

        response.raise_for_status()
        return self._graph_to_event(response.json())

    async def delete_event(self, event_id: str) -> bool:
        """
        Delete an event from the user's calendar.

        Args:
            event_id: The event ID to delete

        Returns:
            True if deleted, False if not found
        """
        client = await self._get_client()

        response = await client.delete(f"{GRAPH_CALENDAR_ENDPOINT}/{event_id}")

        if response.status_code == 404:
            return False
        if response.status_code == 401:
            raise ValueError("Access token expired or invalid")

        response.raise_for_status()
        logger.info("Deleted Outlook event: %s", event_id)
        return True


def get_msgraph_auth() -> MSGraphAuth:
    """Get a configured MSGraphAuth instance."""
    return MSGraphAuth()


def get_outlook_client(access_token: str) -> OutlookCalendarClient:
    """Get an OutlookCalendarClient with the given access token."""
    return OutlookCalendarClient(access_token)
