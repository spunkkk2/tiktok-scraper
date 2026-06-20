# TikTok Scraper & Downloader

Scrape and download useful information from TikTok with Python.

This is not an official TikTok API client. It uses TikTok web endpoints and page metadata, which may change or require request signing/proxying.

## Features

- Scrape metadata from user, hashtag, trend, and music feeds.
- Extract user, hashtag, music, and single-video metadata.
- Save metadata as JSON, CSV, or both.
- Download video files to a folder or ZIP archive.
- Maintain CLI download history to avoid repeated downloads.
- Process batch input files containing users, hashtags, music IDs, and video URLs.

## Installation

```sh
python -m pip install .
```

## CLI usage

```sh
tiktok-scraper --help
tiktok-scraper user USERNAME -n 100 -t json
tiktok-scraper hashtag HASHTAG_NAME -d -n 50
tiktok-scraper trend -n 30 -t all
tiktok-scraper music MUSIC_ID -n 50
tiktok-scraper video https://www.tiktok.com/@tiktok/video/6807491984882765062 -d
tiktok-scraper history
tiktok-scraper history -r user:bob
tiktok-scraper from-file batchDownloadExample 5 -d
```

Common options:

- `--session` / `--session-file`: provide TikTok session cookies.
- `--proxy` / `--proxy-file`: provide proxies.
- `--number`, `-n`: number of posts to scrape. `0` means continue until the feed ends.
- `--download`, `-d`: download videos.
- `--zip`, `-z`: ZIP downloaded videos.
- `--filetype`, `-t`: `json`, `csv`, `all`, or empty.
- `--filepath`: output directory.
- `--store`, `-s`: keep CLI history for duplicate avoidance.
- `--historypath`: history storage directory.

## Python module usage

```python
from tiktok_scraper import user, hashtag, get_video_meta

posts = user("tiktok", {"number": 10, "filetype": "json"})
print(posts["collector"][0]["webVideoUrl"])

tag = hashtag("python", {"number": 5})
video = get_video_meta("https://www.tiktok.com/@tiktok/video/6807491984882765062")
```

The package also exposes compatibility-style names for the old JavaScript API:

```python
from tiktok_scraper import getUserProfileInfo, getVideoMeta, signUrl
```

## Request signing note

The old TypeScript implementation executed TikTok's browser signing code through JSDOM. The Python port exposes a deterministic `sign()` compatibility helper, but TikTok rotates production signing behavior frequently. If TikTok requires a current signature for a target endpoint, inject or wrap the signing boundary with an up-to-date implementation.

## Development

Run tests with:

```sh
python -m unittest discover -s tests
```

Build a wheel with:

```sh
python -m build
```
