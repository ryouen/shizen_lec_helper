"""Configuration loading for shizen_lec_helper.

Config file location: ~/.config/shizen_lec_helper/config.json
Token file location:  ~/.config/shizen_lec_helper/moodle-token.json
State file location:  ~/.config/shizen_lec_helper/state.json

Config directory can be overridden via:
  - CLI flag:       --config-dir PATH  (highest priority)
  - Env variable:   SLH_CONFIG_DIR     (second priority)
  - Default:        ~/.config/shizen_lec_helper/
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# --- Constants ---

# Default config directory (overridable via SLH_CONFIG_DIR env var or --config-dir flag)
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "shizen_lec_helper"

# Default base path for downloaded course materials (overridable via SLH_BASE_PATH env var)
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


def resolve_config_dir(config_dir: Path | str | None = None) -> Path:
    """Resolve the config directory using priority: argument > SLH_CONFIG_DIR env > default.

    Args:
        config_dir: Explicit override from CLI flag, or None to use env/default.

    Returns:
        Resolved Path for the config directory.
    """
    if config_dir is not None:
        return Path(config_dir).expanduser()
    env_value = os.environ.get("SLH_CONFIG_DIR")
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_CONFIG_DIR


def resolve_base_path(base_path: Path | str | None = None) -> Path:
    """Resolve the base path using priority: argument > SLH_BASE_PATH env > default.

    Args:
        base_path: Explicit override from CLI flag, or None to use env/default.

    Returns:
        Resolved Path for the base directory.
    """
    if base_path is not None:
        return Path(base_path).expanduser()
    env_value = os.environ.get("SLH_BASE_PATH")
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_BASE_PATH


# Module-level path constants that reflect env-var defaults at import time.
# These are used by modules that have not yet been wired with explicit config_dir.
# When a CLI override is needed, use resolve_config_dir() instead.
CONFIG_DIR = resolve_config_dir()
CONFIG_PATH = CONFIG_DIR / "config.json"
TOKEN_PATH = CONFIG_DIR / "moodle-token.json"
STATE_PATH = CONFIG_DIR / "state.json"


def make_config_paths(config_dir: Path | str | None = None) -> tuple[Path, Path, Path, Path]:
    """Return (config_dir, config_path, token_path, state_path) for the given override.

    Uses resolve_config_dir() to determine the actual directory.

    Args:
        config_dir: Optional path override (from CLI --config-dir flag).

    Returns:
        Tuple of (config_dir, config_path, token_path, state_path) as Path objects.
    """
    resolved_dir = resolve_config_dir(config_dir)
    return (
        resolved_dir,
        resolved_dir / "config.json",
        resolved_dir / "moodle-token.json",
        resolved_dir / "state.json",
    )


@dataclass
class AppConfig:
    site_url: str = DEFAULT_SITE_URL
    base_path: Path = field(default_factory=lambda: resolve_base_path())
    active_courses: list[str] = field(default_factory=list)
    download_videos: bool = True
    new_course_policy: NewCoursePolicy = "ask"
    notification_format: NotificationFormat = "markdown"

    @classmethod
    def load(cls, config_dir: Path | str | None = None,
             base_path_override: Path | str | None = None) -> "AppConfig":
        """Load config from the resolved config directory.

        Priority for config_dir: argument > SLH_CONFIG_DIR env > default.
        Priority for base_path: config file value > base_path_override > SLH_BASE_PATH > default.

        Args:
            config_dir: Optional path override (from CLI --config-dir flag).
            base_path_override: Optional base path override (from CLI --base-path flag).

        Returns:
            AppConfig loaded from disk, or defaults if file not found.
        """
        _cfg_dir, cfg_path, _tok, _state = make_config_paths(config_dir)
        resolved_default_base = resolve_base_path(base_path_override)

        if not cfg_path.exists():
            logger.info(f"Config file not found at {cfg_path}; using defaults.")
            return cls(base_path=resolved_default_base)

        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to read config file {cfg_path}: {e}")
            raise

        # base_path from file, but honour override if provided
        raw_base = raw.get("base_path", str(resolved_default_base))
        effective_base = (
            Path(base_path_override).expanduser()
            if base_path_override is not None
            else Path(raw_base).expanduser()
        )

        return cls(
            site_url=raw.get("site_url", DEFAULT_SITE_URL),
            base_path=effective_base,
            active_courses=raw.get("active_courses", []),
            download_videos=raw.get("download_videos", True),
            new_course_policy=raw.get("new_course_policy", "ask"),
            notification_format=raw.get("notification_format", "markdown"),
        )

    def save(self, config_dir: Path | str | None = None) -> None:
        """Save current config to disk.

        Args:
            config_dir: Optional path override (from CLI --config-dir flag).
        """
        resolved_dir, cfg_path, _tok, _state = make_config_paths(config_dir)
        resolved_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "site_url": self.site_url,
            "base_path": str(self.base_path),
            "active_courses": self.active_courses,
            "download_videos": self.download_videos,
            "new_course_policy": self.new_course_policy,
            "notification_format": self.notification_format,
        }
        cfg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Config saved to {cfg_path}")


@dataclass
class MoodleToken:
    token: str
    user_id: int
    site_url: str
    created_at: str

    @classmethod
    def load(cls, config_dir: Path | str | None = None) -> "MoodleToken":
        """Load Moodle token from the resolved config directory.

        Args:
            config_dir: Optional path override (from CLI --config-dir flag).
        """
        _cfg_dir, _cfg, token_path, _state = make_config_paths(config_dir)
        if not token_path.exists():
            raise FileNotFoundError(
                f"Token file not found: {token_path}\n"
                "Run `python -m shizen_lec_helper setup` to obtain a token."
            )
        try:
            raw = json.loads(token_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to read token file {token_path}: {e}")
            raise

        return cls(
            token=raw["token"],
            user_id=raw["user_id"],
            site_url=raw.get("site_url", DEFAULT_SITE_URL),
            created_at=raw.get("created_at", ""),
        )

    def save(self, config_dir: Path | str | None = None) -> None:
        """Save token to disk. Never logs the token value.

        Args:
            config_dir: Optional path override (from CLI --config-dir flag).
        """
        resolved_dir, _cfg, token_path, _state = make_config_paths(config_dir)
        resolved_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "token": self.token,
            "user_id": self.user_id,
            "site_url": self.site_url,
            "created_at": self.created_at,
        }
        token_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        # Restrict permissions to owner-read-only
        token_path.chmod(0o600)
        logger.info(f"Token saved to {token_path}")


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
