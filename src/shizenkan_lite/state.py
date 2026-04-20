"""JSON-based state management for shizenkan-lite.

State is stored in ~/.config/shizenkan-lite/state.json.
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

from .config import STATE_PATH

logger = logging.getLogger(__name__)


def _load_state() -> dict[str, Any]:
    """Load state from disk. Returns empty state if file does not exist."""
    if not STATE_PATH.exists():
        return {"synced_files": {}, "last_sync": None, "known_courses": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load state from {STATE_PATH}: {e}")
        return {"synced_files": {}, "last_sync": None, "known_courses": {}}


def _save_state(state: dict[str, Any]) -> None:
    """Atomically save state to disk."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STATE_PATH.with_suffix(".json.tmp")
    try:
        temp_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(STATE_PATH)
    except Exception as e:
        logger.error(f"Failed to save state to {STATE_PATH}: {e}")
        raise


def is_file_synced(course_shortname: str, relative_path: str,
                   time_modified: int) -> bool:
    """Return True if the file is already recorded as synced with this modification time."""
    state = _load_state()
    key = f"{course_shortname}/{relative_path}"
    entry = state.get("synced_files", {}).get(key)
    if entry is None:
        return False
    return entry.get("time_modified", 0) >= time_modified


def record_synced_file(course_shortname: str, relative_path: str,
                       time_modified: int, filesize: int) -> None:
    """Record that a file has been successfully synced."""
    state = _load_state()
    key = f"{course_shortname}/{relative_path}"
    state.setdefault("synced_files", {})[key] = {
        "time_modified": time_modified,
        "filesize": filesize,
    }
    _save_state(state)


def update_last_sync_timestamp() -> None:
    """Record the current UTC time as the last successful sync."""
    state = _load_state()
    state["last_sync"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)


def get_last_sync_timestamp() -> str | None:
    """Return the ISO timestamp of the last successful sync, or None."""
    return _load_state().get("last_sync")


def register_known_course(shortname: str, course_id: int, fullname: str) -> bool:
    """Register a course as known. Returns True if it was newly added."""
    state = _load_state()
    known = state.setdefault("known_courses", {})
    is_new = shortname not in known
    if is_new:
        known[shortname] = {
            "course_id": course_id,
            "fullname": fullname,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_state(state)
        logger.info(f"New course registered: {shortname}")
    return is_new


def get_known_courses() -> dict[str, dict[str, Any]]:
    """Return all known courses as {shortname: {course_id, fullname, added_at}}."""
    return _load_state().get("known_courses", {})


def get_sync_stats() -> dict[str, Any]:
    """Return a summary of sync state for the status command."""
    state = _load_state()
    synced_files = state.get("synced_files", {})
    total_size = sum(v.get("filesize", 0) for v in synced_files.values())
    return {
        "total_files": len(synced_files),
        "total_size_bytes": total_size,
        "last_sync": state.get("last_sync"),
        "known_courses": len(state.get("known_courses", {})),
    }
