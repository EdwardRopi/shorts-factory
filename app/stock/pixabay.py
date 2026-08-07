"""Клиент Pixabay Videos API.

Лимит: 100 запросов за 60 секунд. Кэширование выдачи на 24 часа —
требование условий использования, а не рекомендация.
"""

from __future__ import annotations

import httpx

from app import config
from app.stock import cache
from app.stock.base import TARGET_W, Clip, StockProvider, rank

URL = "https://pixabay.com/api/videos/"


class PixabayError(RuntimeError):
    pass


class PixabayProvider(StockProvider):
    name = "pixabay"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or config.PIXABAY_API_KEY
        if not self.api_key:
            raise PixabayError("PIXABAY_API_KEY не задан в .env")

    def search(self, query: str, need_seconds: float, limit: int = 15) -> list[Clip]:
        extra = f"limit={limit}"
        data = cache.get(self.name, query, extra)
        if data is None:
            data = self._fetch(query, limit)
            cache.put(self.name, query, data, extra)

        clips = [c for hit in data.get("hits", []) if (c := self._to_clip(hit))]
        return rank(clips, need_seconds)

    def _fetch(self, query: str, limit: int) -> dict:
        params = {
            "key": self.api_key,
            "q": query,
            "per_page": max(3, min(limit, 200)),
            "video_type": "film",
            "safesearch": "true",
        }
        try:
            r = httpx.get(URL, params=params, timeout=30)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise PixabayError("Pixabay: превышен лимит (100 запросов в минуту)") from e
            raise PixabayError(f"Pixabay: HTTP {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise PixabayError(f"Pixabay недоступен: {e}") from e
        return r.json()

    @staticmethod
    def _to_clip(hit: dict) -> Clip | None:
        best = _best_variant(hit.get("videos", {}))
        if not best:
            return None
        return Clip(
            provider="pixabay",
            id=str(hit.get("id")),
            width=best.get("width", 0),
            height=best.get("height", 0),
            duration=float(hit.get("duration", 0)),
            file_url=best["url"],
            page_url=hit.get("pageURL", ""),
            author=hit.get("user", ""),
            author_url=f"https://pixabay.com/users/{hit.get('user', '')}-{hit.get('user_id', '')}/",
            preview=best.get("thumbnail", ""),
        )


def _best_variant(videos: dict) -> dict | None:
    """Pixabay отдаёт готовые варианты large/medium/small/tiny.

    Берём самый лёгкий, которого хватает под кадр 1080x1920: large — это
    часто 4K и лишние десятки мегабайт на каждую сцену.
    """
    variants = [v for v in videos.values() if isinstance(v, dict) and v.get("url")]
    if not variants:
        return None
    enough = [v for v in variants if min(v.get("width", 0), v.get("height", 0)) >= TARGET_W]
    pool = enough or variants
    return min(pool, key=lambda v: v.get("width", 0) * v.get("height", 0))
