"""Unit tests for Google Calendar OAuth authentication module."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from google.oauth2.credentials import Credentials

from google_calendar_auth import (
    GOOGLE_CALENDAR_EVENTS_SCOPE,
    GOOGLE_TASKS_SCOPE,
    SCOPES,
    exchange_code_for_credentials,
    get_authorization_url,
    get_calendar_service,
    get_credentials,
    get_oauth_config,
    is_authenticated,
    load_credentials,
    revoke_credentials,
    save_credentials,
)


@pytest.fixture
def mock_env(monkeypatch):
    """Set standard mock environment variables for Google OAuth."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "mock-client-id-123.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "mock-client-secret-xyz")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/oauth/callback")


def test_scopes_include_calendar_events_and_tasks():
    """Verify that Google Calendar events, Google Tasks, and Gmail compose scopes are requested."""
    from google_calendar_auth import GMAIL_COMPOSE_SCOPE

    assert GOOGLE_CALENDAR_EVENTS_SCOPE == "https://www.googleapis.com/auth/calendar.events"
    assert GOOGLE_TASKS_SCOPE == "https://www.googleapis.com/auth/tasks"
    assert GMAIL_COMPOSE_SCOPE == "https://www.googleapis.com/auth/gmail.compose"
    assert GOOGLE_CALENDAR_EVENTS_SCOPE in SCOPES
    assert GOOGLE_TASKS_SCOPE in SCOPES
    assert GMAIL_COMPOSE_SCOPE in SCOPES
    assert len(SCOPES) == 3


def test_missing_oauth_config(monkeypatch):
    """Verify ValueError is raised when required env variables are missing."""
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    with pytest.raises(ValueError, match="Missing required Google OAuth configuration"):
        get_oauth_config()


def test_valid_oauth_config(mock_env):
    """Verify valid configuration dictionary is returned from environment."""
    config = get_oauth_config()
    assert config["client_id"] == "mock-client-id-123.apps.googleusercontent.com"
    assert config["client_secret"] == "mock-client-secret-xyz"
    assert config["redirect_uri"] == "http://localhost:8080/oauth/callback"


def test_get_authorization_url(mock_env):
    """Verify authorization URL generation with proper parameters, both scopes, and CSRF state."""
    auth_url, state = get_authorization_url()

    assert auth_url.startswith("https://accounts.google.com/o/oauth2/auth")
    assert "mock-client-id-123" in auth_url
    assert "access_type=offline" in auth_url
    assert "prompt=consent" in auth_url
    assert "calendar.events" in auth_url
    assert "tasks" in auth_url
    assert state is not None
    assert len(state) > 10
    assert state in auth_url


def test_save_and_load_credentials(tmp_path):
    """Verify credentials can be saved and loaded strictly from backend storage."""
    token_file = tmp_path / "test_token.json"
    expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    mock_creds = Credentials(
        token="mock-access-token-abc",
        refresh_token="mock-refresh-token-xyz",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="mock-client-id-123",
        client_secret="mock-client-secret-xyz",
        scopes=SCOPES,
    )
    mock_creds.expiry = expiry

    saved_path = save_credentials(mock_creds, token_path=token_file)
    assert saved_path == token_file
    assert token_file.exists()

    loaded = load_credentials(token_path=token_file)
    assert loaded is not None
    assert loaded.token == "mock-access-token-abc"
    assert loaded.refresh_token == "mock-refresh-token-xyz"
    assert loaded.client_id == "mock-client-id-123"
    assert loaded.client_secret == "mock-client-secret-xyz"
    assert loaded.scopes == SCOPES


def test_state_mismatch_protection(mock_env):
    """Verify state mismatch raises ValueError to protect against CSRF attacks."""
    with pytest.raises(ValueError, match="State mismatch"):
        exchange_code_for_credentials(
            code="auth-code-123",
            state="state-received-from-google",
            expected_state="different-state-in-session",
        )


def test_exchange_code_for_credentials(mock_env, tmp_path):
    """Verify code exchange with Google Flow and saving to token path."""
    token_file = tmp_path / "exchanged_token.json"

    with patch("google_calendar_auth.create_oauth_flow") as mock_flow_factory:
        mock_flow = MagicMock()
        mock_creds = Credentials(
            token="exchanged-token",
            refresh_token="exchanged-refresh",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="mock-id",
            client_secret="mock-secret",
            scopes=SCOPES,
        )
        mock_flow.credentials = mock_creds
        mock_flow_factory.return_value = mock_flow

        creds = exchange_code_for_credentials(
            code="test-auth-code",
            state="expected-state",
            expected_state="expected-state",
            token_path=token_file,
        )

        mock_flow.fetch_token.assert_called_once_with(code="test-auth-code")
        assert creds.token == "exchanged-token"
        assert token_file.exists()


def test_is_authenticated_false_when_no_token(tmp_path):
    """Verify is_authenticated returns False when no token file exists."""
    assert is_authenticated(token_path=tmp_path / "non_existent.json") is False


def test_is_authenticated_true_with_valid_token(tmp_path):
    """Verify is_authenticated returns True with a valid token."""
    token_file = tmp_path / "valid_token.json"
    creds = Credentials(
        token="valid-token",
        refresh_token="valid-refresh",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="mock-id",
        client_secret="mock-secret",
        scopes=SCOPES,
    )
    # Future expiry (naive UTC for google-auth compatibility)
    creds.expiry = datetime.utcnow() + timedelta(hours=1)
    save_credentials(creds, token_path=token_file)

    assert is_authenticated(token_path=token_file) is True


def test_auto_refresh_credentials(tmp_path):
    """Verify expired credentials with refresh token are refreshed automatically."""
    token_file = tmp_path / "expired_token.json"
    expired_creds = Credentials(
        token="expired-token",
        refresh_token="good-refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="mock-id",
        client_secret="mock-secret",
        scopes=SCOPES,
    )
    # Past expiry (naive UTC for google-auth compatibility)
    expired_creds.expiry = datetime.utcnow() - timedelta(hours=1)
    save_credentials(expired_creds, token_path=token_file)

    with patch.object(Credentials, "refresh", autospec=True) as mock_refresh:
        # Simulate successful refresh on the loaded credentials instance
        def fake_refresh(self, request):
            self.token = "new-fresh-token"
            self.expiry = datetime.utcnow() + timedelta(hours=1)

        mock_refresh.side_effect = fake_refresh

        result = get_credentials(token_path=token_file, auto_refresh=True)
        assert result is not None
        assert mock_refresh.called
        assert result.token == "new-fresh-token"


def test_revoke_credentials(tmp_path):
    """Verify revoke_credentials removes backend token file."""
    token_file = tmp_path / "to_revoke.json"
    creds = Credentials(token="token-to-revoke")
    save_credentials(creds, token_path=token_file)
    assert token_file.exists()

    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        success = revoke_credentials(token_path=token_file)
        assert success is True
        assert not token_file.exists()


def test_get_calendar_service_unauthenticated(tmp_path):
    """Verify get_calendar_service raises RuntimeError if unauthenticated."""
    with pytest.raises(RuntimeError, match="not authenticated"):
        get_calendar_service(token_path=tmp_path / "missing.json")


def test_get_calendar_service_authenticated(tmp_path):
    """Verify get_calendar_service builds the v3 calendar service."""
    token_file = tmp_path / "valid_token.json"
    creds = Credentials(
        token="valid-token",
        refresh_token="valid-refresh",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="mock-id",
        client_secret="mock-secret",
        scopes=SCOPES,
    )
    creds.expiry = datetime.utcnow() + timedelta(hours=1)
    save_credentials(creds, token_path=token_file)

    with patch("google_calendar_auth.build") as mock_build:
        mock_build.return_value = MagicMock()
        service = get_calendar_service(token_path=token_file)
        assert service is not None
        mock_build.assert_called_once()
        args, kwargs = mock_build.call_args
        assert args == ("calendar", "v3")
        assert kwargs["credentials"].token == "valid-token"
        assert kwargs["cache_discovery"] is False
