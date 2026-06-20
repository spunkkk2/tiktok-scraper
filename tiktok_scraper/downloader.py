"""Video download support."""

from __future__ import annotations

import random
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any


class Downloader:
    def __init__(
        self,
        *,
        progress: bool = False,
        proxy: str | list[str] = "",
        no_watermark: bool = False,
        headers: dict[str, str] | None = None,
        filepath: str = "",
        bulk: bool = False,
        cookie_jar: CookieJar | None = None,
    ) -> None:
        self.progress = progress
        self.proxy = proxy
        self.no_watermark = no_watermark
        self.headers = headers or {}
        self.filepath = filepath
        self.bulk = bulk
        self.cookie_jar = cookie_jar or CookieJar()

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

    def to_buffer(self, item: dict[str, Any]) -> bytes:
        url = item.get("videoUrlNoWaterMark") or item.get("videoUrl")
        if not url:
            raise ValueError(f"Cant download video: {item.get('id', '')}")

        request = urllib.request.Request(url, headers=self.headers)
        try:
            with self._opener().open(request, timeout=30) as response:
                return response.read()
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Cant download video: {item.get('id', '')}. If you were using proxy, please try without it."
            ) from exc

    def download_posts(
        self,
        *,
        zip_output: bool,
        folder: str,
        collector: list[dict[str, Any]],
        file_name: str,
        async_download: int = 5,
    ) -> str:
        destination = Path(f"{file_name}.zip") if zip_output else Path(folder)
        if not zip_output:
            destination.mkdir(parents=True, exist_ok=True)

        def fetch(item: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
            try:
                return item, self.to_buffer(item)
            except RuntimeError:
                return item, b""

        with ThreadPoolExecutor(max_workers=max(1, async_download)) as executor:
            downloads = list(executor.map(fetch, collector))

        if zip_output:
            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for item, content in downloads:
                    item["downloaded"] = bool(content)
                    if content:
                        archive.writestr(f"{item['id']}.mp4", content)
        else:
            for item, content in downloads:
                item["downloaded"] = bool(content)
                if content:
                    (destination / f"{item['id']}.mp4").write_bytes(content)

        return str(destination)

    def download_single_video(self, post: dict[str, Any]) -> str:
        output_dir = Path(self.filepath or ".")
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / f"{post['id']}.mp4"
        destination.write_bytes(self.to_buffer(post))
        return str(destination)
