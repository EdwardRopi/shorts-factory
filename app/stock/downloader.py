"""Загрузка клипов с кэшем по хешу URL.

Один и тот же «закат над морем» приходит в выдаче десятки раз — качать
его каждый раз заново значит терять трафик и секунды на ровном месте.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import httpx

from app import config
from app.stock.base import Clip

CLIP_CACHE = config.ROOT / "cache" / "clips"
MAX_BYTES = 80 * 1024 * 1024  # клипы тяжелее 80 МБ для 30-секундного ролика не нужны


class DownloadError(RuntimeError):
    pass


def download(clip: Clip) -> Path:
    digest = hashlib.sha256(clip.file_url.encode()).hexdigest()[:24]
    path = CLIP_CACHE / f"{clip.provider}-{digest}.mp4"
    if path.exists() and path.stat().st_size > 0:
        return path

    CLIP_CACHE.mkdir(parents=True, exist_ok=True)
    # Имя временного файла уникально для процесса: иначе два прогона одной темы
    # дерутся за один .part, а недобитый процесс держит его открытым.
    tmp = path.with_suffix(f".{os.getpid()}.part")
    written = 0
    try:
        with httpx.stream("GET", clip.file_url, timeout=120, follow_redirects=True) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    written += len(chunk)
                    if written > MAX_BYTES:
                        raise DownloadError(f"клип больше {MAX_BYTES // 1024 // 1024} МБ")
                    f.write(chunk)
    except httpx.HTTPError as e:
        tmp.unlink(missing_ok=True)
        raise DownloadError(f"не скачался {clip.key}: {e}") from e
    except DownloadError:
        tmp.unlink(missing_ok=True)
        raise

    _replace_with_retry(tmp, path)
    return path


def _replace_with_retry(tmp: Path, path: Path, attempts: int = 5) -> None:
    """Переименовать скачанный файл.

    На Windows это регулярно падает с WinError 32: антивирус или соседний
    процесс успевает подержать файл открытым сразу после записи.
    """
    for attempt in range(attempts):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.5 * (attempt + 1))
    # Файл скачан целиком, но переименовать не вышло — отдаём как есть.
    if path.exists() and path.stat().st_size > 0:
        tmp.unlink(missing_ok=True)
        return
    raise DownloadError(f"файл занят другим процессом: {path.name}")
