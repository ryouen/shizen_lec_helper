"""File sync: SOS (Moodle) → ~/Shizenkan/ local filesystem.

Syncs PDFs, slides, assignment files from active courses.
Skips files that have not changed since the last sync (based on time_modified).
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .config import AppConfig, VIDEO_FOLDER_NAME, LINKS_FILENAME, canonical_session_folder, canonical_special_folder
from .sos import MoodleFile, MoodleSection, SOSClient, _extract_links_from_html
from .state import is_file_synced, record_synced_file

logger = logging.getLogger(__name__)

# Maximum filename length for local filesystem safety
MAX_FILENAME_LENGTH = 200


@dataclass
class CourseSyncResult:
    course_shortname: str
    files_downloaded: int = 0
    files_skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        logger.error(msg)


@dataclass
class SyncResult:
    courses_synced: list[CourseSyncResult] = field(default_factory=list)

    @property
    def total_downloaded(self) -> int:
        return sum(c.files_downloaded for c in self.courses_synced)

    @property
    def total_skipped(self) -> int:
        return sum(c.files_skipped for c in self.courses_synced)

    @property
    def all_errors(self) -> list[str]:
        errors = []
        for c in self.courses_synced:
            errors.extend(c.errors)
        return errors


def sync_active_courses(sos: SOSClient, config: AppConfig,
                        dry_run: bool = False,
                        config_dir: "Path | str | None" = None) -> SyncResult:
    """Sync all active courses listed in config.active_courses.

    Args:
        sos: Authenticated SOS API client.
        config: App configuration.
        dry_run: If True, log what would be downloaded but don't write files.
        config_dir: Optional config directory override for state isolation.

    Returns:
        SyncResult with per-course stats.
    """
    overall = SyncResult()

    enrolled_courses = sos.get_courses()
    course_map = {c.shortname: c for c in enrolled_courses}

    for shortname in config.active_courses:
        course = course_map.get(shortname)
        if not course:
            logger.warning(f"Active course not found in enrollment: {shortname}")
            continue

        course_result = CourseSyncResult(course_shortname=shortname)
        logger.info(f"Syncing course: {shortname} ({course.fullname})")

        try:
            _sync_single_course(
                sos=sos,
                course_id=course.id,
                course_shortname=shortname,
                course_fullname=course.fullname,
                base_path=config.base_path,
                course_result=course_result,
                dry_run=dry_run,
                config_dir=config_dir,
            )
        except Exception as e:
            course_result.add_error(f"Unexpected error syncing {shortname}: {e}")

        overall.courses_synced.append(course_result)

    return overall


def _sync_single_course(
    sos: SOSClient,
    course_id: int,
    course_shortname: str,
    course_fullname: str,
    base_path: Path,
    course_result: CourseSyncResult,
    dry_run: bool,
    config_dir: "Path | str | None" = None,
) -> None:
    """Sync all files for a single course."""
    # Use short name for directory (e.g. FINANCE_EN_2027 → FINANCE_EN_2027/)
    course_dir = base_path / _sanitize_dirname(course_shortname)

    if not dry_run:
        course_dir.mkdir(parents=True, exist_ok=True)

    # --- Resource files (PDFs, slides, etc.) ---
    file_pairs = sos.extract_files(course_id)
    for section, moodle_file in file_pairs:
        section_dir = _resolve_section_dir(course_dir, section.name)
        _download_file_if_needed(
            sos=sos,
            moodle_file=moodle_file,
            target_dir=section_dir,
            course_shortname=course_shortname,
            course_result=course_result,
            dry_run=dry_run,
            config_dir=config_dir,
        )

    # --- Assignment attachment files ---
    try:
        assign_files = sos.extract_assignment_files(course_id)
        for section_name, moodle_file in assign_files:
            section_dir = _resolve_section_dir(course_dir, section_name)
            _download_file_if_needed(
                sos=sos,
                moodle_file=moodle_file,
                target_dir=section_dir,
                course_shortname=course_shortname,
                course_result=course_result,
                dry_run=dry_run,
                config_dir=config_dir,
            )
    except Exception as e:
        course_result.add_error(f"Error fetching assignment files for {course_shortname}: {e}")

    # --- Write _links.md for this course ---
    try:
        _write_links_file(sos, course_id, course_dir, course_fullname, dry_run)
    except Exception as e:
        logger.warning(f"Could not write _links.md for {course_shortname}: {e}")


def _download_file_if_needed(
    sos: SOSClient,
    moodle_file: MoodleFile,
    target_dir: Path,
    course_shortname: str,
    course_result: CourseSyncResult,
    dry_run: bool,
    config_dir: "Path | str | None" = None,
) -> None:
    """Download a single Moodle file if not already synced."""
    safe_filename = _sanitize_filename(moodle_file.filename)
    # Relative path for state tracking
    relative_path = str(target_dir.name) + "/" + safe_filename

    if is_file_synced(course_shortname, relative_path, moodle_file.time_modified,
                      config_dir=config_dir):
        course_result.files_skipped += 1
        logger.debug(f"Skip (up to date): {safe_filename}")
        return

    if dry_run:
        logger.info(f"[dry-run] Would download: {target_dir / safe_filename}")
        course_result.files_downloaded += 1
        return

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        file_bytes = sos.download_file(moodle_file.fileurl)
        target_path = target_dir / safe_filename
        target_path.write_bytes(file_bytes)
        record_synced_file(
            course_shortname=course_shortname,
            relative_path=relative_path,
            time_modified=moodle_file.time_modified,
            filesize=len(file_bytes),
            config_dir=config_dir,
        )
        logger.info(f"Downloaded: {target_path}")
        course_result.files_downloaded += 1
    except Exception as e:
        course_result.add_error(f"Failed to download {moodle_file.filename}: {e}")


def _resolve_section_dir(course_dir: Path, section_name: str) -> Path:
    """Map a Moodle section name to a local directory path.

    Rules:
    - Numbered sessions → "Session N - Title/"
    - Special sections (Supplemental, TA Review) → named folder
    - "General" or unknown → course root
    """
    parsed_session = canonical_session_folder(section_name)
    if parsed_session:
        _session_num, folder_name = parsed_session
        return course_dir / folder_name

    special = canonical_special_folder(section_name)
    if special:
        return course_dir / special

    # Fall back to course root for unrecognized sections
    return course_dir


def _write_links_file(sos: SOSClient, course_id: int,
                      course_dir: Path, course_fullname: str,
                      dry_run: bool) -> None:
    """Write a Markdown file listing external links found in the course."""
    sections = sos.get_course_contents(course_id)
    links: list[tuple[str, str, str]] = []  # (section_name, module_name, url)

    skip_domains = {"campus.shizenkan.ac.jp", "vimeo.com", "zoom.us"}

    def _should_skip(url: str) -> bool:
        return any(domain in url for domain in skip_domains)

    for section in sections:
        for module in section.modules:
            if module.get("modname") == "url":
                for content in module.get("contents", []):
                    url = content.get("fileurl", "")
                    if url and not _should_skip(url):
                        links.append((section.name, module.get("name", ""), url))

    if not links:
        return

    lines = [f"# Links — {course_fullname}\n"]
    current_section = None
    for section_name, module_name, url in links:
        if section_name != current_section:
            lines.append(f"\n## {section_name}\n")
            current_section = section_name
        lines.append(f"- [{module_name}]({url})\n")

    content = "".join(lines)
    links_path = course_dir / LINKS_FILENAME

    if dry_run:
        logger.info(f"[dry-run] Would write: {links_path}")
        return

    course_dir.mkdir(parents=True, exist_ok=True)
    links_path.write_text(content, encoding="utf-8")
    logger.info(f"Wrote {links_path}")


def _sanitize_dirname(name: str) -> str:
    """Sanitize a course name for use as a directory name."""
    import re
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return cleaned.strip()[:100]


def _sanitize_filename(filename: str) -> str:
    """Sanitize a filename for the local filesystem."""
    import re
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
    return cleaned.strip()[:MAX_FILENAME_LENGTH]
