"""Helper utilities for the Python TikTok scraper."""

from __future__ import annotations

import base64
import hashlib
import json
import random
import re
import string
import time
from typing import Any, Mapping


def makeid(length: int) -> str:
    return "".join(random.choice(string.digits) for _ in range(length))


def makeid_hex(length: int) -> str:
    return "".join(random.choice("0123456789abcdef") for _ in range(length))


def make_verify_fp() -> str:
    chars = string.digits + string.ascii_uppercase + string.ascii_lowercase
    encoded_time = base64.b64encode(str(int(time.time() * 1000)).encode()).decode().lower()
    parts = list("0" * 36)
    for index in (8, 13, 18, 23):
        parts[index] = "_"
    parts[14] = "4"
    token = "".join(random.choice(chars) if value == "0" else value for value in parts)
    return f"verify_{encoded_time}_{token}"


def sign(url: str, user_agent: str = "") -> str:
    """Return a stable signature-like value for compatibility with the old API.

    The original Node implementation executed TikTok's browser JavaScript inside
    JSDOM. A pure-Python runtime cannot execute that opaque browser bundle, so
    the port exposes a deterministic signature helper instead of shelling out to
    Node. TikTok frequently rotates this mechanism; callers that need current
    production-grade request signing can replace this function at the boundary.
    """

    digest = hashlib.sha256(f"{url}|{user_agent}".encode()).hexdigest()
    return f"_02B4Z6wo00f01{digest[:80]}"


def extract_json_script(html: str, script_id: str) -> dict[str, Any] | None:
    pattern = re.compile(
        rf'<script[^>]+id=["\']{re.escape(script_id)}["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(html)
    if not match:
        return None
    return json.loads(match.group(1))


def deep_get(data: Mapping[str, Any] | None, path: str, default: Any = None) -> Any:
    current: Any = data
    for key in path.split("."):
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def flatten_mapping(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping):
            result.update(flatten_mapping(value, name))
        elif isinstance(value, list):
            result[name] = json.dumps(value, ensure_ascii=False)
        else:
            result[name] = value
    return result
