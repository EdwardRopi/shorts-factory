"""Общая модель клипа и правила отбора — одинаковые для всех видеостоков."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# Целевой кадр ролика.
TARGET_W, TARGET_H = 1080, 1920


@dataclass(slots=True)
class Clip:
    provider: str
    id: str
    width: int
    height: int
    duration: float
    file_url: str
    page_url: str
    author: str
    author_url: str
    preview: str = ""

    @property
    def is_portrait(self) -> bool:
        return self.height > self.width

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.id}"

    def fits_vertical(self) -> bool:
        """Годится ли клип для кадра 1080x1920 без апскейла.

        Вертикальный — нужен по ширине от 1080. Горизонтальный придётся резать
        по бокам, поэтому от него требуется высота от 1080: после кропа
        центральной полосы 9:16 останется ровно нужный размер.
        """
        if self.is_portrait:
            return self.width >= TARGET_W
        return self.height >= TARGET_W

    def score(self, need_seconds: float) -> float:
        """Чем больше, тем лучше. Отрицательное значение — клип не подходит."""
        if not self.fits_vertical() or self.duration < need_seconds:
            return -1.0

        s = 0.0
        # Вертикаль всегда предпочтительнее: не теряем края кадра.
        s += 3.0 if self.is_portrait else 0.0
        # Небольшой запас по длительности позволяет срезать рваные крайние кадры.
        slack = self.duration - need_seconds
        s += 2.0 if 1.0 <= slack <= 8.0 else (1.0 if slack < 1.0 else 0.5)
        # Разрешение: хватает — хорошо, избыток 4K только утяжеляет загрузку.
        short_side = min(self.width, self.height)
        if short_side >= TARGET_W:
            s += 2.0 if short_side <= 1440 else 1.0
        return s


class StockProvider(ABC):
    name: str

    @abstractmethod
    def search(self, query: str, need_seconds: float, limit: int = 15) -> list[Clip]:
        """Найти клипы по английскому запросу, уже отсортированные по пригодности."""


def rank(clips: list[Clip], need_seconds: float) -> list[Clip]:
    scored = [(c.score(need_seconds), c) for c in clips]
    good = [(s, c) for s, c in scored if s >= 0]
    good.sort(key=lambda pair: pair[0], reverse=True)
    return [c for _, c in good]


def pick_unique(clips: list[Clip], used: set[str]) -> Clip | None:
    """Первый подходящий клип, который ещё не встречался в этом ролике."""
    for c in clips:
        if c.key not in used:
            used.add(c.key)
            return c
    return None
