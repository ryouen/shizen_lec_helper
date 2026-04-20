"""Moodle REST API client for Shizenkan Online System (SOS).

Standalone version — no dependency on libs/core or shizenkan package.
Uses only the standard library + requests.
"""

import logging
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

import requests

from .config import MoodleToken, moodle_api_endpoint

logger = logging.getLogger(__name__)

# Timeout for individual HTTP requests (seconds)
HTTP_TIMEOUT_SECONDS = 30


class MoodleAPIError(Exception):
    def __init__(self, message: str, errorcode: str):
        self.errorcode = errorcode
        super().__init__(f"Moodle API Error [{errorcode}]: {message}")


@dataclass
class MoodleCourse:
    id: int
    shortname: str
    fullname: str
    summary: str
    time_modified: int = 0  # unix timestamp of last modification


@dataclass
class MoodleFile:
    filename: str
    fileurl: str
    filesize: int
    time_modified: int
    mimetype: str | None = None


@dataclass
class MoodleSection:
    id: int
    name: str
    summary: str
    modules: list[dict[str, Any]]


@dataclass
class MoodleAssignment:
    id: int
    course_id: int
    name: str
    intro: str
    due_date: int      # unix timestamp; 0 = no deadline
    cutoff_date: int   # unix timestamp; 0 = no cutoff
    attachments: list[MoodleFile]


@dataclass
class MoodleVideo:
    """A Vimeo video link found in course content."""
    course_id: int
    section_name: str
    module_name: str
    url: str
    password: str | None = None


class SOSClient:
    """Client for Shizenkan Online System (Moodle REST API).

    Standalone version using requests (not httpx).
    """

    def __init__(self, token: MoodleToken | None = None,
                 config_dir: "Path | str | None" = None):
        from pathlib import Path
        self._token = token or MoodleToken.load(config_dir=config_dir)
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "shizen_lec_helper/0.1.0"})
        self._api_url = moodle_api_endpoint(self._token.site_url)

    def _call(self, function: str, **params: Any) -> Any:
        """Call a Moodle Web Service function and return parsed JSON."""
        payload = {
            "wstoken": self._token.token,
            "wsfunction": function,
            "moodlewsrestformat": "json",
        }
        payload.update(params)

        try:
            resp = self._session.get(self._api_url, params=payload,
                                     timeout=HTTP_TIMEOUT_SECONDS)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"HTTP error calling {function}: {e}")
            raise

        data = resp.json()
        if isinstance(data, dict) and "exception" in data:
            raise MoodleAPIError(data["message"], data.get("errorcode", "unknown"))
        return data

    def get_site_info(self) -> dict[str, Any]:
        """Call core_webservice_get_site_info for connectivity check."""
        return self._call("core_webservice_get_site_info")

    def get_courses(self) -> list[MoodleCourse]:
        """Get all enrolled courses for the authenticated user."""
        data = self._call("core_enrol_get_users_courses", userid=self._token.user_id)
        return [
            MoodleCourse(
                id=c["id"],
                shortname=c["shortname"],
                fullname=c["fullname"],
                summary=c.get("summary", ""),
                time_modified=c.get("timemodified", 0),
            )
            for c in data
        ]

    def get_course_contents(self, course_id: int) -> list[MoodleSection]:
        """Get all sections and modules for a course."""
        data = self._call("core_course_get_contents", courseid=course_id)
        return [
            MoodleSection(
                id=s["id"],
                name=s["name"],
                summary=s.get("summary", ""),
                modules=s.get("modules", []),
            )
            for s in data
        ]

    def get_assignments(self, course_ids: list[int]) -> list[MoodleAssignment]:
        """Get all assignments for the given course IDs."""
        params: dict[str, Any] = {}
        for i, cid in enumerate(course_ids):
            params[f"courseids[{i}]"] = cid

        data = self._call("mod_assign_get_assignments", **params)
        assignments: list[MoodleAssignment] = []

        for course_data in data.get("courses", []):
            cid = course_data["id"]
            for a in course_data.get("assignments", []):
                attachments = [
                    MoodleFile(
                        filename=att["filename"],
                        fileurl=att.get("fileurl", ""),
                        filesize=att.get("filesize", 0),
                        time_modified=att.get("timemodified", 0),
                    )
                    for att in a.get("introattachments", [])
                ]
                assignments.append(MoodleAssignment(
                    id=a["id"],
                    course_id=cid,
                    name=a["name"],
                    intro=a.get("intro", ""),
                    due_date=a.get("duedate", 0),
                    cutoff_date=a.get("cutoffdate", 0),
                    attachments=attachments,
                ))

        return assignments

    def get_updates_since(self, course_id: int, since_timestamp: int) -> dict[str, Any]:
        """Check whether a course has been updated since the given unix timestamp."""
        return self._call("core_course_get_updates_since",
                          courseid=course_id, since=since_timestamp)

    def extract_files(self, course_id: int) -> list[tuple[MoodleSection, MoodleFile]]:
        """Extract all downloadable files from a course with their section context."""
        sections = self.get_course_contents(course_id)
        results: list[tuple[MoodleSection, MoodleFile]] = []

        for section in sections:
            for module in section.modules:
                for content in module.get("contents", []):
                    if content.get("type") != "file":
                        continue
                    # Skip auto-generated index.html from page modules
                    if content["filename"] == "index.html":
                        continue
                    file_entry = MoodleFile(
                        filename=content["filename"],
                        fileurl=content["fileurl"],
                        filesize=content.get("filesize", 0),
                        time_modified=content.get("timemodified", 0),
                        mimetype=content.get("mimetype"),
                    )
                    results.append((section, file_entry))

        return results

    def extract_assignment_files(self, course_id: int) -> list[tuple[str, MoodleFile]]:
        """Extract files attached to assignments (introattachments).

        Returns list of (section_name, MoodleFile) pairs.
        """
        # Build assignment_id → section_name mapping
        sections = self.get_course_contents(course_id)
        assign_section_map: dict[int, str] = {}
        for section in sections:
            for module in section.modules:
                if module.get("modname") == "assign":
                    assign_section_map[module["instance"]] = section.name

        data = self._call("mod_assign_get_assignments", **{"courseids[0]": course_id})
        results: list[tuple[str, MoodleFile]] = []

        for course_data in data.get("courses", []):
            for a in course_data.get("assignments", []):
                section_name = assign_section_map.get(a["id"], "General")
                for att in a.get("introattachments", []):
                    file_entry = MoodleFile(
                        filename=att["filename"],
                        fileurl=att.get("fileurl", ""),
                        filesize=att.get("filesize", 0),
                        time_modified=att.get("timemodified", 0),
                    )
                    results.append((section_name, file_entry))

        return results

    def extract_videos(self, course_id: int) -> list[MoodleVideo]:
        """Extract Vimeo video links from a course.

        Searches URL modules and assignment intro HTML.
        """
        import re

        sections = self.get_course_contents(course_id)
        videos: list[MoodleVideo] = []
        seen_urls: set[str] = set()

        # 1. URL modules containing Vimeo links
        for section in sections:
            for module in section.modules:
                if module.get("modname") != "url":
                    continue
                vimeo_url = None
                for content in module.get("contents", []):
                    fileurl = content.get("fileurl", "")
                    if "vimeo.com" in fileurl:
                        vimeo_url = fileurl
                        break
                if not vimeo_url:
                    module_url = module.get("url", "")
                    if "vimeo.com" in module_url:
                        vimeo_url = module_url

                if vimeo_url:
                    password = _extract_vimeo_password(module)
                    videos.append(MoodleVideo(
                        course_id=course_id,
                        section_name=section.name,
                        module_name=module.get("name", ""),
                        url=vimeo_url,
                        password=password,
                    ))
                    seen_urls.add(vimeo_url)

        # 2. Assignment intro HTML (pre-session / reference videos)
        assign_section_map: dict[int, str] = {}
        for section in sections:
            for module in section.modules:
                if module.get("modname") == "assign":
                    assign_section_map[module["instance"]] = section.name

        try:
            data = self._call("mod_assign_get_assignments", **{"courseids[0]": course_id})
            pw_patterns = [
                r"[Pp]assword\s*[:：]\s*([A-Za-z0-9_\-]+)",
                r"[Pp][Ww]\s*[:：]\s*([A-Za-z0-9_\-]+)",
                r"パスワード\s*[:：]\s*([A-Za-z0-9_\-]+)",
                r"[Pp][Aa][Ss][Ss]\s*[:：]\s*([A-Za-z0-9_\-]+)",
            ]

            for course_data in data.get("courses", []):
                for a in course_data.get("assignments", []):
                    intro = a.get("intro", "") or ""
                    if "vimeo.com" not in intro:
                        continue

                    section_name = assign_section_map.get(a["id"], "General")
                    assign_name = a.get("name", "")

                    intro_password: str | None = None
                    for pat in pw_patterns:
                        match = re.search(pat, intro)
                        if match:
                            intro_password = match.group(1)
                            break

                    for url, text in _extract_links_from_html(intro):
                        if "vimeo.com" not in url:
                            continue
                        url = url.replace("&amp;", "&")
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        label = text if text else assign_name
                        videos.append(MoodleVideo(
                            course_id=course_id,
                            section_name=section_name,
                            module_name=label,
                            url=url,
                            password=intro_password,
                        ))

                    # Catch bare Vimeo URLs not wrapped in <a> tags
                    for url in re.findall(r"https?://(?:www\.)?vimeo\.com/\d+", intro):
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)
                        videos.append(MoodleVideo(
                            course_id=course_id,
                            section_name=section_name,
                            module_name=assign_name,
                            url=url,
                            password=intro_password,
                        ))

        except Exception as e:
            logger.warning(f"Error extracting assignment videos for course {course_id}: {e}")

        return videos

    def download_file(self, file_url: str) -> bytes:
        """Download a Moodle file, appending the auth token to the URL."""
        separator = "&" if "?" in file_url else "?"
        authenticated_url = f"{file_url}{separator}token={self._token.token}"
        try:
            resp = self._session.get(authenticated_url, timeout=HTTP_TIMEOUT_SECONDS,
                                     stream=False, allow_redirects=True)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as e:
            logger.error(f"Failed to download file from {file_url}: {e}")
            raise

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def __enter__(self) -> "SOSClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# --- Module-level helpers ---

def _extract_vimeo_password(module: dict[str, Any]) -> str | None:
    """Try to extract a Vimeo password from module name, description, or content names."""
    import re

    patterns = [
        r"[Pp]assword\s*[:：]\s*([A-Za-z0-9_\-]+)",
        r"パスワード\s*[:：]\s*([A-Za-z0-9_\-]+)",
        r"[Pp][Ww]\s*[:：]\s*([A-Za-z0-9_\-]+)",
        r"[Pp][Aa][Ss][Ss]\s*[:：]\s*([A-Za-z0-9_\-]+)",
    ]

    # Search module name, then description, then content filenames
    search_targets = [
        module.get("name", ""),
        module.get("description", ""),
        *[c.get("filename", "") for c in module.get("contents", [])],
    ]

    for target in search_targets:
        for pattern in patterns:
            match = re.search(pattern, target)
            if match:
                return match.group(1)

    return None


def _extract_links_from_html(html: str) -> list[tuple[str, str]]:
    """Extract (url, link_text) pairs from HTML content."""

    class _LinkParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.links: list[tuple[str, str]] = []
            self._current_href: str | None = None
            self._current_text: str = ""

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag == "a":
                for attr, val in attrs:
                    if attr == "href" and val and val.startswith("http"):
                        self._current_href = val
                        self._current_text = ""

        def handle_data(self, data: str) -> None:
            if self._current_href is not None:
                self._current_text += data

        def handle_endtag(self, tag: str) -> None:
            if tag == "a" and self._current_href:
                self.links.append((self._current_href, self._current_text.strip()))
                self._current_href = None
                self._current_text = ""

    parser = _LinkParser()
    parser.feed(html)
    return parser.links
