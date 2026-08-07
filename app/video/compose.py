"""Финальная сборка ролика из подготовленных сцен."""

from __future__ import annotations

from pathlib import Path

from app.video.ffmpeg import run
from app.video.music import FADE_OUT, VOLUME
from app.video.subtitles import filter_path

# Целевая громкость соцсетей: без нормализации платформа придавит звук сама,
# и ролик будет звучать глуше соседних в ленте.
LOUDNESS = "loudnorm=I=-14:TP=-1.5:LRA=11"


def compose(
    pairs: list[tuple[Path, Path]],
    out: Path,
    subtitles: Path | None = None,
    music: Path | None = None,
    total_seconds: float = 0.0,
) -> Path:
    """Склеить пары (видео сцены, аудио сцены) в готовый ролик.

    Одним вызовом ffmpeg: промежуточные файлы склейки не нужны, а видео и
    аудио каждой сцены уже имеют одинаковую длительность.
    """
    if not pairs:
        raise ValueError("нечего склеивать")

    args: list[str] = []
    for video, audio in pairs:
        args += ["-i", str(video), "-i", str(audio)]

    n = len(pairs)
    streams = "".join(f"[{2 * i}:v][{2 * i + 1}:a]" for i in range(n))
    steps = [f"{streams}concat=n={n}:v=1:a=1[vraw][voice]"]

    if subtitles:
        steps.append(f"[vraw]subtitles='{filter_path(subtitles)}'[v]")
    else:
        steps.append("[vraw]null[v]")

    if music:
        args += ["-stream_loop", "-1", "-i", str(music)]
        fade_at = max(0.0, total_seconds - FADE_OUT)
        steps.append(
            f"[{2 * n}:a]volume={VOLUME},afade=t=out:st={fade_at:.2f}:d={FADE_OUT}[bg]"
        )
        # duration=first обрезает музыку по длине голосовой дорожки.
        steps.append(f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=0[mixed]")
        steps.append(f"[mixed]{LOUDNESS}[a]")
    else:
        steps.append(f"[voice]{LOUDNESS}[a]")

    out.parent.mkdir(parents=True, exist_ok=True)
    run([
        *args,
        "-filter_complex", ";".join(steps),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        # loudnorm поднимает частоту дискретизации до 192 кГц, и кодек тянет её
        # в файл. Возвращаем 48 кГц: больше соцсетям не нужно, а вес растёт.
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out),
    ], "финальная сборка")
    return out
