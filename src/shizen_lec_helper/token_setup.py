"""Interactive Moodle token acquisition.

Prompts for username and password via getpass (never stored to disk),
calls the Moodle token endpoint, verifies with site_info, and saves
the token to ~/.config/shizen_lec_helper/moodle-token.json.
"""

import getpass
import json
import logging
import sys
from datetime import datetime, timezone

import requests

from .config import DEFAULT_SITE_URL, MoodleToken, moodle_api_endpoint

logger = logging.getLogger(__name__)

# Moodle mobile app service name (standard across all Moodle installations)
MOODLE_MOBILE_SERVICE = "moodle_mobile_app"

# HTTP timeout for token acquisition requests (seconds)
TOKEN_REQUEST_TIMEOUT_SECONDS = 20


def acquire_moodle_token(site_url: str = DEFAULT_SITE_URL) -> MoodleToken:
    """Interactively obtain a Moodle token.

    Prompts for credentials, POSTs to the token endpoint, verifies
    connectivity, and returns a MoodleToken ready for saving.

    Password is read via getpass and discarded from memory immediately
    after the HTTP request completes — it is never written to disk.

    Args:
        site_url: Base URL of the Moodle site.

    Returns:
        MoodleToken populated with token, user_id, site_url, created_at.

    Raises:
        RuntimeError: If token acquisition or site info check fails.
    """
    token_url = f"{site_url.rstrip('/')}/login/token.php"

    print(f"\nMoodle token acquisition for: {site_url}")
    print("Your password will only be used to request a token and will not be saved.\n")

    username = input("SOS (Moodle) username (email): ").strip()
    password = getpass.getpass("SOS (Moodle) password: ")

    try:
        resp = requests.post(
            token_url,
            data={
                "username": username,
                "password": password,
                "service": MOODLE_MOBILE_SERVICE,
            },
            timeout=TOKEN_REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Token request failed: {e}")
        raise RuntimeError(f"Could not reach Moodle server at {site_url}: {e}") from e
    finally:
        # Overwrite the password variable immediately after use
        password = ""  # noqa: F841

    response_data: dict = resp.json()

    if "error" in response_data:
        error_msg = response_data.get("error", "Unknown error")
        logger.error(f"Token acquisition failed: {error_msg}")
        raise RuntimeError(f"Login failed: {error_msg}")

    token_value: str = response_data.get("token", "")
    if not token_value:
        raise RuntimeError("Token not found in server response.")

    print("Token received. Verifying connectivity...")

    # Verify token by fetching site info
    user_id = _verify_token_and_get_user_id(site_url, token_value)

    moodle_token = MoodleToken(
        token=token_value,
        user_id=user_id,
        site_url=site_url,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    print(f"Verified! Logged in as user_id={user_id}")
    return moodle_token


def _verify_token_and_get_user_id(site_url: str, token: str) -> int:
    """Call core_webservice_get_site_info to confirm token works.

    Returns the authenticated user's user_id.

    Raises:
        RuntimeError: If the verification call fails.
    """
    api_url = moodle_api_endpoint(site_url)
    try:
        resp = requests.get(
            api_url,
            params={
                "wstoken": token,
                "wsfunction": "core_webservice_get_site_info",
                "moodlewsrestformat": "json",
            },
            timeout=TOKEN_REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Site info verification failed: {e}")
        raise RuntimeError(f"Could not verify token: {e}") from e

    data: dict = resp.json()
    if "exception" in data:
        raise RuntimeError(f"Token verification failed: {data.get('message', 'unknown')}")

    user_id: int = data.get("userid", 0)
    if not user_id:
        raise RuntimeError("Could not retrieve user_id from site info response.")

    username: str = data.get("username", "unknown")
    fullname: str = data.get("fullname", "")
    print(f"Connected to: {data.get('sitename', site_url)}")
    print(f"  Username : {username}")
    print(f"  Full name: {fullname}")

    return user_id


def run_token_setup(site_url: str = DEFAULT_SITE_URL,
                    config_dir: "Path | str | None" = None) -> MoodleToken:
    """Run the full token setup flow: acquire, verify, and save to disk.

    Args:
        site_url: Base URL of the Moodle site.
        config_dir: Optional config directory override (from CLI --config-dir flag).

    Returns:
        The saved MoodleToken.
    """
    from pathlib import Path
    from .config import make_config_paths

    token = acquire_moodle_token(site_url)
    token.save(config_dir)
    resolved_dir, _cfg, token_path, _state = make_config_paths(config_dir)
    print(f"\nToken saved to {token_path}")
    return token
