"""Обёртка над ffmpeg: единая точка запуска и понятные ошибки."""

from __future__ import annotations

from pathlib import Path

from app import proc


class FFmpegError(RuntimeError):
    pass


def run(args: list[str], what: str) -> None:
    """Запустить ffmpeg. При падении отдать хвост stderr — там всегда причина."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    r = proc.run(cmd)
    if r.returncode != 0:
        tail = (r.stderr or "").strip().splitlines()[-6:]
        raise FFmpegError(f"{what}: ffmpeg вернул {r.returncode}\n" + "\n".join(tail))


def probe_duration(path: Path) -> float:
    r = proc.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)]
    )
    try:
        return round(float(r.stdout.strip()), 3)
    except ValueError as e:
        raise FFmpegError(f"не читается длительность {path.name}: {r.stderr[:200]}") from e
