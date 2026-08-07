"""Тайминги слов для субтитров.

Транскрибируем именно синтезированное аудио, а не исходный текст: только так
таймкоды совпадают с реальной речью. Результат кэшируется — файл озвучки
детерминирован, значит и его разметка не меняется.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from app import config

TIMING_CACHE = config.ROOT / "cache" / "timings"
URL = "https://api.mistral.ai/v1/audio/transcriptions"
MODEL = "voxtral-mini-latest"


class TranscribeError(RuntimeError):
    pass


@dataclass(slots=True)
class Word:
    text: str
    start: float
    end: float


def words_for(audio: Path, text_hint: str = "") -> list[Word]:
    """Слова с таймкодами. При недоступности API — равномерная раскладка по тексту."""
    cached = TIMING_CACHE / f"{audio.stem}.json"
    if cached.exists():
        try:
            return [Word(**w) for w in json.loads(cached.read_text(encoding="utf-8"))]
        except (json.JSONDecodeError, TypeError, OSError):
            cached.unlink(missing_ok=True)

    try:
        words = _from_api(audio)
    except (httpx.HTTPError, TranscribeError, KeyError):
        if not text_hint:
            raise
        words = _spread_evenly(text_hint, audio)

    TIMING_CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(
        json.dumps([asdict(w) for w in words], ensure_ascii=False), encoding="utf-8"
    )
    return words


def _from_api(audio: Path) -> list[Word]:
    with open(audio, "rb") as f:
        r = httpx.post(
            URL,
            headers={"Authorization": f"Bearer {config.MISTRAL_API_KEY}"},
            files={"file": (audio.name, f, "audio/wav")},
            # Поле повторяющееся, а не JSON-строка: иначе API отвечает 422.
            data={"model": MODEL, "timestamp_granularities": ["word"]},
            timeout=180,
        )
    if r.status_code != 200:
        raise TranscribeError(f"транскрибация: HTTP {r.status_code} {r.text[:200]}")

    out = []
    for seg in r.json().get("segments", []):
        text = (seg.get("text") or "").strip()
        if text and seg.get("start") is not None and seg.get("end") is not None:
            out.append(Word(text=text, start=float(seg["start"]), end=float(seg["end"])))
    if not out:
        raise TranscribeError("транскрибация не вернула слов")
    return out


def _spread_evenly(text: str, audio: Path) -> list[Word]:
    """Запасной вариант: раскладываем слова пропорционально их длине.

    Работает прилично именно потому, что диктор читает наш собственный текст.
    """
    from app.ai.tts import audio_duration

    total = audio_duration(audio)
    parts = text.split()
    if not parts:
        return []
    weights = [len(p) + 1 for p in parts]
    scale = total / sum(weights)
    words, cursor = [], 0.0
    for part, weight in zip(parts, weights):
        span = weight * scale
        words.append(Word(text=part, start=round(cursor, 3), end=round(cursor + span, 3)))
        cursor += span
    return words
