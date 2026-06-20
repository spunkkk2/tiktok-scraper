"""Constants and small factories used by the scraper."""

from __future__ import annotations

import random

SCRAPE_TYPES = [
    "user",
    "hashtag",
    "trend",
    "music",
    "discover_user",
    "discover_hashtag",
    "discover_music",
    "history",
    "video",
    "from-file",
    "userprofile",
]

CHRONOLOGICAL_TYPES = ["user"]
HISTORY_TYPES = ["user", "hashtag", "trend", "music"]
REQUIRED_SESSION_TYPES = ["user", "hashtag", "trend", "music"]
SOURCE_TYPE = {"user": 8, "music": 11, "trend": 12}

_OPERATING_SYSTEMS = [
    "Macintosh; Intel Mac OS X 10_15_7",
    "Macintosh; Intel Mac OS X 10_15_5",
    "Macintosh; Intel Mac OS X 10_11_6",
    "Macintosh; Intel Mac OS X 10_6_6",
    "Macintosh; Intel Mac OS X 10_9_5",
    "Macintosh; Intel Mac OS X 10_10_5",
    "Macintosh; Intel Mac OS X 10_7_5",
    "Macintosh; Intel Mac OS X 10_11_3",
    "Macintosh; Intel Mac OS X 10_10_3",
    "Macintosh; Intel Mac OS X 10_6_8",
    "Macintosh; Intel Mac OS X 10_10_2",
    "Macintosh; Intel Mac OS X 10_11_5",
    "Windows NT 10.0; Win64; x64",
    "Windows NT 10.0; WOW64",
    "Windows NT 10.0",
]


def user_agent() -> str:
    """Generate a browser user-agent with randomized Chrome build numbers."""

    chrome_major = random.randint(87, 89)
    chrome_build = random.randint(4100, 4289)
    chrome_patch = random.randint(140, 189)
    return (
        f"Mozilla/5.0 ({random.choice(_OPERATING_SYSTEMS)}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_major}.0.{chrome_build}.{chrome_patch} Safari/537.36"
    )
