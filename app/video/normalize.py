"""Приведение исходных материалов к единому формату сцены.

Все сцены обязаны быть одинаковыми по кодеку, разрешению и частоте кадров —
иначе склейка либо развалится, либо потребует полного перекодирования.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app import config
from app.video.ffmpeg import run

SCENE_CACHE = config.ROOT / "cache" / "scenes"

WIDTH, HEIGHT, FPS = 1080, 1920, 30
VIDEO_FILTER = (
    f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
    f"crop={WIDTH}:{HEIGHT},fps={FPS},format=yuv420p"
)


def _cached(prefix: str, *parts: str, suffix: str) -> Path:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]
    SCENE_CACHE.mkdir(parents=True, exist_ok=True)
    return SCENE_CACHE / f"{prefix}-{digest}{suffix}"


def normalize_video(src: Path, duration: float) -> Path:
    """Клип -> ровно duration секунд вертикального видео без звука.

    scale c increase плюс crop заполняет кадр без чёрных полей и без искажения
    пропорций. stream_loop зацикливает клип, если он короче нужного.
    """
    out = _cached("scene", str(src), f"{duration:.3f}", suffix=".mp4")
    if out.exists() and out.stat().st_size > 0:
        return out

    run([
        "-stream_loop", "-1",
        "-i", str(src),
        "-t", f"{duration:.3f}",
        "-vf", VIDEO_FILTER,
        "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-video_track_timescale", "30000",
        str(out),
    ], f"нормализация {src.name}")
    return out


def pad_audio(src: Path, duration: float) -> Path:
    """Озвучка -> ровно duration секунд: добиваем тишиной до длины сцены."""
    out = _cached("audio", str(src), f"{duration:.3f}", suffix=".wav")
    if out.exists() and out.stat().st_size > 0:
        return out

    run([
        "-i", str(src),
        "-af", f"apad=whole_dur={duration:.3f}",
        "-t", f"{duration:.3f}",
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
        str(out),
    ], f"выравнивание аудио {src.name}")
    return out
