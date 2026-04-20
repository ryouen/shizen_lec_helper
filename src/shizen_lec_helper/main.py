"""CLI entry point for shizen_lec_helper.

Commands:
  setup      - First-time setup: obtain Moodle token and generate config
  sync       - Sync course materials to ~/Shizenkan/
  deadlines  - Show upcoming deadlines and update _deadlines.md
  status     - Show config, last sync time, disk usage
  courses    - List enrolled courses with active/inactive classification

Global flags (available before any subcommand):
  --config-dir PATH   Override default ~/.config/shizen_lec_helper/ (also SLH_CONFIG_DIR env)
  --base-path PATH    Override default ~/Shizenkan/ (also SLH_BASE_PATH env)
"""

import argparse
import logging
import os
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
    from .config import AppConfig, make_config_paths, DEFAULT_SITE_URL
    from .token_setup import run_token_setup, run_token_setup_from_file

    config_dir: Path | None = args.config_dir
    base_path: Path | None = args.base_path
    creds_file: str | None = getattr(args, "creds_file", None)
    username: str | None = getattr(args, "username", None)

    # Validate mutual dependency: --username and --creds-file must appear together.
    if bool(creds_file) != bool(username):
        print(
            "Error: --username and --creds-file must be specified together.",
            file=sys.stderr,
        )
        return 1

    _cfg_dir, cfg_path, token_path, _state = make_config_paths(config_dir)

    print("=== shizen_lec_helper setup ===\n")

    # --- Step 1: Moodle token ---
    site_url = DEFAULT_SITE_URL
    if cfg_path.exists():
        try:
            cfg = AppConfig.load(config_dir=config_dir)
            site_url = cfg.site_url
        except Exception:
            pass

    if token_path.exists() and not args.force:
        print(f"Token already exists at {token_path}")
        print("Use --force to re-acquire.\n")
    else:
        try:
            if creds_file and username:
                run_token_setup_from_file(
                    site_url, username, creds_file, config_dir=config_dir
                )
            else:
                run_token_setup(site_url, config_dir=config_dir)
        except EOFError as e:
            print(f"\n{e}", file=sys.stderr)
            return 1
        except RuntimeError as e:
            print(f"\nError: {e}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\nSetup cancelled.", file=sys.stderr)
            return 1

    # --- Step 2: Config file ---
    if cfg_path.exists() and not args.force:
        print(f"Config already exists at {cfg_path}")
        print("Use --force to regenerate.\n")
    else:
        config = AppConfig(base_path=base_path or AppConfig().base_path)
        config.save(config_dir=config_dir)
        print(f"Config file created at: {cfg_path}")
        print("\nNext steps:")
        print("  1. Run: python -m shizen_lec_helper courses")
        print("     (to see your enrolled courses and auto-detect active ones)")
        print("  2. Edit active_courses in config.json")
        print("  3. Run: python -m shizen_lec_helper sync")

    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    """Sync course files from SOS to local ~/Shizenkan/."""
    from .config import AppConfig
    from .sos import SOSClient
    from .sync import sync_active_courses
    from .video import download_course_videos, check_ytdlp_available
    from .state import update_last_sync_timestamp

    config_dir: Path | None = args.config_dir
    base_path: Path | None = args.base_path

    config = AppConfig.load(config_dir=config_dir, base_path_override=base_path)

    if not config.active_courses:
        print("No active_courses configured. Run `python -m shizen_lec_helper courses` first.")
        return 1

    dry_run = args.dry_run
    if dry_run:
        print("[DRY RUN] No files will be written.\n")

    with SOSClient(config_dir=config_dir) as sos:
        # File sync
        result = sync_active_courses(sos, config, dry_run=dry_run, config_dir=config_dir)

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
        update_last_sync_timestamp(config_dir=config_dir)

    return 0 if not result.all_errors else 1


def _cmd_deadlines(args: argparse.Namespace) -> int:
    """Fetch upcoming deadlines and update _deadlines.md."""
    from .config import AppConfig
    from .sos import SOSClient
    from .deadlines import fetch_upcoming_deadlines, write_deadlines_markdown, print_deadlines_table

    config_dir: Path | None = args.config_dir
    base_path: Path | None = args.base_path

    config = AppConfig.load(config_dir=config_dir, base_path_override=base_path)
    dry_run = args.dry_run

    with SOSClient(config_dir=config_dir) as sos:
        deadlines = fetch_upcoming_deadlines(sos, config)

    print_deadlines_table(deadlines)

    output_path = write_deadlines_markdown(deadlines, config, dry_run=dry_run)
    if not dry_run:
        print(f"Updated: {output_path}")

    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    """Show configuration summary, last sync time, and disk usage."""
    from .config import AppConfig, make_config_paths
    from .state import get_sync_stats

    config_dir: Path | None = args.config_dir
    base_path: Path | None = args.base_path

    _cfg_dir, cfg_path, token_path, _state = make_config_paths(config_dir)

    print("=== shizen_lec_helper status ===\n")

    # Config
    config_exists = cfg_path.exists()
    token_exists = token_path.exists()
    print(f"Config file : {'OK  ' if config_exists else 'MISSING'} ({cfg_path})")
    print(f"Token file  : {'OK  ' if token_exists else 'MISSING'} ({token_path})")

    if config_exists:
        try:
            config = AppConfig.load(config_dir=config_dir, base_path_override=base_path)
            print(f"\nSite URL    : {config.site_url}")
            print(f"Base path   : {config.base_path}")
            print(f"Active courses ({len(config.active_courses)}):")
            for shortname in config.active_courses:
                print(f"  - {shortname}")
            print(f"Download videos: {config.download_videos}")
        except Exception as e:
            print(f"  (Could not load config: {e})")
    else:
        print("\nRun `python -m shizen_lec_helper setup` to configure.")

    # Sync stats
    stats = get_sync_stats(config_dir=config_dir)
    last_sync = stats.get("last_sync") or "Never"
    total_files = stats.get("total_files", 0)
    total_mb = stats.get("total_size_bytes", 0) / (1024 * 1024)
    print(f"\nLast sync   : {last_sync}")
    print(f"Tracked files: {total_files} ({total_mb:.1f} MB)")

    # Disk usage of base_path
    if config_exists:
        try:
            cfg = AppConfig.load(config_dir=config_dir, base_path_override=base_path)
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
    from .config import AppConfig, make_config_paths
    from .sos import SOSClient
    from .deadlines import determine_active_courses

    config_dir: Path | None = args.config_dir
    base_path: Path | None = args.base_path

    config = AppConfig.load(config_dir=config_dir, base_path_override=base_path)

    print("Fetching enrolled courses from SOS...\n")

    with SOSClient(config_dir=config_dir) as sos:
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
        _cfg_dir, cfg_path, _tok, _state = make_config_paths(config_dir)
        print(f"\nAuto-detected active courses: {active_shortnames}")
        print("\nTo use these, add them to active_courses in:")
        print(f"  {cfg_path}")

    return 0


def _cmd_prep_password(args: argparse.Namespace) -> int:
    """Create a password file template for the user to fill in.

    Writes a file with comment lines explaining what to do, then a blank
    line at the bottom for the password. Optionally opens the file in the
    user's default editor so they can type into it via Finder/Explorer.
    """
    import subprocess
    import platform
    from .token_setup import create_password_file_template, DEFAULT_PASSWORD_FILE_PATH

    target = args.path or DEFAULT_PASSWORD_FILE_PATH
    path = create_password_file_template(target)

    print(f"\nPassword file created at:\n  {path}\n")
    print("Next steps for the user:")
    print("  1. Open this file (it should open automatically).")
    print("  2. On the last line, type your Moodle password and save.")
    print("  3. Tell the AI / run the setup command when ready.")
    print()

    if args.open:
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.run(["open", "-e", str(path)], check=False)
            elif system == "Windows":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except Exception as open_err:
            logger.warning("Could not auto-open editor: %s", open_err)
            print(f"(Please open this file manually: {path})")

    return 0


def _build_isolation_flags_parser() -> argparse.ArgumentParser:
    """Build a shared parent parser containing the isolation flags.

    Using add_help=False so it can be used as a parent without duplicate -h.
    """
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Override config directory (default: ~/.config/shizen_lec_helper/). "
            "Env var: SLH_CONFIG_DIR."
        ),
    )
    shared.add_argument(
        "--base-path",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Override base path for downloaded materials (default: ~/Shizenkan/). "
            "Env var: SLH_BASE_PATH."
        ),
    )
    return shared


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with global isolation flags.

    --config-dir and --base-path are available on the top-level parser AND
    on every subcommand parser (via parents=[isolation_flags]) so that
    `./run.sh status --help` shows them explicitly.
    """
    isolation_flags = _build_isolation_flags_parser()

    parser = argparse.ArgumentParser(
        prog="python -m shizen_lec_helper",
        description="shizen_lec_helper: Lightweight SOS (Moodle) sync tool for Shizenkan MBA students.",
        parents=[isolation_flags],
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging.")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # setup
    setup_parser = subparsers.add_parser(
        "setup",
        help="First-time setup (token + config).",
        parents=[isolation_flags],
    )
    setup_parser.add_argument("--force", action="store_true",
                               help="Re-run setup even if token/config already exist.")
    setup_parser.add_argument(
        "--username",
        metavar="EMAIL",
        default=None,
        help=(
            "SOS (Moodle) username/email. Required when --creds-file is used. "
            "Must be specified together with --creds-file."
        ),
    )
    setup_parser.add_argument(
        "--creds-file",
        metavar="PATH",
        default=None,
        help=(
            "Path to a file containing just the Moodle password (one line). "
            "Skips interactive prompts. The file must be owned by you and have "
            "permissions 600 or tighter. Deleted on success; kept on failure so "
            "you can fix the password and retry. Must be specified together with "
            "--username. "
            "Example: python -m shizen_lec_helper setup "
            "--username you@example.com --creds-file ~/.shizen_lec_password"
        ),
    )

    # sync
    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync course files from SOS.",
        parents=[isolation_flags],
    )
    sync_parser.add_argument("--dry-run", action="store_true",
                              help="Show what would be downloaded without writing files.")

    # deadlines
    deadlines_parser = subparsers.add_parser(
        "deadlines",
        help="Show upcoming deadlines and update _deadlines.md.",
        parents=[isolation_flags],
    )
    deadlines_parser.add_argument("--dry-run", action="store_true",
                                   help="Print output without writing _deadlines.md.")

    # status
    subparsers.add_parser(
        "status",
        help="Show configuration and sync status.",
        parents=[isolation_flags],
    )

    # courses
    courses_parser = subparsers.add_parser(
        "courses",
        help="List enrolled courses with active status.",
        parents=[isolation_flags],
    )
    courses_parser.add_argument("--auto-detect", action="store_true",
                                 help="Auto-detect active courses based on deadlines/updates.")

    # prep-password
    prep_parser = subparsers.add_parser(
        "prep-password",
        help="Create a password file template in Downloads for the user to fill in.",
    )
    prep_parser.add_argument("--path", metavar="PATH", default=None,
                              help="Where to create the file (default: ~/Downloads/moodle_password.txt).")
    prep_parser.add_argument("--open", action="store_true", default=True,
                              help="Open the file in the default editor after creating (default: True).")
    prep_parser.add_argument("--no-open", dest="open", action="store_false",
                              help="Do not open the file after creating.")

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
        "prep-password": _cmd_prep_password,
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
