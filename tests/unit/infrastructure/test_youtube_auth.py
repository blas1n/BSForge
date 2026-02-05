"""Unit tests for YouTube Auth client."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from app.core.exceptions import InvalidCredentialsError, TokenExpiredError
from app.infrastructure.youtube_auth import (
    YOUTUBE_SCOPES,
    YouTubeAuthClient,
    YouTubeCredentials,
)


class TestYouTubeCredentials:
    """Tests for YouTubeCredentials dataclass."""

    def test_basic_instantiation(self):
        """Test creating credentials with required fields."""
        creds = YouTubeCredentials(
            access_token="test_access",
            refresh_token="test_refresh",
            token_expiry=datetime.now(tz=UTC) + timedelta(hours=1),
            client_id="test_client_id",
            client_secret="test_secret",
        )

        assert creds.access_token == "test_access"
        assert creds.refresh_token == "test_refresh"
        assert creds.scopes == []

    def test_with_scopes(self):
        """Test credentials with scopes."""
        creds = YouTubeCredentials(
            access_token="test_access",
            refresh_token="test_refresh",
            token_expiry=None,
            client_id="test_client_id",
            client_secret="test_secret",
            scopes=["scope1", "scope2"],
        )

        assert len(creds.scopes) == 2


class TestYouTubeScopes:
    """Tests for YOUTUBE_SCOPES constant."""

    def test_scopes_defined(self):
        """Test that required scopes are defined."""
        assert "https://www.googleapis.com/auth/youtube.upload" in YOUTUBE_SCOPES
        assert "https://www.googleapis.com/auth/youtube.readonly" in YOUTUBE_SCOPES
        assert "https://www.googleapis.com/auth/yt-analytics.readonly" in YOUTUBE_SCOPES


class TestYouTubeAuthClient:
    """Tests for YouTubeAuthClient."""

    @pytest.fixture
    def client(self):
        """Create YouTubeAuthClient with default paths."""
        return YouTubeAuthClient(
            credentials_path="credentials.json",
            token_path="token.pickle",
        )

    # =========================================================================
    # Initialization tests
    # =========================================================================

    def test_init_with_string_paths(self):
        """Test initialization with string paths."""
        client = YouTubeAuthClient(
            credentials_path="creds.json",
            token_path="token.pickle",
        )

        assert isinstance(client.credentials_path, Path)
        assert isinstance(client.token_path, Path)
        assert client.credentials_path == Path("creds.json")
        assert client.token_path == Path("token.pickle")

    def test_init_with_path_objects(self):
        """Test initialization with Path objects."""
        client = YouTubeAuthClient(
            credentials_path=Path("/path/to/credentials.json"),
            token_path=Path("/path/to/token.pickle"),
        )

        assert client.credentials_path == Path("/path/to/credentials.json")
        assert client.token_path == Path("/path/to/token.pickle")

    def test_init_no_credentials_loaded(self, client):
        """Test that credentials are not loaded on init."""
        assert client._credentials is None

    # =========================================================================
    # _load_credentials() tests
    # =========================================================================

    def test_load_credentials_file_not_exists(self, client):
        """Test loading when token file doesn't exist."""
        with patch.object(Path, "exists", return_value=False):
            result = client._load_credentials()

        assert result is None

    def test_load_credentials_success(self, client):
        """Test successful credential loading."""
        with (
            patch.object(Path, "exists", return_value=True),
            patch("pickle.load") as mock_pickle_load,
            patch("builtins.open", mock_open()),
        ):
            mock_creds = MagicMock()
            mock_pickle_load.return_value = mock_creds
            result = client._load_credentials()

        assert result is not None

    def test_load_credentials_corrupted_file(self, client):
        """Test loading corrupted token file."""
        with (
            patch.object(Path, "exists", return_value=True),
            patch("builtins.open", mock_open(read_data=b"invalid pickle data")),
        ):
            result = client._load_credentials()

        assert result is None

    # =========================================================================
    # _save_credentials() tests
    # =========================================================================

    def test_save_credentials_creates_directory(self, client):
        """Test that save creates parent directory if needed."""
        mock_creds = MagicMock()

        with patch.object(Path, "mkdir") as mock_mkdir, patch("builtins.open", mock_open()):
            client._save_credentials(mock_creds)

        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_save_credentials_writes_pickle(self, client):
        """Test that credentials are pickled."""
        mock_creds = MagicMock()

        with patch.object(Path, "mkdir"), patch("builtins.open", mock_open()) as mock_file:
            client._save_credentials(mock_creds)

        mock_file.assert_called()

    # =========================================================================
    # _refresh_credentials() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_refresh_credentials_no_refresh_token(self, client):
        """Test refresh fails without refresh token."""
        mock_creds = MagicMock()
        mock_creds.refresh_token = None

        with pytest.raises(TokenExpiredError):
            await client._refresh_credentials(mock_creds)

    @pytest.mark.asyncio
    async def test_refresh_credentials_success(self, client):
        """Test successful credential refresh."""
        mock_creds = MagicMock()
        mock_creds.refresh_token = "test_refresh_token"
        mock_creds.refresh = MagicMock()

        with patch.object(client, "_save_credentials"):
            result = await client._refresh_credentials(mock_creds)

        mock_creds.refresh.assert_called_once()
        assert result == mock_creds

    @pytest.mark.asyncio
    async def test_refresh_credentials_network_error(self, client):
        """Test refresh handles network errors."""
        mock_creds = MagicMock()
        mock_creds.refresh_token = "test_refresh_token"
        mock_creds.refresh = MagicMock(side_effect=Exception("Network error"))

        with pytest.raises(TokenExpiredError) as exc_info:
            await client._refresh_credentials(mock_creds)

        assert "Network error" in str(exc_info.value)

    # =========================================================================
    # _run_oauth_flow() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_run_oauth_flow_missing_credentials(self, client):
        """Test OAuth flow fails when credentials file missing."""
        with (
            patch.object(Path, "exists", return_value=False),
            pytest.raises(InvalidCredentialsError) as exc_info,
        ):
            await client._run_oauth_flow()

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_run_oauth_flow_success(self, client):
        """Test successful OAuth flow."""
        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds

        with (
            patch.object(Path, "exists", return_value=True),
            patch("app.infrastructure.youtube_auth.InstalledAppFlow") as mock_flow_class,
            patch.object(client, "_save_credentials"),
        ):
            mock_flow_class.from_client_secrets_file.return_value = mock_flow
            result = await client._run_oauth_flow()

        assert result == mock_creds
        mock_flow.run_local_server.assert_called_once()

    # =========================================================================
    # get_credentials() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_credentials_cached_valid(self, client):
        """Test returning cached valid credentials."""
        mock_creds = MagicMock()
        mock_creds.valid = True
        client._credentials = mock_creds

        result = await client.get_credentials()

        assert result == mock_creds

    @pytest.mark.asyncio
    async def test_get_credentials_loads_from_file(self, client):
        """Test loading credentials from file."""
        mock_creds = MagicMock()
        mock_creds.valid = True

        with patch.object(client, "_load_credentials", return_value=mock_creds):
            result = await client.get_credentials()

        assert result == mock_creds

    @pytest.mark.asyncio
    async def test_get_credentials_refreshes_expired(self, client):
        """Test refreshing expired credentials."""
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_token"

        with (
            patch.object(client, "_load_credentials", return_value=mock_creds),
            patch.object(client, "_refresh_credentials", return_value=mock_creds),
        ):
            result = await client.get_credentials()

        assert result == mock_creds

    @pytest.mark.asyncio
    async def test_get_credentials_runs_oauth_flow(self, client):
        """Test running OAuth flow when no credentials available."""
        mock_creds = MagicMock()

        with (
            patch.object(client, "_load_credentials", return_value=None),
            patch.object(client, "_run_oauth_flow", return_value=mock_creds),
        ):
            result = await client.get_credentials()

        assert result == mock_creds

    # =========================================================================
    # get_youtube_service() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_youtube_service_creates_service(self, client):
        """Test creating YouTube service."""
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_service = MagicMock()

        with (
            patch.object(client, "get_credentials", return_value=mock_creds),
            patch("app.infrastructure.youtube_auth.build", return_value=mock_service),
        ):
            result = await client.get_youtube_service()

        assert result == mock_service

    @pytest.mark.asyncio
    async def test_get_youtube_service_caches_service(self, client):
        """Test that service is cached."""
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_service = MagicMock()
        client._credentials = mock_creds
        client._youtube_service = mock_service

        result = await client.get_youtube_service()

        assert result == mock_service

    # =========================================================================
    # get_analytics_service() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_get_analytics_service_creates_service(self, client):
        """Test creating Analytics service."""
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_service = MagicMock()

        with (
            patch.object(client, "get_credentials", return_value=mock_creds),
            patch("app.infrastructure.youtube_auth.build", return_value=mock_service),
        ):
            result = await client.get_analytics_service()

        assert result == mock_service

    # =========================================================================
    # is_authenticated() tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_is_authenticated_true(self, client):
        """Test is_authenticated returns True for valid credentials."""
        mock_creds = MagicMock()
        mock_creds.valid = True

        with patch.object(client, "_load_credentials", return_value=mock_creds):
            result = await client.is_authenticated()

        assert result is True

    @pytest.mark.asyncio
    async def test_is_authenticated_false_no_credentials(self, client):
        """Test is_authenticated returns False when no credentials."""
        with patch.object(client, "_load_credentials", return_value=None):
            result = await client.is_authenticated()

        assert result is False

    @pytest.mark.asyncio
    async def test_is_authenticated_refreshes_expired(self, client):
        """Test is_authenticated refreshes expired credentials."""
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_token"

        with (
            patch.object(client, "_load_credentials", return_value=mock_creds),
            patch.object(client, "_refresh_credentials"),
        ):
            result = await client.is_authenticated()

        assert result is True

    # =========================================================================
    # get_credentials_info() tests
    # =========================================================================

    def test_get_credentials_info_no_credentials(self, client):
        """Test credentials info when not authenticated."""
        with patch.object(client, "_load_credentials", return_value=None):
            info = client.get_credentials_info()

        assert info == {"authenticated": False}

    def test_get_credentials_info_with_credentials(self, client):
        """Test credentials info with valid credentials."""
        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds.expired = False
        mock_creds.refresh_token = "refresh_token"
        mock_creds.scopes = ["scope1", "scope2"]
        mock_creds.expiry = datetime.now(tz=UTC)

        with patch.object(client, "_load_credentials", return_value=mock_creds):
            info = client.get_credentials_info()

        assert info["authenticated"] is True
        assert info["expired"] is False
        assert info["has_refresh_token"] is True
        assert len(info["scopes"]) == 2
