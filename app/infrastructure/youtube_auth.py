"""YouTube OAuth authentication client.

This module provides OAuth 2.0 authentication for YouTube Data API v3
and YouTube Analytics API v2, handling token refresh and credential persistence.

Required OAuth scopes:
- youtube.upload: Upload videos
- youtube: Manage YouTube account
- youtube.readonly: View account info
- yt-analytics.readonly: View analytics
"""

import pickle
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from app.core.exceptions import InvalidCredentialsError, TokenExpiredError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Required OAuth scopes for full functionality
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


@dataclass
class YouTubeCredentials:
    """YouTube OAuth credentials wrapper.

    Attributes:
        access_token: Current access token
        refresh_token: Token for refreshing access
        token_expiry: When the access token expires
        client_id: OAuth client ID
        client_secret: OAuth client secret
        scopes: Authorized scopes
    """

    access_token: str
    refresh_token: str
    token_expiry: datetime | None
    client_id: str
    client_secret: str
    scopes: list[str] = field(default_factory=list)


class YouTubeAuthClient:
    """YouTube OAuth authentication client.

    Manages OAuth 2.0 credentials for YouTube APIs, handling token refresh
    and persistence. Provides authenticated service objects for Data API
    and Analytics API.

    Example:
        >>> auth = YouTubeAuthClient(
        ...     credentials_path=Path("credentials.json"),
        ...     token_path=Path("token.pickle"),
        ... )
        >>> youtube = await auth.get_youtube_service()
        >>> analytics = await auth.get_analytics_service()
    """

    def __init__(
        self,
        credentials_path: Path | str,
        token_path: Path | str,
    ) -> None:
        """Initialize YouTube auth client.

        Args:
            credentials_path: Path to OAuth client credentials JSON
            token_path: Path to store/load token pickle file
        """
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self._credentials: Credentials | None = None
        self._youtube_service: Resource | None = None
        self._analytics_service: Resource | None = None

        logger.info(
            "YouTubeAuthClient initialized",
            credentials_path=str(self.credentials_path),
            token_path=str(self.token_path),
        )

    def _load_credentials(self) -> Credentials | None:
        """Load credentials from token file.

        Returns:
            Credentials if token file exists, None otherwise
        """
        if not self.token_path.exists():
            return None

        try:
            with open(self.token_path, "rb") as f:
                creds = pickle.load(f)  # noqa: S301
                logger.debug("Loaded credentials from token file")
                return creds
        except Exception as e:
            logger.warning("Failed to load token file", error=str(e))
            return None

    def _save_credentials(self, creds: Credentials) -> None:
        """Save credentials to token file.

        Args:
            creds: Credentials to save
        """
        try:
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_path, "wb") as f:
                pickle.dump(creds, f)
            logger.debug("Saved credentials to token file")
        except Exception as e:
            logger.error("Failed to save token file", error=str(e))

    async def _refresh_credentials(self, creds: Credentials) -> Credentials:
        """Refresh expired credentials.

        Args:
            creds: Expired credentials with refresh token

        Returns:
            Refreshed credentials

        Raises:
            TokenExpiredError: If refresh fails
        """
        if not creds.refresh_token:
            raise TokenExpiredError(
                token_type="refresh",
                message="No refresh token available",
            )

        try:
            creds.refresh(Request())
            self._save_credentials(creds)
            logger.info("Successfully refreshed credentials")
            return creds
        except Exception as e:
            logger.error("Failed to refresh credentials", error=str(e))
            raise TokenExpiredError(
                token_type="access",
                message=f"Failed to refresh token: {e}",
            ) from e

    async def _run_oauth_flow(self) -> Credentials:
        """Run OAuth 2.0 authorization flow.

        Opens browser for user authorization and exchanges code for tokens.

        Returns:
            New credentials from authorization

        Raises:
            InvalidCredentialsError: If credentials file is missing or invalid
        """
        if not self.credentials_path.exists():
            raise InvalidCredentialsError(
                credential_type="oauth_client",
                message=f"Credentials file not found: {self.credentials_path}",
            )

        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path),
                scopes=YOUTUBE_SCOPES,
            )
            creds = flow.run_local_server(port=0)
            self._save_credentials(creds)
            logger.info("OAuth flow completed successfully")
            return creds
        except Exception as e:
            logger.error("OAuth flow failed", error=str(e))
            raise InvalidCredentialsError(
                credential_type="oauth",
                message=f"OAuth flow failed: {e}",
            ) from e

    async def get_credentials(self) -> Credentials:
        """Get valid credentials, refreshing or re-authorizing if needed.

        Returns:
            Valid OAuth credentials

        Raises:
            InvalidCredentialsError: If unable to obtain valid credentials
            TokenExpiredError: If token refresh fails
        """
        # Return cached credentials if still valid
        if self._credentials and self._credentials.valid:
            return self._credentials

        # Try to load from file
        creds = self._load_credentials()

        if creds:
            if creds.valid:
                self._credentials = creds
                return creds

            if creds.expired and creds.refresh_token:
                creds = await self._refresh_credentials(creds)
                self._credentials = creds
                return creds

        # Need new authorization
        creds = await self._run_oauth_flow()
        self._credentials = creds
        return creds

    async def get_youtube_service(self) -> Resource:
        """Get authenticated YouTube Data API v3 service.

        Returns:
            YouTube API service resource

        Raises:
            InvalidCredentialsError: If authentication fails
        """
        if self._youtube_service and self._credentials and self._credentials.valid:
            return self._youtube_service

        creds = await self.get_credentials()
        self._youtube_service = build("youtube", "v3", credentials=creds)
        logger.debug("Created YouTube Data API service")
        return self._youtube_service

    async def get_analytics_service(self) -> Resource:
        """Get authenticated YouTube Analytics API v2 service.

        Returns:
            YouTube Analytics API service resource

        Raises:
            InvalidCredentialsError: If authentication fails
        """
        if self._analytics_service and self._credentials and self._credentials.valid:
            return self._analytics_service

        creds = await self.get_credentials()
        self._analytics_service = build("youtubeAnalytics", "v2", credentials=creds)
        logger.debug("Created YouTube Analytics API service")
        return self._analytics_service

    async def is_authenticated(self) -> bool:
        """Check if client has valid authentication.

        Returns:
            True if valid credentials are available
        """
        try:
            creds = self._load_credentials()
            if creds and creds.valid:
                return True
            if creds and creds.expired and creds.refresh_token:
                await self._refresh_credentials(creds)
                return True
            return False
        except Exception:
            return False

    def get_credentials_info(self) -> dict[str, Any]:
        """Get info about current credentials.

        Returns:
            Dictionary with credentials info (without sensitive data)
        """
        creds = self._load_credentials()
        if not creds:
            return {"authenticated": False}

        return {
            "authenticated": creds.valid,
            "expired": creds.expired,
            "has_refresh_token": bool(creds.refresh_token),
            "scopes": list(creds.scopes) if creds.scopes else [],
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
        }


__all__ = [
    "YouTubeAuthClient",
    "YouTubeCredentials",
    "YOUTUBE_SCOPES",
]
