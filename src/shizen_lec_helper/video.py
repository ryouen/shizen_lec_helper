"""Vimeo video download via yt-dlp subprocess.

Downloads lecture videos from Vimeo links found in SOS course content,
saving them to ~/Shizenkan/{course}/LEC_VIDEO/.

Uses yt-dlp as a subprocess (not the Python API) to stay compatible
with Homebrew-installed yt-dlp that includes curl_cffi for Vimeo impersonation.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from .config import AppConfig, VIDEO_FOLDER_NAME
from .sos import MoodleVideo, SOSClient

logger = logging.getLogger(__name__)

# yt-dlp format selector: prefer 720p or lower to save storage
YTDLP_FORMAT = "bestvideo[height<=720]+bestaudio/best[height<=720]"

# Merge output format for combined streams
YTDLP_MERGE_FORMAT = "mp4"

# Download timeout per video (seconds)
DOWNLOAD_TIMEOUT_SECONDS = 3600  # 1 hour max

# Maximum consecutive password failures before giving up
MAX_PASSWORD_ATTEMPTS = 5


def download_course_videos(
    sos: SOSClient,
    config: AppConfig,
    course_shortname: str,
    course_id: int,
    dry_run: bool = False,
) -> dict[str, int]:
    """Download all Vimeo videos for a single course.

    Saves to ~/Shizenkan/{course_shortname}/LEC_VIDEO/.

    Returns:
        dict with keys "downloaded", "skipped", "failed"
    """
    stats = {"downloaded": 0, "skipped": 0, "failed": 0}

    video_dir = config.base_path / _sanitize_dirname(course_shortname) / VIDEO_FOLDER_NAME

    if not dry_run:
        video_dir.mkdir(parents=True, exist_ok=True)

    try:
        videos = sos.extract_videos(course_id)
    except Exception as e:
        logger.error(f"Failed to extract videos for {course_shortname}: {e}")
        return stats

    for video in videos:
        filename = _derive_video_filename(video)
        target_path = video_dir / filename

        if target_path.exists():
            logger.info(f"Skip (exists): {target_path.name}")
            stats["skipped"] += 1
            continue

        if dry_run:
            logger.info(f"[dry-run] Would download: {video.url} → {target_path}")
            stats["downloaded"] += 1
            continue

        success = _download_single_video(video, target_path)
        if success:
            stats["downloaded"] += 1
        else:
            stats["failed"] += 1

    return stats


def _download_single_video(video: MoodleVideo, target_path: Path) -> bool:
    """Download one Vimeo video to the target path using yt-dlp.

    Tries the video's own password first, then no password.

    Returns:
        True if download succeeded, False otherwise.
    """
    ytdlp_bin = shutil.which("yt-dlp") or "yt-dlp"

    # Output template uses final target path stem to avoid title-based renaming
    output_template = str(target_path.with_suffix(".%(ext)s"))

    def _build_command(password: str | None) -> list[str]:
        cmd = [
            ytdlp_bin,
            "--no-check-certificates",
            "-o", output_template,
            "-f", YTDLP_FORMAT,
            "--merge-output-format", YTDLP_MERGE_FORMAT,
        ]
        if password:
            cmd.extend(["--video-password", password])
        cmd.append(video.url)
        return cmd

    passwords_to_try: list[str | None] = [video.password]
    if video.password:
        # Also try without password (some videos are publicly accessible)
        passwords_to_try.append(None)

    logger.info(f"Downloading: {video.module_name} ({video.url})")

    for password in passwords_to_try:
        cmd = _build_command(password)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=DOWNLOAD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            logger.error(f"Download timed out after {DOWNLOAD_TIMEOUT_SECONDS}s: {video.url}")
            return False
        except FileNotFoundError:
            logger.error(
                "yt-dlp not found. Install with: brew install yt-dlp  OR  pip install yt-dlp"
            )
            return False

        if result.returncode == 0:
            logger.info(f"Downloaded successfully: {target_path.name}")
            return True

        if "Wrong password" in result.stderr and len(passwords_to_try) > 1:
            logger.info(f"Password attempt failed for {video.module_name}, trying next...")
            continue

        logger.error(f"yt-dlp failed for {video.url}:\n{result.stderr[-500:]}")
        return False

    return False


def check_ytdlp_available() -> bool:
    """Check whether yt-dlp is available on PATH."""
    return shutil.which("yt-dlp") is not None


def _derive_video_filename(video: MoodleVideo) -> str:
    """Derive a safe local filename for a video.

    Attempts to produce a short descriptive name from the module/section name.
    Falls back to a URL-based slug if the name is unusable.
    """
    import re

    name = (video.module_name or video.section_name or "video").strip()
    # Remove password hints from the name
    name = re.sub(
        r"\*?[Pp][Ww]\s*[:：]\s*\S+|\*?[Pp]assword\s*[:：]\s*\S+|パスワード\s*[:：]\s*\S+",
        "",
        name,
    ).strip()
    # Replace forbidden characters
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", "_", name)
    name = name.strip("_")[:80]

    if not name:
        # Last resort: derive from URL
        url_slug = re.sub(r"[^a-zA-Z0-9]", "_", video.url.split("/")[-1])
        name = f"video_{url_slug}"

    return f"{name}.mp4"


def _sanitize_dirname(name: str) -> str:
    """Sanitize a name for use as a directory name."""
    import re
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return cleaned.strip()[:100]
