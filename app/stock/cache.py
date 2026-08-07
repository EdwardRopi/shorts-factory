"""Кэш поисковой выдачи на 24 часа.

Для Pixabay это прямое требование условий использования, для Pexels —
экономия лимита в 200 запросов в час. Кэш файловый: базы данных на этом
шаге ещё нет, а переписать на Postgres потом будет несложно.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from app import config

TTL_SECONDS = 24 * 60 * 60
CACHE_DIR = config.ROOT / "cache" / "search"


def _path(provider: str, query: str, extra: str = "") -> Path:
    digest = hashlib.sha256(f"{provider}|{query}|{extra}".encode()).hexdigest()[:20]
    return CACHE_DIR / f"{provider}-{digest}.json"


def get(provider: str, query: str, extra: str = "") -> dict | None:
    path = _path(provider, query, extra)
    if not path.exists() or time.time() - path.stat().st_mtime > TTL_SECONDS:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def put(provider: str, query: str, payload: dict, extra: str = "") -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _path(provider, query, extra).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
