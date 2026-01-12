"""
Google Calendar OAuth and API integration service.

Provides OAuth flow for Google Calendar and methods to create events
in user's Google Calendar.

Uses direct REST API calls via httpx instead of google-api-python-client
to reduce bundle size (~92MB savings).
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel, Field

from api.config import get_settings

# Google Calendar API base URL
CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"

logger = logging.getLogger(__name__)

# Google Calendar API scopes
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

# Token storage directory
TOKEN_DIR = Path(__file__).parent.parent.parent / "data" / "google_tokens"


class GoogleCalendarEvent(BaseModel):
    """Event data for Google Calendar."""

    summary: str = Field(description="Event title")
    start: datetime = Field(description="Event start time")
    end: datetime | None = Field(default=None, description="Event end time")
    description: str | None = Field(default=None, description="Event description")
    location: str | None = Field(default=None, description="Event location")


class OAuthState(BaseModel):
    """OAuth state for CSRF protection."""

    user_id: str
    redirect_url: str | None = None


class GoogleCalendarService:
    """Service for Google Calendar OAuth and event creation.

    Handles the OAuth flow and provides methods to create events
    in a user's Google Calendar.
    """

    def __init__(self):
        """Initialize the Google Calendar service."""
        self.settings = get_settings()
        self._ensure_token_dir()

    def _ensure_token_dir(self) -> None:
        """Ensure token storage directory exists."""
        TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    def _get_client_config(self) -> dict[str, Any]:
        """Get OAuth client configuration."""
        return {
            "web": {
                "client_id": self.settings.google_client_id,
                "client_secret": self.settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.settings.google_redirect_uri],
            }
        }

    def _get_token_path(self, user_id: str) -> Path:
        """Get the token file path for a user."""
        # Sanitize user_id for filesystem
        safe_id = "".join(c if c.isalnum() else "_" for c in user_id)
        return TOKEN_DIR / f"{safe_id}_token.json"

    def is_configured(self) -> bool:
        """Check if Google OAuth is configured."""
        return bool(
            self.settings.google_client_id and self.settings.google_client_secret
        )

    def get_authorization_url(self, user_id: str, redirect_url: str | None = None) -> str:
        """Get the Google OAuth authorization URL.

        Args:
            user_id: Unique identifier for the user
            redirect_url: Optional URL to redirect after OAuth completion

        Returns:
            Authorization URL for the user to visit
        """
        if not self.is_configured():
            raise ValueError("Google OAuth is not configured")

        flow = Flow.from_client_config(
            self._get_client_config(),
            scopes=SCOPES,
            redirect_uri=self.settings.google_redirect_uri,
        )

        # Create state with user_id and optional redirect
        state = OAuthState(user_id=user_id, redirect_url=redirect_url)
        state_json = state.model_dump_json()

        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state_json,
        )

        return authorization_url

    def handle_oauth_callback(self, code: str, state: str) -> tuple[str, str | None]:
        """Handle the OAuth callback and store tokens.

        Args:
            code: Authorization code from Google
            state: State parameter for CSRF validation

        Returns:
            Tuple of (user_id, redirect_url)
        """
        if not self.is_configured():
            raise ValueError("Google OAuth is not configured")

        # Parse state
        state_data = OAuthState.model_validate_json(state)
        user_id = state_data.user_id

        # Exchange code for tokens
        flow = Flow.from_client_config(
            self._get_client_config(),
            scopes=SCOPES,
            redirect_uri=self.settings.google_redirect_uri,
        )
        flow.fetch_token(code=code)

        # Store credentials
        credentials = flow.credentials
        if credentials is None:
            raise ValueError("Failed to obtain credentials from OAuth flow")
        self._store_credentials(user_id, credentials)  # type: ignore[arg-type]

        logger.info("Stored Google OAuth tokens for user: %s", user_id)
        return user_id, state_data.redirect_url

    def _store_credentials(self, user_id: str, credentials: Credentials) -> None:
        """Store user credentials to file."""
        token_path = self._get_token_path(user_id)
        token_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
        }
        token_path.write_text(json.dumps(token_data))

    def _load_credentials(self, user_id: str) -> Credentials | None:
        """Load user credentials from file."""
        token_path = self._get_token_path(user_id)
        if not token_path.exists():
            return None

        try:
            token_data = json.loads(token_path.read_text())
            return Credentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes"),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load credentials for user %s: %s", user_id, e)
            return None

    def has_valid_credentials(self, user_id: str) -> bool:
        """Check if user has valid stored credentials."""
        credentials = self._load_credentials(user_id)
        if credentials is None:
            return False
        # Credentials might be expired but can be refreshed
        return credentials.refresh_token is not None

    def revoke_credentials(self, user_id: str) -> bool:
        """Revoke and delete user credentials.

        Args:
            user_id: User identifier

        Returns:
            True if credentials were deleted, False if none existed
        """
        token_path = self._get_token_path(user_id)
        if token_path.exists():
            token_path.unlink()
            logger.info("Revoked Google credentials for user: %s", user_id)
            return True
        return False

    def _refresh_credentials_if_needed(self, credentials: Credentials) -> Credentials:
        """Refresh credentials if expired."""
        if credentials.expired and credentials.refresh_token:
            import google.auth.transport.requests
            request = google.auth.transport.requests.Request()
            credentials.refresh(request)
        return credentials

    def create_event(
        self,
        user_id: str,
        event: GoogleCalendarEvent,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Create an event in the user's Google Calendar.

        Args:
            user_id: User identifier
            event: Event data to create
            calendar_id: Calendar ID (default: primary)

        Returns:
            Created event data from Google API

        Raises:
            ValueError: If user has no valid credentials
            httpx.HTTPStatusError: If Google API call fails
        """
        credentials = self._load_credentials(user_id)
        if credentials is None:
            raise ValueError(f"No credentials found for user: {user_id}")

        # Refresh token if needed
        credentials = self._refresh_credentials_if_needed(credentials)

        # Build event body
        event_body: dict[str, Any] = {
            "summary": event.summary,
            "start": {
                "dateTime": event.start.isoformat(),
                "timeZone": "UTC",
            },
        }

        # Set end time (default to 1 hour after start)
        if event.end:
            event_body["end"] = {
                "dateTime": event.end.isoformat(),
                "timeZone": "UTC",
            }
        else:
            from datetime import timedelta

            end_time = event.start + timedelta(hours=1)
            event_body["end"] = {
                "dateTime": end_time.isoformat(),
                "timeZone": "UTC",
            }

        if event.description:
            event_body["description"] = event.description

        if event.location:
            event_body["location"] = event.location

        # Use direct REST API call instead of google-api-python-client
        url = f"{CALENDAR_API_BASE}/calendars/{calendar_id}/events"
        headers = {"Authorization": f"Bearer {credentials.token}"}

        try:
            with httpx.Client() as client:
                response = client.post(url, headers=headers, json=event_body)
                response.raise_for_status()
                created_event = response.json()

            logger.info(
                "Created Google Calendar event '%s' for user %s",
                event.summary,
                user_id,
            )
            return created_event
        except httpx.HTTPStatusError as e:
            logger.error(
                "Failed to create Google Calendar event for user %s: %s",
                user_id,
                e,
            )
            raise

    def create_events_batch(
        self,
        user_id: str,
        events: list[GoogleCalendarEvent],
        calendar_id: str = "primary",
    ) -> list[dict[str, Any]]:
        """Create multiple events in the user's Google Calendar.

        Args:
            user_id: User identifier
            events: List of events to create
            calendar_id: Calendar ID (default: primary)

        Returns:
            List of created event data from Google API
        """
        results = []
        for event in events:
            try:
                result = self.create_event(user_id, event, calendar_id)
                results.append(result)
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Failed to create event '%s': %s",
                    event.summary,
                    e,
                )
                results.append({"error": str(e), "summary": event.summary})
        return results


# Singleton instance
_google_calendar_service: GoogleCalendarService | None = None


def get_google_calendar_service() -> GoogleCalendarService:
    """Get the singleton Google Calendar service."""
    global _google_calendar_service
    if _google_calendar_service is None:
        _google_calendar_service = GoogleCalendarService()
    return _google_calendar_service
