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
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import DEFAULT_SITE_URL, MoodleToken, moodle_api_endpoint

logger = logging.getLogger(__name__)

# Moodle mobile app service name (standard across all Moodle installations)
MOODLE_MOBILE_SERVICE = "moodle_mobile_app"

# HTTP timeout for token acquisition requests (seconds)
TOKEN_REQUEST_TIMEOUT_SECONDS = 20

# Max candidate lines to try from a password file (guard against accidental
# giant files that would spam the Moodle login endpoint).
MAX_PASSWORD_CANDIDATES = 5

# Default location for the password file (user-friendly: visible in Finder).
DEFAULT_PASSWORD_FILE_PATH = "~/Downloads/moodle_password.txt"

# Template shown to the user when the AI creates the password file.
PASSWORD_FILE_TEMPLATE = """# Moodleのパスワードをここに入力して保存してください。
# Put your Moodle password on the line below and save.
#
# 1. このファイルの一番下の行に、あなたのMoodleのパスワードだけを書いてください
#    (On the last line, write only your Moodle password.)
# 2. 保存したらAIに「できました」と伝えてください
#    (Tell the AI "done" once you've saved.)
# 3. 認証に成功すると、このファイルは自動的に削除されます
#    (On successful login, this file will be deleted automatically.)
# 4. 認証に失敗した場合はファイルが残るので、直して再実行できます
#    (If login fails, the file stays so you can fix and retry.)

"""


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
            "non-TTY shell). Please use the password-file flow instead:\n"
            "  1. Run:  python -m shizen_lec_helper prep-password\n"
            "     (creates a template file at ~/Downloads/moodle_password.txt)\n"
            "  2. Open that file in TextEdit / Notepad and write your password\n"
            "  3. Run:  python -m shizen_lec_helper setup --username EMAIL "
            "--creds-file ~/Downloads/moodle_password.txt\n"
            "\nAlternatively, run this command directly in your own Terminal "
            "(not from the AI chat)."
        )

    try:
        return acquire_moodle_token(site_url, username, password)
    finally:
        # Overwrite credential variables immediately after use
        password = "\x00" * len(password)  # noqa: F841
        username = "\x00" * len(username)  # noqa: F841


def create_password_file_template(target_path: str = DEFAULT_PASSWORD_FILE_PATH) -> Path:
    """Create a password file template at the given path for the user to fill in.

    The template contains comment lines explaining what to do, then a blank
    line at the bottom where the user should write their password.

    Args:
        target_path: Where to create the file (default: ~/Downloads/moodle_password.txt).

    Returns:
        The absolute Path where the file was created.
    """
    path = Path(target_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PASSWORD_FILE_TEMPLATE, encoding="utf-8")
    return path


def _read_password_candidates(file_path: str) -> list[str]:
    """Read all non-comment, non-blank lines from a password file.

    Comment lines start with '#' (after leading whitespace). Blank lines
    (empty or whitespace-only) are skipped. All other lines are returned
    in file order as candidate passwords — the caller tries each until
    one succeeds.

    This forgiving approach handles common user mistakes like leaving
    placeholder text (e.g. "← ここに書く") above the real password:
    the authentication layer simply tries both and the wrong one fails
    harmlessly.

    Args:
        file_path: Absolute path to the password file.

    Returns:
        List of candidate password strings (whitespace stripped), in file order.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file contains no non-comment, non-blank line.
    """
    candidates: list[str] = []
    with open(file_path, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            candidates.append(stripped)

    if not candidates:
        raise ValueError(
            f"Password file contains no password line: {file_path}\n"
            f"Add a line with just your password (no '#' at the start)."
        )
    return candidates


def acquire_moodle_token_from_file(
    site_url: str,
    username: str,
    creds_path: str,
) -> MoodleToken:
    """Obtain a Moodle token using a username and a password file.

    Flow:
    1. Reads ALL non-comment, non-blank lines as password candidates.
    2. Tries each candidate against the Moodle login endpoint.
    3. First candidate that authenticates successfully wins.
    4. On any success: deletes the password file.
       On all-candidates-fail: leaves the file so the user can fix and retry.

    Multiple candidates are useful when users forget to delete placeholder
    text like "← ここに書く" and add their real password on a separate line.
    We try each harmlessly instead of forcing the user to clean up the file.

    Capped at MAX_PASSWORD_CANDIDATES to avoid spamming the Moodle endpoint.
    Only Moodle "Invalid login" errors trigger retry with the next candidate;
    network errors are raised immediately.

    Args:
        site_url: Base URL of the Moodle site.
        username: Moodle login email/username (passed via CLI flag).
        creds_path: Path to the password file.

    Returns:
        MoodleToken populated with token, user_id, site_url, created_at.

    Raises:
        RuntimeError: If all candidates fail auth, or on a non-auth error
            (network, server). File is NOT deleted when this raises.
        FileNotFoundError: If the password file does not exist.
        ValueError: If the password file has no candidate line, or > MAX.
    """
    resolved_path = str(Path(creds_path).expanduser())
    candidates = _read_password_candidates(resolved_path)

    if len(candidates) > MAX_PASSWORD_CANDIDATES:
        raise ValueError(
            f"Password file has {len(candidates)} non-comment lines "
            f"(maximum is {MAX_PASSWORD_CANDIDATES}): {resolved_path}\n"
            f"Please remove extra lines (keep only your password and comment lines)."
        )

    print(f"\nMoodle token acquisition for: {site_url}")
    print(f"Reading password from: {resolved_path}")
    if len(candidates) > 1:
        print(f"Found {len(candidates)} candidate lines; will try each until one works.")
    print("(Password values are not displayed.)\n")

    last_error: RuntimeError | None = None
    for idx, password in enumerate(candidates, start=1):
        if len(candidates) > 1:
            print(f"Attempt {idx}/{len(candidates)}...")
        try:
            token = acquire_moodle_token(site_url, username, password)
        except RuntimeError as e:
            err_msg = str(e)
            # Only retry on authentication failures. Network / server errors
            # won't improve by trying another candidate — fail fast.
            is_auth_failure = err_msg.startswith("Login failed:")
            if not is_auth_failure:
                raise
            last_error = e
            if idx < len(candidates):
                print("  → Rejected by server, trying next candidate...")
            continue

        # Success — delete the password file (plain unlink; shred unnecessary).
        try:
            os.unlink(resolved_path)
            print(f"Password file deleted: {resolved_path}")
        except OSError as unlink_err:
            logger.warning("Could not delete password file: %s", unlink_err)
        return token

    # All candidates exhausted with auth failures; do NOT delete the file.
    assert last_error is not None  # guaranteed by len(candidates) >= 1
    raise last_error


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
