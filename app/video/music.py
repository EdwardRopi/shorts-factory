"""Подбор фоновой музыки.

Треки не входят в репозиторий: лицензионно чистую музыку нужно положить
самому в assets/music (Pixabay Music, Free Music Archive). Если папка пуста,
ролик собирается без музыки — это не ошибка.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app import config

MUSIC_DIR = config.ROOT / "assets" / "music"
EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".opus"}

# Музыка должна быть заметно тише голоса: на 0,3 и выше речь перестаёт читаться.
VOLUME = 0.14
FADE_OUT = 3.0


CREDITS_FILE = MUSIC_DIR / "CREDITS.txt"


def credit(track: Path) -> str:
    """Строка атрибуции для трека, если она записана в CREDITS.txt.

    Формат файла: «имя_файла.mp3 = текст атрибуции», по строке на трек.
    """
    if not CREDITS_FILE.exists():
        return ""
    for line in CREDITS_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, _, text = line.partition("=")
            if name.strip() == track.name:
                return text.strip()
    return ""


def pick(seed: str = "") -> Path | None:
    """Трек, выбранный детерминированно по теме: один ролик — одна музыка."""
    if not MUSIC_DIR.exists():
        return None
    tracks = sorted(p for p in MUSIC_DIR.iterdir() if p.suffix.lower() in EXTENSIONS)
    if not tracks:
        return None
    index = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(tracks)
    return tracks[index]
