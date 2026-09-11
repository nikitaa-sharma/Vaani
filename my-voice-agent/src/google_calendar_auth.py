"""Google OAuth 2.0 authentication module for Vaani.

Provides secure OAuth 2.0 authorization code flow to access Google Calendar, Google Tasks,
and Gmail drafts with:
- calendar events scope (https://www.googleapis.com/auth/calendar.events)
- tasks scope (https://www.googleapis.com/auth/tasks)
- gmail compose scope (https://www.googleapis.com/auth/gmail.compose)
All tokens and credentials are strictly stored and refreshed on the backend.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import Resource, build

# Ensure .env.local is loaded if present
load_dotenv(".env.local")

logger = logging.getLogger("google_calendar_auth")

# Scopes required for Vaani calendar, tasks, and gmail interactions
GOOGLE_CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"
GOOGLE_TASKS_SCOPE = "https://www.googleapis.com/auth/tasks"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
SCOPES = [GOOGLE_CALENDAR_EVENTS_SCOPE, GOOGLE_TASKS_SCOPE, GMAIL_COMPOSE_SCOPE]

# Default backend token file location
DEFAULT_TOKEN_FILE = "google_calendar_token.json"
DEFAULT_TOKEN_PATH = Path(__file__).resolve().parent.parent / DEFAULT_TOKEN_FILE

# Google OAuth endpoints
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URI = "https://oauth2.googleapis.com/revoke"


def get_token_storage_path(custom_path: Path | str | None = None) -> Path:
    """Resolve the storage path for backend OAuth tokens."""
    if custom_path:
        return Path(custom_path)
    env_path = os.getenv("GOOGLE_TOKEN_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_TOKEN_PATH


def get_oauth_config() -> dict[str, str]:
    """Retrieve and validate Google OAuth configuration from environment variables.

    Returns:
        dict containing client_id, client_secret, and redirect_uri.

    Raises:
        ValueError: If required environment variables are missing.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:8080/oauth/callback"
    )

    missing = []
    if not client_id:
        missing.append("GOOGLE_CLIENT_ID")
    if not client_secret:
        missing.append("GOOGLE_CLIENT_SECRET")

    if missing:
        raise ValueError(
            f"Missing required Google OAuth configuration in environment: {', '.join(missing)}. "
            f"Please set these in .env.local (refer to .env.local.example)."
        )

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


def get_client_config() -> dict[str, Any]:
    """Construct client configuration dictionary compatible with Google OAuth Flow."""
    config = get_oauth_config()
    return {
        "web": {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
            "redirect_uris": [config["redirect_uri"]],
        }
    }


def create_oauth_flow(
    state: str | None = None,
    redirect_uri: str | None = None,
) -> Flow:
    """Create a Google OAuth Flow instance configured for Calendar events scope.

    Args:
        state: Optional CSRF state string.
        redirect_uri: Optional override for OAuth redirect URI.

    Returns:
        Configured Flow instance.
    """
    client_config = get_client_config()
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        state=state,
    )
    flow.redirect_uri = redirect_uri or client_config["web"]["redirect_uris"][0]
    return flow


def get_authorization_url(
    state: str | None = None,
    redirect_uri: str | None = None,
) -> tuple[str, str]:
    """Generate the Google OAuth authorization URL and CSRF state token.

    Args:
        state: Optional CSRF state token. If None, a secure token is generated.
        redirect_uri: Optional custom redirect URI.

    Returns:
        A tuple of (authorization_url, state).
    """
    if not state:
        state = secrets.token_urlsafe(32)

    flow = create_oauth_flow(state=state, redirect_uri=redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url, state


def save_credentials(
    credentials: Credentials,
    token_path: Path | str | None = None,
) -> Path:
    """Save OAuth credentials securely on the backend.

    Tokens are stored strictly on the backend filesystem with restricted
    file permissions. Never exposed to the frontend.

    Args:
        credentials: The Google Credentials object.
        token_path: Optional custom file path to store credentials.

    Returns:
        Path to the saved credentials file.
    """
    dest_path = get_token_storage_path(token_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    expiry_iso = None
    if credentials.expiry:
        if credentials.expiry.tzinfo is None:
            expiry_iso = credentials.expiry.replace(tzinfo=timezone.utc).isoformat()
        else:
            expiry_iso = credentials.expiry.isoformat()

    creds_dict = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri or GOOGLE_TOKEN_URI,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes or SCOPES,
        "expiry": expiry_iso,
    }

    # Write credentials securely
    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(creds_dict, f, indent=2)

    # Restrict permissions on POSIX operating systems (chmod 600)
    with contextlib.suppress(OSError, AttributeError):
        os.chmod(dest_path, 0o600)

    logger.info(f"Saved Google Calendar credentials to {dest_path}")
    return dest_path


def load_credentials(
    token_path: Path | str | None = None,
) -> Credentials | None:
    """Load stored credentials from backend storage.

    Args:
        token_path: Optional custom path to credentials file.

    Returns:
        Credentials object if found and valid, otherwise None.
    """
    path = get_token_storage_path(token_path)
    if not path.exists():
        return None

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        expiry_str = data.get("expiry")
        expiry = None
        if expiry_str:
            try:
                dt = datetime.fromisoformat(expiry_str)
                # google-auth requires offset-naive UTC datetime for comparisons
                if dt.tzinfo is not None:
                    expiry = dt.astimezone(timezone.utc).replace(tzinfo=None)
                else:
                    expiry = dt
            except (ValueError, TypeError):
                expiry = None

        return Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri", GOOGLE_TOKEN_URI),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=data.get("scopes", SCOPES),
            expiry=expiry,
        )
    except Exception as e:
        logger.warning(f"Failed to read credentials from {path}: {e}")
        return None


def get_credentials(
    token_path: Path | str | None = None,
    auto_refresh: bool = True,
) -> Credentials | None:
    """Retrieve credentials, automatically refreshing them if expired.

    Args:
        token_path: Optional custom path to credentials file.
        auto_refresh: Whether to automatically refresh expired credentials.

    Returns:
        Valid Credentials object, or None if not authenticated.
    """
    creds = load_credentials(token_path=token_path)
    if not creds:
        return None

    if creds.expired and creds.refresh_token and auto_refresh:
        try:
            logger.info("Credentials expired; refreshing via Google token endpoint")
            creds.refresh(Request())
            save_credentials(creds, token_path=token_path)
        except Exception as e:
            logger.error(f"Failed to refresh Google credentials: {e}")
            return None

    return creds if creds.valid else None


def is_authenticated(token_path: Path | str | None = None) -> bool:
    """Check if valid or refreshable Google Calendar credentials are available on the backend.

    Args:
        token_path: Optional custom path to credentials file.

    Returns:
        True if authenticated with valid/refreshable credentials, False otherwise.
    """
    creds = get_credentials(token_path=token_path, auto_refresh=True)
    return creds is not None and creds.valid


def exchange_code_for_credentials(
    code: str,
    state: str | None = None,
    expected_state: str | None = None,
    redirect_uri: str | None = None,
    token_path: Path | str | None = None,
) -> Credentials:
    """Exchange authorization code for access & refresh tokens and save them.

    Args:
        code: The authorization code returned by Google.
        state: The state received in the callback.
        expected_state: The state originally generated and stored in session.
        redirect_uri: Optional custom redirect URI.
        token_path: Optional custom path to save credentials.

    Returns:
        Authorized Credentials object.

    Raises:
        ValueError: If state verification fails or exchange fails.
    """
    if expected_state and state != expected_state:
        raise ValueError(
            "State mismatch during OAuth callback (potential CSRF attack)."
        )

    flow = create_oauth_flow(state=state, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)

    credentials = flow.credentials
    save_credentials(credentials, token_path=token_path)
    return credentials


def revoke_credentials(token_path: Path | str | None = None) -> bool:
    """Revoke access token with Google and remove stored credentials from the backend.

    Args:
        token_path: Optional custom path to credentials file.

    Returns:
        True if credentials were removed successfully, False otherwise.
    """
    path = get_token_storage_path(token_path)
    creds = load_credentials(token_path=token_path)

    revoked = False
    if creds and creds.token:
        try:
            resp = requests.post(
                GOOGLE_REVOKE_URI,
                params={"token": creds.token},
                headers={"content-type": "application/x-www-form-urlencoded"},
                timeout=5,
            )
            revoked = resp.status_code == 200
        except Exception as e:
            logger.warning(f"Error revoking token with Google: {e}")

    if path.exists():
        try:
            path.unlink()
            logger.info(f"Removed backend credentials file {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete credentials file {path}: {e}")
            return False

    return revoked


def get_calendar_service(token_path: Path | str | None = None) -> Resource:
    """Construct an authorized Google Calendar API Resource service.

    Args:
        token_path: Optional custom path to credentials file.

    Returns:
        googleapiclient.discovery.Resource for Google Calendar API v3.

    Raises:
        RuntimeError: If user is not authenticated.
    """
    creds = get_credentials(token_path=token_path, auto_refresh=True)
    if not creds:
        raise RuntimeError(
            "Google Calendar is not authenticated. Complete the OAuth flow first."
        )

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def run_local_oauth_flow(
    port: int = 8080,
    open_browser: bool = True,
    token_path: Path | str | None = None,
) -> Credentials:
    """Run an interactive local server OAuth flow.

    Convenient for CLI or initial setup to authenticate Vaani with Google Calendar.
    Starts a temporary HTTP listener on localhost to capture the authorization code.

    Args:
        port: Port to run callback server on (default: 8080).
        open_browser: Whether to automatically launch the default browser.
        token_path: Optional path to store credentials.

    Returns:
        Credentials obtained from the OAuth flow.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    config = get_oauth_config()
    client_config = {
        "installed": {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
            "redirect_uris": [f"http://localhost:{port}/", config["redirect_uri"]],
        }
    }

    flow = InstalledAppFlow.from_client_config(
        client_config,
        scopes=SCOPES,
    )

    credentials = flow.run_local_server(
        port=port,
        open_browser=open_browser,
        prompt="consent",
        authorization_prompt_message="Please visit this URL in your browser to authenticate Vaani: {url}",
        success_message="Authentication successful! Google Calendar is now connected to Vaani. You may close this window.",
    )

    save_credentials(credentials, token_path=token_path)
    return credentials


if __name__ == "__main__":
    import sys

    print("Google Calendar OAuth Tool for Vaani")
    print("=" * 40)
    try:
        cfg = get_oauth_config()
        print(f"Client ID: {cfg['client_id'][:12]}...")
        print(f"Redirect URI: {cfg['redirect_uri']}")
        print(f"Scopes: {', '.join(SCOPES)}")
        auth_state = is_authenticated()
        print(f"Authenticated: {auth_state}")

        if len(sys.argv) > 1 and sys.argv[1] == "--login":
            print("Launching local OAuth flow...")
            creds = run_local_oauth_flow()
            print("Successfully authenticated and saved credentials!")
        elif not auth_state:
            auth_url, state = get_authorization_url()
            print("\nTo authorize manually, open this URL in a browser:")
            print(auth_url)
    except Exception as err:
        print(f"Configuration error: {err}")
