"""CLI entry point for shizenkan-lite.

Commands:
  setup      - First-time setup: obtain Moodle token and generate config
  sync       - Sync course materials to ~/Shizenkan/
  deadlines  - Show upcoming deadlines and update _deadlines.md
  status     - Show config, last sync time, disk usage
  courses    - List enrolled courses with active/inactive classification
"""

import argparse
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool = False) -> None:
    """Configure root logger for CLI output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def _cmd_setup(args: argparse.Namespace) -> int:
    """Run first-time setup: acquire token and generate config.json."""
    from .config import AppConfig, CONFIG_DIR, CONFIG_PATH, TOKEN_PATH, DEFAULT_SITE_URL
    from .token_setup import run_token_setup

    print("=== shizenkan-lite setup ===\n")

    # --- Step 1: Moodle token ---
    site_url = DEFAULT_SITE_URL
    if CONFIG_PATH.exists():
        try:
            cfg = AppConfig.load()
            site_url = cfg.site_url
        except Exception:
            pass

    if TOKEN_PATH.exists() and not args.force:
        print(f"Token already exists at {TOKEN_PATH}")
        print("Use --force to re-acquire.\n")
    else:
        try:
            run_token_setup(site_url)
        except RuntimeError as e:
            print(f"\nError: {e}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\nSetup cancelled.", file=sys.stderr)
            return 1

    # --- Step 2: Config file ---
    if CONFIG_PATH.exists() and not args.force:
        print(f"Config already exists at {CONFIG_PATH}")
        print("Use --force to regenerate.\n")
    else:
        config = AppConfig()
        config.save()
        print(f"Config file created at: {CONFIG_PATH}")
        print("\nNext steps:")
        print("  1. Run: python -m shizenkan_lite courses")
        print("     (to see your enrolled courses and auto-detect active ones)")
        print("  2. Edit active_courses in config.json")
        print("  3. Run: python -m shizenkan_lite sync")

    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    """Sync course files from SOS to local ~/Shizenkan/."""
    from .config import AppConfig
    from .sos import SOSClient
    from .sync import sync_active_courses
    from .video import download_course_videos, check_ytdlp_available
    from .state import update_last_sync_timestamp

    config = AppConfig.load()

    if not config.active_courses:
        print("No active_courses configured. Run `python -m shizenkan_lite courses` first.")
        return 1

    dry_run = args.dry_run
    if dry_run:
        print("[DRY RUN] No files will be written.\n")

    with SOSClient() as sos:
        # File sync
        result = sync_active_courses(sos, config, dry_run=dry_run)

        print(f"\nFile sync complete:")
        print(f"  Downloaded: {result.total_downloaded}")
        print(f"  Skipped:    {result.total_skipped}")

        if result.all_errors:
            print(f"\nErrors ({len(result.all_errors)}):")
            for err in result.all_errors:
                print(f"  - {err}")

        # Video download
        if config.download_videos:
            if not check_ytdlp_available():
                print("\nWarning: yt-dlp not found. Skipping video downloads.")
                print("Install with: brew install yt-dlp")
            else:
                enrolled = sos.get_courses()
                course_map = {c.shortname: c for c in enrolled}

                print("\nVideo download:")
                for shortname in config.active_courses:
                    course = course_map.get(shortname)
                    if not course:
                        continue
                    video_stats = download_course_videos(
                        sos=sos,
                        config=config,
                        course_shortname=shortname,
                        course_id=course.id,
                        dry_run=dry_run,
                    )
                    print(f"  {shortname}: "
                          f"downloaded={video_stats['downloaded']}, "
                          f"skipped={video_stats['skipped']}, "
                          f"failed={video_stats['failed']}")

    if not dry_run:
        update_last_sync_timestamp()

    return 0 if not result.all_errors else 1


def _cmd_deadlines(args: argparse.Namespace) -> int:
    """Fetch upcoming deadlines and update _deadlines.md."""
    from .config import AppConfig
    from .sos import SOSClient
    from .deadlines import fetch_upcoming_deadlines, write_deadlines_markdown, print_deadlines_table

    config = AppConfig.load()
    dry_run = args.dry_run

    with SOSClient() as sos:
        deadlines = fetch_upcoming_deadlines(sos, config)

    print_deadlines_table(deadlines)

    output_path = write_deadlines_markdown(deadlines, config, dry_run=dry_run)
    if not dry_run:
        print(f"Updated: {output_path}")

    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Show configuration summary, last sync time, and disk usage."""
    from .config import AppConfig, CONFIG_PATH, TOKEN_PATH
    from .state import get_sync_stats, get_last_sync_timestamp

    print("=== shizenkan-lite status ===\n")

    # Config
    config_exists = CONFIG_PATH.exists()
    token_exists = TOKEN_PATH.exists()
    print(f"Config file : {'OK  ' if config_exists else 'MISSING'} ({CONFIG_PATH})")
    print(f"Token file  : {'OK  ' if token_exists else 'MISSING'} ({TOKEN_PATH})")

    if config_exists:
        try:
            config = AppConfig.load()
            print(f"\nSite URL    : {config.site_url}")
            print(f"Base path   : {config.base_path}")
            print(f"Active courses ({len(config.active_courses)}):")
            for shortname in config.active_courses:
                print(f"  - {shortname}")
            print(f"Download videos: {config.download_videos}")
        except Exception as e:
            print(f"  (Could not load config: {e})")
    else:
        print("\nRun `python -m shizenkan_lite setup` to configure.")

    # Sync stats
    stats = get_sync_stats()
    last_sync = stats.get("last_sync") or "Never"
    total_files = stats.get("total_files", 0)
    total_mb = stats.get("total_size_bytes", 0) / (1024 * 1024)
    print(f"\nLast sync   : {last_sync}")
    print(f"Tracked files: {total_files} ({total_mb:.1f} MB)")

    # Disk usage of base_path
    if config_exists:
        try:
            cfg = AppConfig.load()
            base = cfg.base_path.expanduser()
            if base.exists():
                import shutil as _shutil
                usage = _shutil.disk_usage(base)
                free_gb = usage.free / (1024 ** 3)
                print(f"Disk free   : {free_gb:.1f} GB (at {base})")
        except Exception:
            pass

    return 0


def _cmd_courses(args: argparse.Namespace) -> int:
    """List enrolled courses with active/inactive classification."""
    from .config import AppConfig
    from .sos import SOSClient
    from .deadlines import determine_active_courses

    config = AppConfig.load()

    print("Fetching enrolled courses from SOS...\n")

    with SOSClient() as sos:
        enrolled = sos.get_courses()

        if not enrolled:
            print("No enrolled courses found.")
            return 0

        print(f"{'Shortname':<30} {'Status':<10} Full name")
        print("-" * 80)

        if args.auto_detect:
            active_shortnames = determine_active_courses(sos, enrolled)
        else:
            active_shortnames = config.active_courses

        for course in enrolled:
            is_active = course.shortname in active_shortnames
            status = "ACTIVE" if is_active else "inactive"
            print(f"{course.shortname:<30} {status:<10} {course.fullname}")

    if args.auto_detect:
        print(f"\nAuto-detected active courses: {active_shortnames}")
        print("\nTo use these, add them to active_courses in:")
        print(f"  ~/.config/shizenkan-lite/config.json")

    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m shizenkan_lite",
        description="shizenkan-lite: Lightweight SOS (Moodle) sync tool for Shizenkan MBA students.",
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging.")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # setup
    setup_parser = subparsers.add_parser("setup", help="First-time setup (token + config).")
    setup_parser.add_argument("--force", action="store_true",
                               help="Re-run setup even if token/config already exist.")

    # sync
    sync_parser = subparsers.add_parser("sync", help="Sync course files from SOS.")
    sync_parser.add_argument("--dry-run", action="store_true",
                              help="Show what would be downloaded without writing files.")

    # deadlines
    deadlines_parser = subparsers.add_parser("deadlines",
                                              help="Show upcoming deadlines and update _deadlines.md.")
    deadlines_parser.add_argument("--dry-run", action="store_true",
                                   help="Print output without writing _deadlines.md.")

    # status
    subparsers.add_parser("status", help="Show configuration and sync status.")

    # courses
    courses_parser = subparsers.add_parser("courses",
                                            help="List enrolled courses with active status.")
    courses_parser.add_argument("--auto-detect", action="store_true",
                                 help="Auto-detect active courses based on deadlines/updates.")

    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_argument_parser()
    args = parser.parse_args()

    _configure_logging(verbose=getattr(args, "verbose", False))

    command_handlers = {
        "setup": _cmd_setup,
        "sync": _cmd_sync,
        "deadlines": _cmd_deadlines,
        "status": _cmd_status,
        "courses": _cmd_courses,
    }

    if not args.command:
        parser.print_help()
        return 0

    handler = command_handlers.get(args.command)
    if not handler:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1

    try:
        return handler(args)
    except FileNotFoundError as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
