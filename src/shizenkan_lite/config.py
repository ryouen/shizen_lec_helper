"""Configuration loading for shizenkan-lite.

Config file location: ~/.config/shizenkan-lite/config.json
Token file location:  ~/.config/shizenkan-lite/moodle-token.json
State file location:  ~/.config/shizenkan-lite/state.json
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# --- Constants ---

CONFIG_DIR = Path.home() / ".config" / "shizenkan-lite"
CONFIG_PATH = CONFIG_DIR / "config.json"
TOKEN_PATH = CONFIG_DIR / "moodle-token.json"
STATE_PATH = CONFIG_DIR / "state.json"

DEFAULT_BASE_PATH = Path.home() / "Shizenkan"

# Default Moodle site URL (can be overridden in config)
DEFAULT_SITE_URL = "https://campus.shizenkan.ac.jp"

# Active course detection thresholds
ACTIVE_COURSE_LOOKAHEAD_DAYS = 14  # days ahead to look for future deadlines
ACTIVE_COURSE_RECENT_UPDATE_DAYS = 14  # days back to check for recent updates

# Video download folder name within each course folder
VIDEO_FOLDER_NAME = "LEC_VIDEO"

# Cross-course deadlines file
DEADLINES_FILENAME = "_deadlines.md"

# Links summary file per course
LINKS_FILENAME = "_links.md"

NewCoursePolicy = Literal["auto", "ask", "ignore"]
NotificationFormat = Literal["markdown", "macos", "email"]


@dataclass
class AppConfig:
    site_url: str = DEFAULT_SITE_URL
    base_path: Path = field(default_factory=lambda: DEFAULT_BASE_PATH)
    active_courses: list[str] = field(default_factory=list)
    download_videos: bool = True
    new_course_policy: NewCoursePolicy = "ask"
    notification_format: NotificationFormat = "markdown"

    @classmethod
    def load(cls) -> "AppConfig":
        """Load config from ~/.config/shizenkan-lite/config.json.

        Returns default config if file does not exist.
        """
        if not CONFIG_PATH.exists():
            logger.info(f"Config file not found at {CONFIG_PATH}; using defaults.")
            return cls()

        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to read config file {CONFIG_PATH}: {e}")
            raise

        return cls(
            site_url=raw.get("site_url", DEFAULT_SITE_URL),
            base_path=Path(raw.get("base_path", str(DEFAULT_BASE_PATH))).expanduser(),
            active_courses=raw.get("active_courses", []),
            download_videos=raw.get("download_videos", True),
            new_course_policy=raw.get("new_course_policy", "ask"),
            notification_format=raw.get("notification_format", "markdown"),
        )

    def save(self) -> None:
        """Save current config to disk."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "site_url": self.site_url,
            "base_path": str(self.base_path),
            "active_courses": self.active_courses,
            "download_videos": self.download_videos,
            "new_course_policy": self.new_course_policy,
            "notification_format": self.notification_format,
        }
        CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Config saved to {CONFIG_PATH}")


@dataclass
class MoodleToken:
    token: str
    user_id: int
    site_url: str
    created_at: str

    @classmethod
    def load(cls) -> "MoodleToken":
        """Load Moodle token from ~/.config/shizenkan-lite/moodle-token.json."""
        if not TOKEN_PATH.exists():
            raise FileNotFoundError(
                f"Token file not found: {TOKEN_PATH}\n"
                "Run `python -m shizenkan_lite setup` to obtain a token."
            )
        try:
            raw = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to read token file {TOKEN_PATH}: {e}")
            raise

        return cls(
            token=raw["token"],
            user_id=raw["user_id"],
            site_url=raw.get("site_url", DEFAULT_SITE_URL),
            created_at=raw.get("created_at", ""),
        )

    def save(self) -> None:
        """Save token to disk. Never logs the token value."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "token": self.token,
            "user_id": self.user_id,
            "site_url": self.site_url,
            "created_at": self.created_at,
        }
        TOKEN_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        # Restrict permissions to owner-read-only
        TOKEN_PATH.chmod(0o600)
        logger.info(f"Token saved to {TOKEN_PATH}")


def moodle_api_endpoint(site_url: str) -> str:
    """Build the Moodle REST API endpoint URL from the site base URL."""
    return f"{site_url.rstrip('/')}/webservice/rest/server.php"


def canonical_session_folder(section_name: str) -> tuple[int, str] | None:
    """Derive a canonical local folder name from a Moodle section name.

    Returns (session_num, folder_name) or None if not a numbered session.
    Convention: "Session {N} - {keyword_phrase}" (max ~65 chars, word-boundary truncation).

    Adapted from shizenkan/config.py for standalone use.
    """
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKC", section_name)
    # Remove smart quotes
    for ch in "\u2018\u2019\u201c\u201d":
        normalized = normalized.replace(ch, "")

    m = re.search(r"[Ss]ession\s*#?\s*(\d+)", normalized)
    if not m:
        return None

    session_num = int(m.group(1))
    rest = normalized[m.end():].strip()

    # Strip leading separators
    rest = re.sub(r"^[\s:;\-\u2013\u2014_.]+", "", rest).strip()
    if not rest:
        return (session_num, f"Session {session_num}")

    # Remove trailing [Professor] tag
    rest = re.sub(r"\s*\[.*?\]\s*$", "", rest).strip()

    # Take first clause only (up to first major delimiter)
    for delim in (" - ", " & ", " \u2013 ", " \u2014 "):
        idx = rest.find(delim)
        if 0 < idx:
            rest = rest[:idx].strip()
            break

    # Cap at 7 words
    words = rest.split()[:7]
    rest = " ".join(words)

    # Remove forbidden filesystem characters
    rest = re.sub(r'[<>:"/\\|?*]', "", rest)
    rest = re.sub(r"\s+", " ", rest).strip()

    if not rest:
        return (session_num, f"Session {session_num}")

    folder_name = f"Session {session_num} - {rest}"

    # Hard cap at 65 chars, truncate at word boundary
    if len(folder_name) > 65:
        folder_name = folder_name[:65].rsplit(" ", 1)[0]

    return (session_num, folder_name)


def canonical_special_folder(section_name: str) -> str | None:
    """Derive canonical folder for non-session sections (Supplemental, TA Review, etc.).

    Returns None for "General" (files go to course root).

    Adapted from shizenkan/config.py for standalone use.
    """
    import re

    normalized = section_name.strip()
    lower = normalized.lower()

    if not lower or lower == "general":
        return None

    if "supplemental" in lower and "session" in lower:
        return "Supplemental Session"
    if "ta review" in lower:
        return "TA Review Session"

    # Unknown non-session section: basic sanitize
    cleaned = re.sub(r'[<>:"/\\|?*]', "", normalized)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:65] if cleaned else None
