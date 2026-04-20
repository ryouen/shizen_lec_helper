"""Moodle token acquisition: interactive and non-interactive modes.

Three public entry points:
  acquire_moodle_token(site_url, username, password)  -- core HTTP logic
  acquire_moodle_token_interactive(site_url)           -- prompts via input/getpass
  acquire_moodle_token_from_file(site_url, username, creds_path)  -- reads password from file

run_token_setup(site_url, config_dir)                              -- interactive full flow
run_token_setup_from_file(site_url, username, creds_path, config_dir) -- file-based full flow
"""

import getpass
import logging
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import DEFAULT_SITE_URL, MoodleToken, moodle_api_endpoint

logger = logging.getLogger(__name__)

# Moodle mobile app service name (standard across all Moodle installations)
MOODLE_MOBILE_SERVICE = "moodle_mobile_app"

# HTTP timeout for token acquisition requests (seconds)
TOKEN_REQUEST_TIMEOUT_SECONDS = 20

# Octal permission mask for "group or other has any access" (i.e. not 600 or tighter)
_PERMISSION_GROUP_OTHER_MASK = 0o077


def acquire_moodle_token(
    site_url: str,
    username: str,
    password: str,
) -> MoodleToken:
    """Core token acquisition: POST credentials, verify with site_info, return token.

    Username and password are used only for the HTTP request and are NOT
    logged or written to disk.

    Args:
        site_url: Base URL of the Moodle site.
        username: Moodle login email/username.
        password: Moodle login password (cleared from caller after this returns).

    Returns:
        MoodleToken populated with token, user_id, site_url, created_at.

    Raises:
        RuntimeError: If token acquisition or site info check fails.
    """
    token_url = f"{site_url.rstrip('/')}/login/token.php"

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
        logger.error("Token request failed: %s", e)
        raise RuntimeError(f"Could not reach Moodle server at {site_url}: {e}") from e

    response_data: dict = resp.json()

    if "error" in response_data:
        error_msg = response_data.get("error", "Unknown error")
        logger.error("Token acquisition failed: %s", error_msg)
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


def acquire_moodle_token_interactive(site_url: str = DEFAULT_SITE_URL) -> MoodleToken:
    """Obtain a Moodle token interactively via input() / getpass().

    Suitable for TTY environments (Terminal.app, etc.) only.
    Raises EOFError with a helpful message when running in non-TTY shells
    (e.g. an AI agent's Bash tool).

    Args:
        site_url: Base URL of the Moodle site.

    Returns:
        MoodleToken populated with token, user_id, site_url, created_at.

    Raises:
        RuntimeError: If token acquisition or site info check fails.
        EOFError: Re-raised with guidance if stdin is not a TTY.
    """
    print(f"\nMoodle token acquisition for: {site_url}")
    print("Your password will only be used to request a token and will not be saved.\n")

    try:
        username = input("SOS (Moodle) username (email): ").strip()
        password = getpass.getpass("SOS (Moodle) password: ")
    except EOFError:
        raise EOFError(
            "Interactive input is not available (probably running from an AI agent's "
            "non-TTY shell). Please either:\n"
            "  1. Run this command directly in your Terminal (not AI chat), or\n"
            "  2. Use --creds-file PATH with a file containing SOS_USERNAME and "
            "SOS_PASSWORD\n"
            "     (see AI_SETUP.md for the non-interactive flow)."
        )

    try:
        return acquire_moodle_token(site_url, username, password)
    finally:
        # Overwrite credential variables immediately after use
        password = "\x00" * len(password)  # noqa: F841
        username = "\x00" * len(username)  # noqa: F841


def _read_password_file(file_path: str) -> str:
    """Read a password from a file (single line, trailing whitespace stripped).

    Supports files with or without trailing newline.

    Args:
        file_path: Absolute path to the password file.

    Returns:
        The password string with surrounding whitespace removed.

    Raises:
        ValueError: If the file is empty or contains only whitespace.
    """
    with open(file_path, "r", encoding="utf-8") as fh:
        content = fh.read()
    password = content.strip()
    if not password:
        raise ValueError(f"Password file is empty: {file_path}")
    return password


def _verify_credentials_file_security(creds_path: str) -> None:
    """Check that the credentials file is safe to read.

    Validates:
    - File exists.
    - File is owned by the current effective user.
    - File permissions are 600 or tighter (no group/other access).

    Args:
        creds_path: Path to the credentials file.

    Raises:
        SystemExit: Calls sys.exit(1) if any check fails.
    """
    path = Path(creds_path)

    if not path.exists():
        print(
            f"Error: Credentials file not found: {creds_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    file_stat = os.stat(creds_path)
    current_uid = os.getuid()

    if file_stat.st_uid != current_uid:
        print(
            f"Error: Credentials file is not owned by you (owner uid={file_stat.st_uid}, "
            f"your uid={current_uid}): {creds_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    file_mode = stat.S_IMODE(file_stat.st_mode)
    if file_mode & _PERMISSION_GROUP_OTHER_MASK:
        print(
            f"Error: File permissions too open ({oct(file_mode)}): {creds_path}\n"
            f"       Run: chmod 600 {creds_path}",
            file=sys.stderr,
        )
        sys.exit(1)


def acquire_moodle_token_from_file(
    site_url: str,
    username: str,
    creds_path: str,
) -> MoodleToken:
    """Obtain a Moodle token using a username and a password file.

    Security steps:
    1. Validates file ownership and permissions (600 or tighter).
    2. Reads the password from the file (one line, whitespace stripped).
    3. Calls the Moodle token endpoint.
    4. On success only: deletes the password file.
       On failure: leaves the file so the user can fix the password and retry.

    Args:
        site_url: Base URL of the Moodle site.
        username: Moodle login email/username (passed via CLI flag).
        creds_path: Path to the password file (one line containing the password).

    Returns:
        MoodleToken populated with token, user_id, site_url, created_at.

    Raises:
        RuntimeError: If token acquisition fails. File is NOT deleted on failure.
        ValueError: If the password file is empty.
        SystemExit: If security checks fail (ownership / permissions).
    """
    _verify_credentials_file_security(creds_path)
    password = _read_password_file(creds_path)

    # Credentials intentionally not logged
    print(f"\nMoodle token acquisition for: {site_url}")
    print("Reading password from file (not displayed).\n")

    try:
        token = acquire_moodle_token(site_url, username, password)
    except Exception:
        # Do NOT delete on failure — the user may want to retry after fixing the password.
        raise

    # Success: delete the password file (plain unlink; shred is unnecessary here).
    try:
        os.unlink(creds_path)
        print(f"Password file deleted: {creds_path}")
    except OSError as unlink_err:
        logger.warning("Could not delete password file: %s", unlink_err)

    return token


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
        logger.error("Site info verification failed: %s", e)
        raise RuntimeError(f"Could not verify token: {e}") from e

    data: dict = resp.json()
    if "exception" in data:
        raise RuntimeError(f"Token verification failed: {data.get('message', 'unknown')}")

    user_id: int = data.get("userid", 0)
    if not user_id:
        raise RuntimeError("Could not retrieve user_id from site info response.")

    # Site info is safe to display; credentials are NOT shown here
    print(f"Connected to: {data.get('sitename', site_url)}")
    print(f"  Username : {data.get('username', 'unknown')}")
    print(f"  Full name: {data.get('fullname', '')}")

    return user_id


def run_token_setup(
    site_url: str = DEFAULT_SITE_URL,
    config_dir: "Path | str | None" = None,
) -> MoodleToken:
    """Interactive full flow: acquire token via TTY, then save to disk.

    Args:
        site_url: Base URL of the Moodle site.
        config_dir: Optional config directory override.

    Returns:
        The saved MoodleToken.
    """
    from .config import make_config_paths

    token = acquire_moodle_token_interactive(site_url)
    token.save(config_dir)
    _resolved_dir, _cfg, token_path, _state = make_config_paths(config_dir)
    print(f"\nToken saved to {token_path}")
    return token


def run_token_setup_from_file(
    site_url: str,
    username: str,
    creds_path: str,
    config_dir: "Path | str | None" = None,
) -> MoodleToken:
    """Non-interactive full flow: read password from file, acquire token, save.

    The password file is deleted on success; left intact on failure so the
    user can fix the password and retry.

    Args:
        site_url: Base URL of the Moodle site.
        username: Moodle login email/username (from CLI flag).
        creds_path: Path to the password file (one line).
        config_dir: Optional config directory override.

    Returns:
        The saved MoodleToken.
    """
    from .config import make_config_paths

    token = acquire_moodle_token_from_file(site_url, username, creds_path)
    token.save(config_dir)
    _resolved_dir, _cfg, token_path, _state = make_config_paths(config_dir)
    print(f"\nToken saved to {token_path}")
    return token
