"""Minimal CLI to authorize Vaani with Google Calendar via localhost OAuth flow.

Usage:
    uv run python setup_google_calendar.py
"""

import sys
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from google_calendar_auth import (
    get_oauth_config,
    is_authenticated,
    run_local_oauth_flow,
)


def main() -> None:
    print()
    print("=" * 50)
    print("  Vaani — Google Calendar Setup")
    print("=" * 50)
    print()

    try:
        cfg = get_oauth_config()
    except ValueError as e:
        print(f"❌ {e}")
        print()
        print("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.local")
        print("(see .env.local.example for details)")
        sys.exit(1)

    print(f"  Client ID:    {cfg['client_id'][:20]}...")
    print(f"  Redirect URI: {cfg['redirect_uri']}")
    print()

    if is_authenticated():
        print("✅ Google Calendar is already connected!")
        answer = input("   Re-authorize anyway? [y/N] ").strip().lower()
        if answer != "y":
            print("   Nothing to do. Exiting.")
            return

    print("Opening browser for Google sign-in...")
    print()

    try:
        run_local_oauth_flow(port=8080, open_browser=True)
    except Exception as e:
        print(f"❌ OAuth flow failed: {e}")
        sys.exit(1)

    print()
    print("✅ Google Calendar connected successfully!")
    print("   Refresh token saved locally. You can now use calendar tools in Vaani.")
    print()


if __name__ == "__main__":
    main()
