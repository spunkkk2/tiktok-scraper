"""Core TikTok scraper implementation."""

from __future__ import annotations

import csv
import json
import os
import random
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import Cookie, CookieJar
from pathlib import Path
from typing import Any, Callable

from . import constants
from .downloader import Downloader
from .helpers import deep_get, extract_json_script, flatten_mapping, makeid, sign

Callback = Callable[[Any], None]


class TikTokScraper:
    def __init__(
        self,
        *,
        download: bool = False,
        filepath: str = "",
        filetype: str = "",
        proxy: str | list[str] = "",
        strict_ssl: bool = True,
        async_download: int = 5,
        cli: bool = False,
        event: bool = False,
        progress: bool = False,
        input: str = "",
        number: int = 30,
        since: int = 0,
        type: str = "",
        by_user_id: bool = False,
        store_history: bool = False,
        history_path: str = "",
        no_watermark: bool = False,
        use_test_endpoints: bool = False,
        file_name: str = "",
        timeout: int = 0,
        bulk: bool = False,
        zip: bool = False,
        test: bool = False,
        hd_video: bool = False,
        web_hook_url: str = "",
        method: str = "POST",
        headers: dict[str, str] | None = None,
        verify_fp: str = "",
        session_list: list[str] | None = None,
        **_: Any,
    ) -> None:
        self.user_id_store = ""
        self.verify_fp = verify_fp
        self.main_host = "https://t.tiktok.com/" if use_test_endpoints else "https://m.tiktok.com/"
        self.headers = headers or {"user-agent": constants.user_agent(), "referer": "https://www.tiktok.com/"}
        self.download = download
        self.filepath = "/usr/app/files" if os.getenv("SCRAPING_FROM_DOCKER") else filepath or ""
        self.file_name = file_name
        self.filetype = filetype
        self.input = input
        self.test = test
        self.proxy = proxy
        self.strict_ssl = strict_ssl
        self.number = int(number or 0)
        self.since = int(since or 0)
        self.csrf = ""
        self.zip = zip
        self.cookie_jar = CookieJar()
        self.hd_video = hd_video
        self.session_list = session_list or []
        self.async_download = async_download or 5
        self.collector: list[dict[str, Any]] = []
        self.event = event
        self.scrape_type = type
        self.cli = cli
        self.by_user_id = by_user_id
        self.store_history = cli and download and store_history
        self.history_path = "/usr/app/files" if os.getenv("SCRAPING_FROM_DOCKER") else history_path or tempfile.gettempdir()
        self.id_store = ""
        self.no_watermark = no_watermark
        self.max_cursor = 0
        self.no_duplicates: list[str] = []
        self.timeout = timeout
        self.bulk = bulk
        self.valid_headers = False
        self.downloader = Downloader(
            progress=progress,
            cookie_jar=self.cookie_jar,
            proxy=proxy,
            no_watermark=no_watermark,
            headers=self.headers,
            filepath=self.filepath,
            bulk=bulk,
        )
        self.web_hook_url = web_hook_url
        self.method = method
        self.http_requests = {"good": 0, "bad": 0}
        self.store: list[str] = []
        self.store_value = ""
        self._callbacks: dict[str, list[Callback]] = {}

    # Compatibility aliases for callers migrating from the TypeScript API.
    @property
    def Downloader(self) -> Downloader:  # noqa: N802
        return self.downloader

    def on(self, event: str, callback: Callback) -> "TikTokScraper":
        self._callbacks.setdefault(event, []).append(callback)
        return self

    def emit(self, event: str, payload: Any) -> None:
        for callback in self._callbacks.get(event, []):
            callback(payload)

    @property
    def file_destination(self) -> str:
        if self.file_name:
            if not self.zip and self.download:
                return f"{self.folder_destination}/{self.file_name}"
            return f"{self.filepath}/{self.file_name}" if self.filepath else self.file_name

        suffix = int(time.time() * 1000)
        if self.scrape_type in {"user", "hashtag"}:
            base = f"{self.input}_{suffix}"
        else:
            base = f"{self.scrape_type}_{suffix}"

        if not self.zip and self.download:
            return f"{self.folder_destination}/{base}"
        return f"{self.filepath}/{base}" if self.filepath else base

    @property
    def folder_destination(self) -> str:
        if self.scrape_type == "user":
            name = self.input
        elif self.scrape_type == "hashtag":
            name = f"#{self.input}"
        elif self.scrape_type == "music":
            name = f"music_{self.input}"
        elif self.scrape_type == "trend":
            name = "trend"
        elif self.scrape_type == "video":
            name = "video"
        else:
            raise TypeError(f"{self.scrape_type} is not supported")
        return f"{self.filepath}/{name}" if self.filepath else name

    @property
    def api_endpoint(self) -> str:
        endpoints = {
            "user": "api/post/item_list/",
            "trend": "api/recommend/item_list/",
            "hashtag": "api/challenge/item_list/",
            "music": "api/music/item_list/",
        }
        if self.scrape_type not in endpoints:
            raise TypeError(f"{self.scrape_type} is not supported")
        return urllib.parse.urljoin(self.main_host, endpoints[self.scrape_type])

    def _proxy_url(self) -> str:
        if isinstance(self.proxy, list):
            return random.choice(self.proxy) if self.proxy else ""
        return self.proxy or ""

    def _opener(self) -> urllib.request.OpenerDirector:
        handlers: list[Any] = [urllib.request.HTTPCookieProcessor(self.cookie_jar)]
        proxy = self._proxy_url()
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        return urllib.request.build_opener(*handlers)

    def _set_cookie(self, name: str, value: str, domain: str = ".tiktok.com") -> None:
        cookie = Cookie(
            version=0,
            name=name,
            value=value,
            port=None,
            port_specified=False,
            domain=domain,
            domain_specified=True,
            domain_initial_dot=domain.startswith("."),
            path="/",
            path_specified=True,
            secure=True,
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={},
            rfc2109=False,
        )
        self.cookie_jar.set_cookie(cookie)

    def _prepare_cookies(self) -> None:
        for session in self.session_list:
            if "=" in session:
                name, value = session.split("=", 1)
                self._set_cookie(name.strip(), value.split(";", 1)[0].strip())

        if not any(cookie.name == "tt_webid_v2" for cookie in self.cookie_jar):
            self._set_cookie("tt_webid_v2", f"69{makeid(17)}")

    def request(
        self,
        *,
        uri: str,
        method: str = "GET",
        qs: dict[str, Any] | None = None,
        body: Any = None,
        headers: dict[str, str] | None = None,
        json_response: bool = False,
        follow_all_redirects: bool = False,
        simple: bool = True,
        body_only: bool = True,
    ) -> Any:
        self._prepare_cookies()
        query = urllib.parse.urlencode({k: v for k, v in (qs or {}).items() if v is not None})
        url = f"{uri}?{query}" if query else uri
        request_headers = {**self.headers, **(headers or {})}
        if self.csrf:
            request_headers["x-secsdk-csrf-token"] = self.csrf

        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode() if isinstance(body, (dict, list)) else str(body).encode()
            request_headers.setdefault("content-type", "application/json")

        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with self._opener().open(request, timeout=10) as response:
                raw = response.read()
                if method == "HEAD":
                    csrf = response.headers.get("x-ware-csrf-token", "")
                    if "," in csrf:
                        self.csrf = csrf.split(",", 1)[1]
                if self.timeout:
                    time.sleep(self.timeout / 1000)
                if not body_only:
                    return {"body": raw, "url": response.geturl(), "headers": dict(response.headers)}
                text = raw.decode("utf-8", errors="replace")
                return json.loads(text) if json_response else text
        except urllib.error.HTTPError as exc:
            if simple:
                raise RuntimeError(str(exc)) from exc
            return {"body": exc.read(), "url": exc.geturl(), "headers": dict(exc.headers), "status": exc.code}
        except urllib.error.URLError as exc:
            raise RuntimeError(str(exc)) from exc

    def _return_init_error(self, error: str) -> None:
        if self.event:
            self.emit("error", error)
            return None
        raise ValueError(error)

    def scrape(self) -> dict[str, Any] | None:
        if self.download and not self.zip:
            Path(self.folder_destination).mkdir(parents=True, exist_ok=True)

        if not self.scrape_type or self.scrape_type not in constants.SCRAPE_TYPES:
            return self._return_init_error(f"Missing scraping type. Scrape types: {constants.SCRAPE_TYPES} ")
        if self.scrape_type != "trend" and not self.input:
            return self._return_init_error("Missing input")

        self.main_loop()

        if self.event:
            self.emit("done", "completed")
            return None

        if self.store_history:
            self.get_downloaded_videos_from_history()
        if self.no_watermark:
            self.without_watermark()

        json_path, csv_path, zip_path = self.save_collector_data()

        if self.store_history:
            for item in self.collector:
                if item["id"] not in self.store and item.get("downloaded"):
                    self.store.append(item["id"])
            self.store_download_progress()

        if self.web_hook_url:
            self.send_data_to_webhook_url()

        result: dict[str, Any] = {
            "headers": {**self.headers, "cookie": self.cookie_header()},
            "collector": self.collector,
        }
        if self.download:
            result["zip"] = zip_path
        if self.filetype == "all":
            result.update({"json": json_path, "csv": csv_path})
        elif self.filetype == "json":
            result["json"] = json_path
        elif self.filetype == "csv":
            result["csv"] = csv_path
        if self.web_hook_url:
            result["webhook"] = self.http_requests
        return result

    def cookie_header(self) -> str:
        return "; ".join(f"{cookie.name}={cookie.value}" for cookie in self.cookie_jar)

    def main_loop(self) -> None:
        for item in range(1, 1001):
            if self.scrape_type == "user":
                query = self.get_user_id()
                done = self.submit_scraping_request({**query, "cursor": self.max_cursor}, True)
            elif self.scrape_type == "hashtag":
                query = self.get_hash_tag_id()
                done = self.submit_scraping_request({**query, "cursor": 0 if item == 1 else (item - 1) * query["count"]}, True)
            elif self.scrape_type == "trend":
                done = self.submit_scraping_request(self.get_trending_feed_query(), True)
            elif self.scrape_type == "music":
                query = self.get_music_feed_query()
                done = self.submit_scraping_request({**query, "cursor": 0 if item == 1 else (item - 1) * query["count"]}, True)
            else:
                done = True
            if done:
                break

    def submit_scraping_request(self, query: dict[str, Any], updated_api_response: bool = False) -> bool:
        if not self.valid_headers:
            if self.scrape_type == "trend":
                self.get_valid_headers("https://www.tiktok.com/foryou", sign_url=False, method="GET")
            self.valid_headers = True

        result = self.scrape_data(query)
        if result.get("statusCode") != 0:
            raise RuntimeError("Can't scrape more posts")
        posts = result.get("itemList") if updated_api_response else result.get("items")
        if not posts:
            raise RuntimeError("No more posts")

        done = self.collect_posts(posts)["done"]
        if not result.get("hasMore"):
            return True
        if done:
            return True

        self.max_cursor = int(result.get("maxCursor", result.get("cursor", 0)) or 0)
        return False

    def save_collector_data(self) -> tuple[str, str, str]:
        if self.download and self.collector and not self.test:
            self.downloader.download_posts(
                zip_output=self.zip,
                folder=self.folder_destination,
                collector=self.collector,
                file_name=self.file_destination,
                async_download=self.async_download,
            )

        if not self.collector:
            return "", "", ""

        json_path = f"{self.file_destination}.json"
        csv_path = f"{self.file_destination}.csv"
        zip_path = f"{self.file_destination}.zip" if self.zip else self.folder_destination
        self.save_metadata(json_path=json_path, csv_path=csv_path)
        return json_path, csv_path, zip_path

    def save_metadata(self, *, json_path: str, csv_path: str) -> None:
        if not self.collector:
            return
        if self.filetype in {"json", "all"}:
            Path(json_path).parent.mkdir(parents=True, exist_ok=True) if Path(json_path).parent != Path(".") else None
            Path(json_path).write_text(json.dumps(self.collector, ensure_ascii=False), encoding="utf-8")
        if self.filetype in {"csv", "all"}:
            rows = [flatten_mapping(item) for item in self.collector]
            fieldnames = sorted({key for row in rows for key in row})
            Path(csv_path).parent.mkdir(parents=True, exist_ok=True) if Path(csv_path).parent != Path(".") else None
            with Path(csv_path).open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

    def get_downloaded_videos_from_history(self) -> None:
        try:
            self.store = json.loads(Path(self.history_path, f"{self.store_value}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.store = []
        for item in self.collector:
            if item["id"] in self.store:
                item["repeated"] = True
        self.collector = [item for item in self.collector if not item.get("repeated")]

    def store_download_progress(self) -> None:
        history_type = "trend" if self.scrape_type == "trend" else f"{self.scrape_type}_{self.input}"
        total_new = len([item for item in self.collector if item.get("downloaded")])
        if not self.store_value or not total_new:
            return

        history_file = Path(self.history_path, "tiktok_history.json")
        try:
            history = json.loads(history_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            history = {}

        current = history.get(history_type, {"downloaded_posts": 0})
        history[history_type] = {
            "type": self.scrape_type,
            "input": self.input,
            "downloaded_posts": current.get("downloaded_posts", 0) + total_new,
            "last_change": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "file_location": str(Path(self.history_path, f"{self.store_value}.json")),
        }
        Path(self.history_path).mkdir(parents=True, exist_ok=True)
        Path(self.history_path, f"{self.store_value}.json").write_text(json.dumps(self.store), encoding="utf-8")
        history_file.write_text(json.dumps(history), encoding="utf-8")

    def collect_posts(self, posts: list[dict[str, Any]]) -> dict[str, bool]:
        result = {"done": False}
        for post in posts:
            if self.since and int(post.get("createTime", 0)) < self.since:
                result["done"] = self.scrape_type in constants.CHRONOLOGICAL_TYPES
                if result["done"]:
                    break
                continue

            post_id = str(post.get("id", ""))
            if post_id and post_id not in self.no_duplicates:
                self.no_duplicates.append(post_id)
                item = self._post_to_collector(post)
                if self.event:
                    self.emit("data", item)
                    self.collector.append({})
                else:
                    self.collector.append(item)

            if self.number and len(self.collector) >= self.number:
                result["done"] = True
                break
        return result

    def _post_to_collector(self, post: dict[str, Any], *, single_video: bool = False) -> dict[str, Any]:
        author = post.get("author", {})
        author_stats = post.get("authorStats", {})
        video = post.get("video", {})
        music = post.get("music") or {}
        stats = post.get("stats", {})
        desc = post.get("desc", "") or ""
        item: dict[str, Any] = {
            "id": str(post.get("id", "")),
            "secretID": video.get("id", ""),
            "text": desc,
            "createTime": post.get("createTime", 0),
            "authorMeta": {
                "id": author.get("id", ""),
                "secUid": author.get("secUid", ""),
                "name": author.get("uniqueId", ""),
                "nickName": author.get("nickname", ""),
                "verified": author.get("verified", False),
                "signature": author.get("signature", ""),
                "avatar": author.get("avatarLarger", ""),
                "following": author_stats.get("followingCount"),
                "fans": author_stats.get("followerCount"),
                "heart": author_stats.get("heartCount"),
                "video": author_stats.get("videoCount"),
                "digg": author_stats.get("diggCount"),
            },
            "covers": {
                "default": video.get("cover", ""),
                "origin": video.get("originCover", ""),
                "dynamic": video.get("dynamicCover", ""),
            },
            "videoUrl": video.get("playAddr" if single_video else "downloadAddr", ""),
            "videoUrlNoWaterMark": "",
            "videoApiUrlNoWaterMark": "",
            "videoMeta": {
                "height": video.get("height", 0),
                "width": video.get("width", 0),
                "duration": video.get("duration", 0),
            },
            "diggCount": stats.get("diggCount", 0),
            "shareCount": stats.get("shareCount", 0),
            "playCount": stats.get("playCount", 0),
            "commentCount": stats.get("commentCount", 0),
            "downloaded": False,
            "mentions": re.findall(r"@\w+", desc),
            "hashtags": [
                {
                    "id": challenge.get("id", ""),
                    "name": challenge.get("title", ""),
                    "title": challenge.get("desc", ""),
                    "cover": challenge.get("coverLarger") or challenge.get("profileLarger", ""),
                }
                for challenge in post.get("challenges") or []
            ],
            "effectStickers": [
                {"id": sticker.get("ID", ""), "name": sticker.get("name", "")}
                for sticker in post.get("effectStickers") or []
            ],
        }

        if music:
            item["musicMeta"] = {
                "musicId": music.get("id", ""),
                "musicName": music.get("title", ""),
                "musicAuthor": music.get("authorName", ""),
                "musicOriginal": music.get("original", False),
                "musicAlbum": music.get("album", ""),
                "playUrl": music.get("playUrl", ""),
                "coverThumb": music.get("coverThumb", ""),
                "coverMedium": music.get("coverMedium", ""),
                "coverLarge": music.get("coverLarge", ""),
                "duration": music.get("duration", 0),
            }

        if single_video:
            item["authorMeta"]["private"] = author.get("secret", False)
            item["imageUrl"] = video.get("cover", "")
            item["videoMeta"].update(
                {
                    "ratio": video.get("ratio", ""),
                    "duetEnabled": post.get("duetEnabled", False),
                    "stitchEnabled": post.get("stitchEnabled", False),
                    "duetInfo": post.get("duetInfo", {}),
                }
            )
        else:
            item["webVideoUrl"] = f"https://www.tiktok.com/@{author.get('uniqueId', '')}/video/{post.get('id', '')}"
        return item

    def without_watermark(self) -> None:
        for item in self.collector:
            item["videoApiUrlNoWaterMark"] = self.extract_video_id(item)
            item["videoUrlNoWaterMark"] = self.get_url_without_the_watermark(item["videoApiUrlNoWaterMark"])

    def extract_video_id(self, item: dict[str, Any]) -> str:
        if int(item.get("createTime", 0)) > 1595808000:
            return ""
        try:
            response = self.request(uri=item["videoUrl"], headers=self.headers)
            position = response.find("vid:")
            if position != -1:
                video_id = response[position + 4 : position + 36]
                hd = "&ratio=default&improve_bitrate=1" if self.hd_video else ""
                return (
                    "https://api2-16-h2.musical.ly/aweme/v1/play/"
                    f"?video_id={video_id}&vr_type=0&is_play_url=1"
                    f"&source=PackSourceEnum_PUBLISH&media_type=4{hd}"
                )
        except RuntimeError:
            pass
        return ""

    def get_url_without_the_watermark(self, uri: str) -> str:
        if not uri:
            return ""
        response = self.request(
            uri=uri,
            method="GET",
            headers={
                "user-agent": (
                    "com.zhiliaoapp.musically/2021600040 (Linux; U; Android 5.0; en_US; "
                    "SM-N900T; Build/LRX21V; Cronet/TTNetVersion:6c7b701a 2020-04-23 "
                    "QuicVersion:0144d358 2020-03-24)"
                ),
                "sec-fetch-mode": "navigate",
            },
            follow_all_redirects=True,
            simple=False,
            body_only=False,
        )
        return response.get("url", "")

    def get_valid_headers(self, url: str = "", sign_url: bool = True, method: str = "HEAD") -> None:
        qs = {"_signature": sign(url, self.headers.get("user-agent", ""))} if sign_url else None
        self.request(
            uri=url,
            method=method,
            qs=qs,
            headers={"x-secsdk-csrf-request": "1", "x-secsdk-csrf-version": "1.2.5"},
        )

    def scrape_data(self, qs: dict[str, Any]) -> dict[str, Any]:
        self.store_value = "trend" if self.scrape_type == "trend" else qs.get("id") or qs.get("challengeID") or qs.get("musicID") or ""
        unsigned = f"{self.api_endpoint}?{urllib.parse.urlencode(qs)}"
        query = {**qs, "_signature": sign(unsigned, self.headers.get("user-agent", ""))}
        return self.request(uri=self.api_endpoint, method="GET", qs=query, json_response=True)

    def get_trending_feed_query(self) -> dict[str, Any]:
        return {
            "aid": 1988,
            "app_name": "tiktok_web",
            "device_platform": "web_pc",
            "lang": "",
            "count": 30,
            "from_page": "fyp",
            "itemID": 1,
        }

    def get_music_feed_query(self) -> dict[str, Any]:
        match = re.search(r"\.com/music/[\w+-]+-(\d{15,22})", self.input)
        if match:
            self.input = match.group(1)
        return {"musicID": self.input, "lang": "", "aid": 1988, "count": 30, "cursor": 0, "verifyFp": ""}

    def get_hash_tag_id(self) -> dict[str, Any]:
        if self.id_store:
            return {"challengeID": self.id_store, "count": 30, "cursor": 0, "aid": 1988, "verifyFp": self.verify_fp}
        encoded = urllib.parse.quote(self.input)
        response = self.request(
            uri=f"{self.main_host}node/share/tag/{encoded}",
            qs={"uniqueId": encoded, "user_agent": self.headers.get("user-agent", "")},
            method="GET",
            json_response=True,
        )
        if response.get("statusCode") != 0:
            raise RuntimeError(f"Can not find the hashtag: {self.input}")
        self.id_store = deep_get(response, "challengeInfo.challenge.id", "")
        return {"challengeID": self.id_store, "count": 30, "cursor": 0, "aid": 1988, "verifyFp": self.verify_fp}

    def get_user_id(self) -> dict[str, Any]:
        if self.by_user_id or self.id_store:
            return {
                "id": self.user_id_store,
                "secUid": self.id_store or self.input,
                "lang": "",
                "aid": 1988,
                "count": 30,
                "cursor": 0,
                "app_name": "tiktok_web",
                "device_platform": "web_pc",
                "cookie_enabled": True,
                "history_len": 2,
                "focus_state": True,
                "is_fullscreen": False,
            }
        response = self.get_user_profile_info()
        self.id_store = deep_get(response, "user.secUid", "")
        self.user_id_store = deep_get(response, "user.id", "")
        return self.get_user_id()

    def get_user_profile_info(self) -> dict[str, Any]:
        if not self.input:
            raise ValueError("Username is missing")
        try:
            html = self.request(uri=f"https://www.tiktok.com/@{urllib.parse.quote(self.input)}", method="GET")
            data = extract_json_script(html, "__NEXT_DATA__")
            user_info = deep_get(data, "props.pageProps.userInfo")
            if user_info:
                return user_info
        except RuntimeError as exc:
            if "404" in str(exc):
                raise RuntimeError("User does not exist") from exc
        raise RuntimeError("Can't extract user metadata from the html page. Make sure that user does exist and try to use proxy")

    def get_hashtag_info(self) -> dict[str, Any]:
        if not self.input:
            raise ValueError("Hashtag is missing")
        response = self.request(
            uri=f"{self.main_host}node/share/tag/{self.input}",
            qs={"uniqueId": self.input, "appId": 1233},
            method="GET",
            json_response=True,
        )
        if not response or response.get("statusCode") != 0:
            raise RuntimeError(f"Can't find hashtag: {self.input}")
        return response.get("challengeInfo", {})

    def get_music_info(self) -> dict[str, Any]:
        if not self.input:
            raise ValueError("Music is missing")
        title = re.search(r"music/([\w-]+)-\d+", self.input)
        music_id = re.search(r"music/[\w-]+-(\d+)", self.input)
        query = {
            "screen_width": 1792,
            "screen_height": 1120,
            "lang": "en",
            "priority_region": "",
            "referer": "",
            "root_referer": "",
            "app_language": "en",
            "is_page_visible": True,
            "history_len": 6,
            "focus_state": True,
            "is_fullscreen": False,
            "aid": 1988,
            "app_name": "tiktok_web",
            "timezone_name": "",
            "device_platform": "web",
            "musicId": music_id.group(1) if music_id else "",
            "musicName": title.group(1) if title else "",
        }
        uri = f"https://www.tiktok.com/node/share/music/{query['musicName']}-{query['musicId']}"
        unsigned = f"{uri}?{urllib.parse.urlencode(query)}"
        query["_signature"] = sign(unsigned, self.headers.get("user-agent", ""))
        response = self.request(uri=uri, qs=query, method="GET", json_response=True)
        if response.get("statusCode") != 0:
            raise RuntimeError(f"Can't find music data: {self.input}")
        return response.get("musicInfo", {})

    def sign_url(self) -> str:
        if not self.input:
            raise ValueError("Url is missing")
        return sign(self.input, self.headers.get("user-agent", ""))

    def get_video_metadata_from_html(self) -> dict[str, Any]:
        html = self.request(uri=self.input, method="GET")
        next_data = extract_json_script(html, "__NEXT_DATA__")
        item = deep_get(next_data, "props.pageProps.itemInfo.itemStruct")
        if item:
            return item
        sigi_state = extract_json_script(html, "SIGI_STATE")
        item_module = sigi_state.get("ItemModule", {}) if isinstance(sigi_state, dict) else {}
        if item_module:
            return next(iter(item_module.values()))
        raise RuntimeError("No available parser for html page")

    def get_video_metadata(self, url: str = "") -> dict[str, Any]:
        video_data = re.search(r"tiktok\.com/(@[\w.-]+)/video/(\d+)", url or self.input)
        if video_data:
            response = self.request(
                uri=f"https://www.tiktok.com/node/share/video/{video_data.group(1)}/{video_data.group(2)}",
                method="GET",
                json_response=True,
            )
            if response.get("statusCode") == 0:
                return deep_get(response, "itemInfo.itemStruct", {})
        raise RuntimeError(f"Can't extract video metadata: {self.input}")

    def get_video_meta(self, html: bool = True) -> dict[str, Any]:
        if not self.input:
            raise ValueError("Url is missing")
        try:
            video_data = self.get_video_metadata_from_html() if html else self.get_video_metadata()
        except RuntimeError as exc:
            raise RuntimeError(f"Can't extract video metadata: {self.input}") from exc
        video_item = self._post_to_collector(video_data, single_video=True)
        if self.no_watermark:
            video_item["videoApiUrlNoWaterMark"] = self.extract_video_id(video_item)
            video_item["videoUrlNoWaterMark"] = self.get_url_without_the_watermark(video_item["videoApiUrlNoWaterMark"])
        self.collector.append(video_item)
        return video_item

    def send_data_to_webhook_url(self) -> None:
        for item in self.collector:
            try:
                if self.method == "POST":
                    self.request(uri=self.web_hook_url, method="POST", body=item, headers={"user-agent": "TikTok-Scraper"})
                else:
                    self.request(
                        uri=self.web_hook_url,
                        method="GET",
                        qs={"json": urllib.parse.quote(json.dumps(item))},
                        headers={"user-agent": "TikTok-Scraper"},
                    )
                self.http_requests["good"] += 1
            except RuntimeError:
                self.http_requests["bad"] += 1

    # CamelCase compatibility methods.
    getUserProfileInfo = get_user_profile_info
    getHashtagInfo = get_hashtag_info
    getMusicInfo = get_music_info
    signUrl = sign_url
    getVideoMeta = get_video_meta
    saveMetadata = save_metadata
    getHashTagId = get_hash_tag_id
    getUserId = get_user_id
