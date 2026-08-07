"""Поиск по обоим стокам сразу с деградацией при отказе одного из них."""

from __future__ import annotations

from app.stock.base import Clip, StockProvider, rank
from app.stock.pexels import PexelsError, PexelsProvider
from app.stock.pixabay import PixabayError, PixabayProvider


class ClipFinder:
    def __init__(self, providers: list[StockProvider] | None = None):
        if providers is None:
            providers = []
            for factory in (PexelsProvider, PixabayProvider):
                try:
                    providers.append(factory())
                except (PexelsError, PixabayError):
                    continue  # нет ключа — работаем на том, что есть
        self.providers = providers
        self.errors: list[str] = []

    def search(self, query: str, need_seconds: float, limit: int = 15) -> list[Clip]:
        found: list[Clip] = []
        self.errors = []
        for p in self.providers:
            try:
                found.extend(p.search(query, need_seconds, limit))
            except (PexelsError, PixabayError) as e:
                # Падение одного стока не должно ронять задачу целиком.
                self.errors.append(str(e))
        return rank(found, need_seconds)

    def search_with_fallback(self, query: str, need_seconds: float) -> tuple[list[Clip], str]:
        """Если по полному ключу пусто — пробуем сокращённый.

        Возвращает клипы и тот запрос, который в итоге сработал.
        """
        attempts = [query]
        words = query.split()
        if len(words) > 2:
            attempts.append(" ".join(words[:2]))
        if len(words) > 1:
            attempts.append(words[0])

        for attempt in attempts:
            clips = self.search(attempt, need_seconds)
            if clips:
                return clips, attempt
        return [], query
