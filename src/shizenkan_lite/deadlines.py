"""Deadline extraction and Markdown output for active courses.

Fetches assignments from SOS, filters future deadlines, and writes
~/Shizenkan/_deadlines.md as a cross-course summary.
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import AppConfig, DEADLINES_FILENAME
from .sos import MoodleAssignment, SOSClient

logger = logging.getLogger(__name__)

# Japan Standard Time offset
JST_OFFSET = timezone(timedelta(hours=9))

# Assignments with due_date of 0 have no deadline (skip them)
NO_DEADLINE_SENTINEL = 0

# Only show deadlines within this many days ahead in the summary
DEADLINE_LOOKAHEAD_DAYS = 60


def fetch_upcoming_deadlines(
    sos: SOSClient,
    config: AppConfig,
) -> list[dict]:
    """Fetch upcoming assignments from all active courses.

    Returns a list of dicts sorted by due_date ascending:
    [
      {
        "course": str,
        "name": str,
        "due_date": int,          # unix timestamp
        "due_str": str,           # human-readable in JST
        "days_left": int,
        "cutoff_date": int,
      },
      ...
    ]
    """
    enrolled_courses = sos.get_courses()
    course_name_map = {c.shortname: c.fullname for c in enrolled_courses}

    active_course_ids: list[int] = []
    active_shortnames: list[str] = config.active_courses

    for course in enrolled_courses:
        if course.shortname in active_shortnames:
            active_course_ids.append(course.id)

    if not active_course_ids:
        logger.warning("No active courses found to fetch deadlines for.")
        return []

    try:
        assignments = sos.get_assignments(active_course_ids)
    except Exception as e:
        logger.error(f"Failed to fetch assignments: {e}")
        raise

    now = datetime.now(JST_OFFSET)
    lookahead_cutoff = now + timedelta(days=DEADLINE_LOOKAHEAD_DAYS)

    upcoming: list[dict] = []
    shortname_by_course_id = {c.id: c.shortname for c in enrolled_courses}

    for assignment in assignments:
        if assignment.due_date == NO_DEADLINE_SENTINEL:
            continue

        due_dt = datetime.fromtimestamp(assignment.due_date, tz=JST_OFFSET)

        # Skip past deadlines (already overdue)
        if due_dt < now:
            continue

        # Skip deadlines too far in the future
        if due_dt > lookahead_cutoff:
            continue

        shortname = shortname_by_course_id.get(assignment.course_id, str(assignment.course_id))
        days_left = (due_dt - now).days

        upcoming.append({
            "course": shortname,
            "course_fullname": course_name_map.get(shortname, shortname),
            "name": assignment.name,
            "due_date": assignment.due_date,
            "due_str": due_dt.strftime("%Y-%m-%d %H:%M JST"),
            "days_left": days_left,
            "cutoff_date": assignment.cutoff_date,
        })

    upcoming.sort(key=lambda x: x["due_date"])
    return upcoming


def write_deadlines_markdown(
    deadlines: list[dict],
    config: AppConfig,
    dry_run: bool = False,
) -> Path:
    """Write the cross-course deadline summary to ~/Shizenkan/_deadlines.md.

    Returns the path that was written (or would be written in dry-run mode).
    """
    output_path = config.base_path / DEADLINES_FILENAME
    generated_at = datetime.now(JST_OFFSET).strftime("%Y-%m-%d %H:%M JST")

    lines = [
        f"# Upcoming Deadlines\n",
        f"\n_Generated: {generated_at}_\n\n",
    ]

    if not deadlines:
        lines.append("No upcoming deadlines in the next "
                     f"{DEADLINE_LOOKAHEAD_DAYS} days.\n")
    else:
        lines.append(f"| Course | Assignment | Due | Days Left |\n")
        lines.append(f"|--------|-----------|-----|----------|\n")
        for item in deadlines:
            urgency_marker = "🔴 " if item["days_left"] <= 2 else (
                "🟡 " if item["days_left"] <= 7 else ""
            )
            lines.append(
                f"| {item['course']} "
                f"| {urgency_marker}{item['name']} "
                f"| {item['due_str']} "
                f"| {item['days_left']}d |\n"
            )

    content = "".join(lines)

    if dry_run:
        logger.info(f"[dry-run] Would write deadlines to: {output_path}")
        print(content)
        return output_path

    config.base_path.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    logger.info(f"Wrote deadlines to: {output_path}")
    return output_path


def print_deadlines_table(deadlines: list[dict]) -> None:
    """Print a formatted deadline table to stdout."""
    if not deadlines:
        print("No upcoming deadlines.")
        return

    print(f"\n{'Course':<25} {'Days':>4}  {'Due':<20}  Assignment")
    print("-" * 80)
    for item in deadlines:
        urgency = " !" if item["days_left"] <= 2 else ""
        print(
            f"{item['course']:<25} {item['days_left']:>4}d  "
            f"{item['due_str']:<20}  {item['name']}{urgency}"
        )
    print()


def determine_active_courses(
    sos: SOSClient,
    enrolled_courses: list,
) -> list[str]:
    """Determine which courses are 'active' based on future deadlines or recent updates.

    A course is considered active if it has:
    - At least one assignment due in the future, OR
    - Content updated within the last ACTIVE_COURSE_RECENT_UPDATE_DAYS days

    Returns a list of course shortnames.
    """
    from .config import ACTIVE_COURSE_LOOKAHEAD_DAYS, ACTIVE_COURSE_RECENT_UPDATE_DAYS
    import time

    now_ts = int(time.time())
    recent_threshold_ts = now_ts - (ACTIVE_COURSE_RECENT_UPDATE_DAYS * 86400)

    active_shortnames: list[str] = []

    for course in enrolled_courses:
        is_active = False

        # Check: future assignments exist
        try:
            assignments = sos.get_assignments([course.id])
            for a in assignments:
                if a.due_date > now_ts:
                    is_active = True
                    break
        except Exception as e:
            logger.warning(f"Could not fetch assignments for {course.shortname}: {e}")

        if not is_active:
            # Check: recent updates
            try:
                updates = sos.get_updates_since(course.id, recent_threshold_ts)
                # If any instance was updated, the course is active
                instances = updates.get("instances", [])
                if instances:
                    is_active = True
            except Exception as e:
                logger.warning(f"Could not fetch updates for {course.shortname}: {e}")

        if is_active:
            active_shortnames.append(course.shortname)
            logger.info(f"Active course detected: {course.shortname}")
        else:
            logger.info(f"Inactive course (no future deadlines/updates): {course.shortname}")

    return active_shortnames
