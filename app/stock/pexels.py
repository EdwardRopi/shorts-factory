"""Клиент Pexels Videos API.

Лимиты: 200 запросов в час, 20 000 в месяц. Атрибуция обязательна —
имя автора сохраняем в Clip и показываем в интерфейсе.
"""

from __future__ import annotations

import httpx

from app import config
from app.stock import cache
from app.stock.base import TARGET_W, Clip, StockProvider, rank

URL = "https://api.pexels.com/videos/search"


class PexelsError(RuntimeError):
    pass


class PexelsProvider(StockProvider):
    name = "pexels"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or config.PEXELS_API_KEY
        if not self.api_key:
            raise PexelsError("PEXELS_API_KEY не задан в .env")

    def search(self, query: str, need_seconds: float, limit: int = 15) -> list[Clip]:
        extra = f"limit={limit}"
        data = cache.get(self.name, query, extra)
        if data is None:
            data = self._fetch(query, limit)
            cache.put(self.name, query, data, extra)

        clips = [c for v in data.get("videos", []) if (c := self._to_clip(v))]
        return rank(clips, need_seconds)

    def _fetch(self, query: str, limit: int) -> dict:
        params = {
            "query": query,
            "orientation": "portrait",
            "per_page": min(limit, 80),
        }
        try:
            r = httpx.get(
                URL,
                params=params,
                headers={"Authorization": self.api_key},
                timeout=30,
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise PexelsError("Pexels: исчерпан лимит запросов (200/час)") from e
            raise PexelsError(f"Pexels: HTTP {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise PexelsError(f"Pexels недоступен: {e}") from e
        return r.json()

    @staticmethod
    def _to_clip(v: dict) -> Clip | None:
        best = _best_file(v.get("video_files", []))
        if not best:
            return None
        user = v.get("user") or {}
        return Clip(
            provider="pexels",
            id=str(v["id"]),
            width=best.get("width") or v.get("width", 0),
            height=best.get("height") or v.get("height", 0),
            duration=float(v.get("duration", 0)),
            file_url=best["link"],
            page_url=v.get("url", ""),
            author=user.get("name", ""),
            author_url=user.get("url", ""),
            preview=v.get("image", ""),
        )


def _best_file(files: list[dict]) -> dict | None:
    """Самый лёгкий из файлов, которого хватает для кадра 1080x1920.

    Брать первый попавшийся нельзя: в выдаче лежат и 360p, и 4K. Первый
    испортит картинку, второй утяжелит загрузку на десятки мегабайт.
    """
    mp4 = [f for f in files if f.get("file_type") == "video/mp4" and f.get("link")]
    if not mp4:
        return None
    enough = [f for f in mp4 if min(f.get("width", 0), f.get("height", 0)) >= TARGET_W]
    pool = enough or mp4
    return min(pool, key=lambda f: f.get("width", 0) * f.get("height", 0))
