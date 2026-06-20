"""Public library API."""

from __future__ import annotations

import json
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from . import constants
from .helpers import make_verify_fp
from .scraper import TikTokScraper


def get_init_options() -> dict[str, Any]:
    return {
        "number": 30,
        "since": 0,
        "download": False,
        "zip": False,
        "async_download": 5,
        "async_scraping": 3,
        "proxy": "",
        "filepath": "",
        "filetype": "",
        "progress": False,
        "event": False,
        "by_user_id": False,
        "no_watermark": False,
        "hd_video": False,
        "timeout": 0,
        "verify_fp": make_verify_fp(),
        "headers": {"user-agent": constants.user_agent(), "referer": "https://www.tiktok.com/"},
    }


def _normalize_options(options: dict[str, Any] | None) -> dict[str, Any]:
    if options is None:
        return {}
    if not isinstance(options, dict):
        raise TypeError("Object is expected")
    normalized = dict(options)
    aliases = {
        "proxyFile": "proxy_file",
        "sessionFile": "session_file",
        "asyncDownload": "async_download",
        "asyncBulk": "async_bulk",
        "byUserId": "by_user_id",
        "noWaterMark": "no_watermark",
        "storeHistory": "store_history",
        "historyPath": "history_path",
        "fileName": "file_name",
        "hdVideo": "hd_video",
        "webHookUrl": "web_hook_url",
        "verifyFp": "verify_fp",
        "sessionList": "session_list",
        "useTestEndpoints": "use_test_endpoints",
    }
    for old, new in aliases.items():
        if old in normalized and new not in normalized:
            normalized[new] = normalized.pop(old)
    if normalized.get("proxy_file"):
        normalized["proxy"] = _lines_from_file(normalized["proxy_file"], "Proxy file is empty")
    if normalized.get("session_file"):
        normalized["session_list"] = _lines_from_file(normalized["session_file"], "Session file is empty")
    return normalized


def _lines_from_file(path: str, empty_message: str) -> list[str]:
    lines = [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError(empty_message)
    return lines


def _build_scraper(input_value: str, scrape_type: str, options: dict[str, Any] | None = None, **extra: Any) -> TikTokScraper:
    constructor = {**get_init_options(), **_normalize_options(options), **extra, "type": scrape_type, "input": input_value}
    return TikTokScraper(**constructor)


def _promise_scraper(input_value: str, scrape_type: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return _build_scraper(input_value, scrape_type, options).scrape() or {}


def _event_scraper(input_value: str, scrape_type: str, options: dict[str, Any] | None = None) -> TikTokScraper:
    return _build_scraper(input_value, scrape_type, options, event=True)


def hashtag(input_value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return _promise_scraper(input_value, "hashtag", options)


def user(input_value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return _promise_scraper(input_value, "user", options)


def trend(input_value: str = "", options: dict[str, Any] | None = None) -> dict[str, Any]:
    return _promise_scraper(input_value, "trend", options)


def music(input_value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return _promise_scraper(input_value, "music", options)


def hashtag_event(input_value: str, options: dict[str, Any] | None = None) -> TikTokScraper:
    return _event_scraper(input_value, "hashtag", options)


def user_event(input_value: str, options: dict[str, Any] | None = None) -> TikTokScraper:
    return _event_scraper(input_value, "user", options)


def music_event(input_value: str, options: dict[str, Any] | None = None) -> TikTokScraper:
    return _event_scraper(input_value, "music", options)


def trend_event(input_value: str = "", options: dict[str, Any] | None = None) -> TikTokScraper:
    return _event_scraper(input_value, "trend", options)


def get_hashtag_info(input_value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return _build_scraper(input_value, "single_hashtag", options).get_hashtag_info()


def get_music_info(input_value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return _build_scraper(input_value, "single_music", options).get_music_info()


def get_user_profile_info(input_value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return _build_scraper(input_value, "single_user", options).get_user_profile_info()


def sign_url(input_value: str, options: dict[str, Any] | None = None) -> str:
    return _build_scraper(input_value, "signature", options).sign_url()


def get_video_meta(input_value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    scraper = _build_scraper(input_value, "video_meta", options)
    full_url = re.match(r"^https://www\.tiktok\.com/@[\w.-]+/video/\d+", input_value)
    result = scraper.get_video_meta(html=not bool(full_url))
    return {"headers": {**scraper.headers, "cookie": scraper.cookie_header()}, "collector": [result]}


def video(input_value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    opts = _normalize_options(options)
    scraper = _build_scraper(input_value, "video", opts)
    result = scraper.get_video_meta()
    path = f"{opts.get('filepath')}/{result['id']}" if opts.get("filepath") else result["id"]
    output: dict[str, Any] = {}

    if opts.get("download"):
        try:
            destination = scraper.downloader.download_single_video(result)
        except RuntimeError as exc:
            raise RuntimeError("Unable to download the video") from exc
        output["message"] = f"Video location: {destination}"

    if opts.get("filetype"):
        scraper.filetype = opts["filetype"]
        scraper.save_metadata(json_path=f"{path}.json", csv_path=f"{path}.csv")
        if opts["filetype"] == "all":
            output.update({"json": f"{path}.json", "csv": f"{path}.csv"})
        elif opts["filetype"] == "json":
            output["json"] = f"{path}.json"
        elif opts["filetype"] == "csv":
            output["csv"] = f"{path}.csv"
    return output


def history(input_value: str = "", options: dict[str, Any] | None = None) -> dict[str, Any]:
    opts = _normalize_options(options)
    history_path = "/usr/app/files" if os.getenv("SCRAPING_FROM_DOCKER") else opts.get("history_path") or tempfile.gettempdir()
    history_file = Path(history_path, "tiktok_history.json")
    if not history_file.exists():
        raise FileNotFoundError("History file doesn't exist")
    history_store = json.loads(history_file.read_text(encoding="utf-8"))

    remove = opts.get("remove")
    if remove:
        if ":" not in remove:
            remove = f"{remove}:"
        kind = remove.split(":", 1)[0]
        if kind == "all":
            for item in history_store.values():
                Path(item["file_location"]).unlink(missing_ok=True)
            history_file.unlink(missing_ok=True)
            return {"message": "History was completely removed"}

        key = remove.replace(":", "_") if kind != "trend" else "trend"
        if key in history_store:
            Path(history_store[key]["file_location"]).unlink(missing_ok=True)
            del history_store[key]
            history_file.write_text(json.dumps(history_store), encoding="utf-8")
            return {"message": f"Record {key} was removed"}
        raise KeyError(f"Can't find record: {key.replace('_', ' ')}")

    return {"table": list(history_store.values())}


def _batch_from_file(input_value: str) -> list[dict[str, Any]]:
    content = Path(input_value).read_text(encoding="utf-8")
    batch: list[dict[str, Any]] = []
    for raw in content.splitlines():
        item = re.sub(r"\s", "", raw)
        if not item or "##" in item:
            continue
        if "#" in item:
            batch.append({"type": "hashtag", "input": item.split("#", 1)[1]})
        elif re.match(r"^https://(www|v[a-z]{1}|[a-z])+\.(tiktok|tiktokv)\.com/@?\w.+/video/(\d+)(.+)?$", item):
            batch.append({"type": "video", "input": item})
        elif "music:" in item:
            batch.append({"type": "music", "input": item.split(":", 1)[1]})
        elif "id:" in item:
            batch.append({"type": "user", "input": item.split(":", 1)[1], "by_user_id": True})
        else:
            batch.append({"type": "user", "input": item.replace("@", "")})
    if not batch:
        raise ValueError(f"File is empty: {input_value}")
    return batch


def from_file(input_value: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    opts = _normalize_options(options)
    batch = _batch_from_file(input_value)
    results: list[dict[str, Any]] = []

    def run(item: dict[str, Any]) -> dict[str, Any]:
        try:
            task_options = {**opts, **({"by_user_id": True} if item.get("by_user_id") else {}), "bulk": True}
            if item["type"] == "video":
                video(item["input"], task_options)
                return {"type": item["type"], "input": item["input"], "completed": True}
            output = {"user": user, "hashtag": hashtag, "music": music}[item["type"]](item["input"], task_options)
            return {"type": item["type"], "input": item["input"], "completed": True, "scraped": len(output.get("collector", []))}
        except Exception:
            return {"type": item["type"], "input": item["input"], "completed": False}

    with ThreadPoolExecutor(max_workers=max(1, int(opts.get("async_bulk", 5)))) as executor:
        futures = [executor.submit(run, item) for item in batch]
        for future in as_completed(futures):
            results.append(future.result())
    return {"table": results}


fromfile = from_file

# CamelCase compatibility exports.
hashtagEvent = hashtag_event
userEvent = user_event
musicEvent = music_event
trendEvent = trend_event
getHashtagInfo = get_hashtag_info
getMusicInfo = get_music_info
getUserProfileInfo = get_user_profile_info
signUrl = sign_url
getVideoMeta = get_video_meta
