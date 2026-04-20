"""JSON-based state management for shizen_lec_helper.

State is stored in ~/.config/shizen_lec_helper/state.json.
No SQLite — intentionally simple for distribution.

Schema:
{
  "synced_files": {
    "{course_shortname}/{relative_path}": {
      "time_modified": 1234567890,
      "filesize": 12345
    }
  },
  "last_sync": "2026-04-20T05:00:00",
  "known_courses": {
    "{shortname}": {
      "course_id": 123,
      "fullname": "...",
      "added_at": "2026-04-20T05:00:00"
    }
  }
}
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import make_config_paths

logger = logging.getLogger(__name__)

# Module-level default: resolved at import time from env/default.
# Commands that override config_dir pass it explicitly to each function.
_DEFAULT_STATE_PATH = make_config_paths()[3]


def _resolve_state_path(config_dir: Path | str | None = None) -> Path:
    """Return the state.json path for the given config_dir override."""
    return make_config_paths(config_dir)[3]


def _load_state(config_dir: Path | str | None = None) -> dict[str, Any]:
    """Load state from disk. Returns empty state if file does not exist."""
    state_path = _resolve_state_path(config_dir)
    if not state_path.exists():
        return {"synced_files": {}, "last_sync": None, "known_courses": {}}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load state from {state_path}: {e}")
        return {"synced_files": {}, "last_sync": None, "known_courses": {}}


def _save_state(state: dict[str, Any], config_dir: Path | str | None = None) -> None:
    """Atomically save state to disk."""
    state_path = _resolve_state_path(config_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = state_path.with_suffix(".json.tmp")
    try:
        temp_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(state_path)
    except Exception as e:
        logger.error(f"Failed to save state to {state_path}: {e}")
        raise


def is_file_synced(course_shortname: str, relative_path: str,
                   time_modified: int,
                   config_dir: Path | str | None = None) -> bool:
    """Return True if the file is already recorded as synced with this modification time."""
    state = _load_state(config_dir)
    key = f"{course_shortname}/{relative_path}"
    entry = state.get("synced_files", {}).get(key)
    if entry is None:
        return False
    return entry.get("time_modified", 0) >= time_modified


def record_synced_file(course_shortname: str, relative_path: str,
                       time_modified: int, filesize: int,
                       config_dir: Path | str | None = None) -> None:
    """Record that a file has been successfully synced."""
    state = _load_state(config_dir)
    key = f"{course_shortname}/{relative_path}"
    state.setdefault("synced_files", {})[key] = {
        "time_modified": time_modified,
        "filesize": filesize,
    }
    _save_state(state, config_dir)


def update_last_sync_timestamp(config_dir: Path | str | None = None) -> None:
    """Record the current UTC time as the last successful sync."""
    state = _load_state(config_dir)
    state["last_sync"] = datetime.now(timezone.utc).isoformat()
    _save_state(state, config_dir)


def get_last_sync_timestamp(config_dir: Path | str | None = None) -> str | None:
    """Return the ISO timestamp of the last successful sync, or None."""
    return _load_state(config_dir).get("last_sync")


def register_known_course(shortname: str, course_id: int, fullname: str,
                          config_dir: Path | str | None = None) -> bool:
    """Register a course as known. Returns True if it was newly added."""
    state = _load_state(config_dir)
    known = state.setdefault("known_courses", {})
    is_new = shortname not in known
    if is_new:
        known[shortname] = {
            "course_id": course_id,
            "fullname": fullname,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_state(state, config_dir)
        logger.info(f"New course registered: {shortname}")
    return is_new


def get_known_courses(config_dir: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Return all known courses as {shortname: {course_id, fullname, added_at}}."""
    return _load_state(config_dir).get("known_courses", {})


def get_sync_stats(config_dir: Path | str | None = None) -> dict[str, Any]:
    """Return a summary of sync state for the status command."""
    state = _load_state(config_dir)
    synced_files = state.get("synced_files", {})
    total_size = sum(v.get("filesize", 0) for v in synced_files.values())
    return {
        "total_files": len(synced_files),
        "total_size_bytes": total_size,
        "last_sync": state.get("last_sync"),
        "known_courses": len(state.get("known_courses", {})),
    }
