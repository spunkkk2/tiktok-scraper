"""Command-line interface for tiktok-scraper."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from typing import Any

from . import api, constants


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--session", default="", help="Set a session cookie value")
    parser.add_argument("--session-file", dest="session_file", default="", help="Path to a file with one session per line")
    parser.add_argument("--timeout", type=int, default=0, help="Timeout between requests in milliseconds")
    parser.add_argument("--number", "-n", type=int, default=0, help="Number of posts to scrape; 0 means all")
    parser.add_argument("--since", type=int, default=0, help="Scrape no posts published before this timestamp")
    parser.add_argument("--proxy", "-p", default="", help="Set a single proxy")
    parser.add_argument("--proxy-file", dest="proxy_file", default="", help="Path to a file with one proxy per line")
    parser.add_argument("--download", "-d", action="store_true", help="Download video posts")
    parser.add_argument("--asyncDownload", "-a", dest="async_download", type=int, default=5, help="Concurrent downloads")
    parser.add_argument("--hd", action="store_true", help="Download HD video when no-watermark extraction is enabled")
    parser.add_argument("--zip", "-z", action="store_true", help="ZIP all downloaded video posts")
    parser.add_argument(
        "--filepath",
        default="" if os.getenv("SCRAPING_FROM_DOCKER") else os.getcwd(),
        help="File path to save output files",
    )
    parser.add_argument("--filetype", "-t", choices=["csv", "json", "all", ""], default="", help="Metadata output type")
    parser.add_argument("--filename", "-f", default="", help="Custom output filename")
    parser.add_argument("--noWaterMark", "-w", dest="no_watermark", action="store_true", help="Download without watermark")
    parser.add_argument("--store", "-s", action="store_true", help="Save progress to avoid duplicate downloads")
    parser.add_argument(
        "--historypath",
        default="" if os.getenv("SCRAPING_FROM_DOCKER") else tempfile.gettempdir(),
        help="Custom history storage path",
    )
    parser.add_argument("--remove", "-r", default="", help='Delete history record, e.g. "user:bob" or "all"')
    parser.add_argument("--webHookUrl", dest="web_hook_url", default="", help="Webhook URL to receive scraper results")
    parser.add_argument("--method", choices=["GET", "POST"], default="POST", help="Webhook HTTP method")
    parser.add_argument("--useTestEndpoints", action="store_true", help="Use TikTok test endpoints")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tiktok-scraper", description="TikTok Scraper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    commands = {
        "user": "Scrape videos from the User Feed. Enter only the username",
        "hashtag": "Scrape videos from the Hashtag Feed. Enter hashtag without #",
        "trend": "Scrape posts from the Trend Feed",
        "music": "Scrape videos from the Music Feed. Enter the music id",
        "video": "Extract metadata from a single video. To download use -d",
        "history": "View previous download history",
        "from-file": "Scrape users, hashtags, music, and videos from a file",
        "userprofile": "Show user metadata",
    }
    for command, description in commands.items():
        sub = subparsers.add_parser(command, help=description)
        if command in {"user", "hashtag", "music", "video", "userprofile"}:
            sub.add_argument("id", nargs="?", default="")
        elif command == "from-file":
            sub.add_argument("file")
            sub.add_argument("async_tasks", nargs="?", type=int, default=5)
        _add_common_options(sub)
    return parser


def _options_from_args(args: argparse.Namespace) -> dict[str, Any]:
    options = vars(args).copy()
    command = options.pop("command")
    options.pop("id", None)
    options.pop("file", None)
    async_tasks = options.pop("async_tasks", None)
    if async_tasks:
        options["async_bulk"] = async_tasks
    options["type"] = command
    options["cli"] = True
    options["store_history"] = options.pop("store")
    options["history_path"] = options.pop("historypath")
    options["file_name"] = options.pop("filename")
    options["hd_video"] = options.pop("hd")
    if options.get("session"):
        options["session_list"] = [options.pop("session")]
    else:
        options.pop("session")
    return options


def _validate(args: argparse.Namespace) -> None:
    if args.command not in constants.SCRAPE_TYPES:
        raise ValueError("Wrong command")
    if args.store and not args.download:
        raise ValueError("--store, -s flag only works in combination with the download flag. Add -d to your command")
    if args.command == "from-file" and not args.async_tasks:
        raise ValueError("You need to set number of tasks that should be executed at the same time")
    if args.command == "from-file" and not args.filetype and not args.download:
        raise ValueError("You need to specify file type(-t) and/or if posts should be downloaded (-d)")
    if args.hd and not args.no_watermark and args.command != "video":
        raise ValueError("--hd option won't work without -w option")
    if os.getenv("SCRAPING_FROM_DOCKER") and (args.historypath or args.filepath):
        raise ValueError("Can't set custom path when running from Docker")
    if args.remove:
        remove = args.remove if ":" in args.remove else f"{args.remove}:"
        kind, item = remove.split(":", 1)
        if kind != "all" and kind not in constants.HISTORY_TYPES:
            raise ValueError(f"--remove, -r list of allowed types: {constants.HISTORY_TYPES}")
        if not item and kind not in {"trend", "all"}:
            raise ValueError('--remove, -r requires "TYPE:INPUT". For example: user:bob')


def run(args: argparse.Namespace) -> dict[str, Any]:
    _validate(args)
    options = _options_from_args(args)
    command = args.command
    input_value = getattr(args, "id", "") or getattr(args, "file", "")

    if command == "from-file":
        return api.from_file(input_value, options)
    if command == "history":
        return api.history("", options)
    if command == "userprofile":
        return api.get_user_profile_info(input_value, options)
    if command == "video":
        if not options.get("download") and not options.get("filetype"):
            options["filetype"] = "csv"
        return api.video(input_value, options)
    return {"user": api.user, "hashtag": api.hashtag, "trend": api.trend, "music": api.music}[command](input_value, options)


def print_result(result: dict[str, Any]) -> None:
    for key, label in (("zip", "ZIP path"), ("json", "JSON path"), ("csv", "CSV path")):
        if result.get(key):
            print(f"{label}: {result[key]}")
    if result.get("message"):
        print(result["message"])
    if result.get("webhook"):
        print(json.dumps(result["webhook"], indent=2))
    if result.get("table"):
        print(json.dumps(result["table"], indent=2))
    if not any(result.get(key) for key in ("zip", "json", "csv", "message", "webhook", "table")) and result:
        print(json.dumps(result, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        print_result(run(args))
    except Exception as exc:  # pragma: no cover - exercised by CLI users
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
