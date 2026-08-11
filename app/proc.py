"""Запуск внешних процессов с защитой от флаки Windows.

На этой машине CreateProcess периодически отвечает WinError 5 «отказано в
доступе» на совершенно нормальную команду — виноват не код, а антивирус или
блокировка файла в момент запуска. Через доли секунды та же команда работает,
поэтому просто повторяем.
"""

from __future__ import annotations

import subprocess
import time
from functools import lru_cache
from pathlib import Path

# В переносимой сборке ffmpeg и ffprobe лежат в bin/ рядом с программой:
# на чужом компьютере их нет ни в PATH, ни вообще в системе.
BUNDLED_BIN = Path(__file__).resolve().parent.parent / "bin"

ATTEMPTS = 4
PAUSE = 0.4
TIMEOUT = 300

# 0xC0000005 — процесс не отработал с ошибкой, а рухнул на access violation.
# У ffmpeg и ffprobe это случается прямо на старте, на здоровых входных файлах.
CRASH_CODES = {3221225477, -1073741819}


@lru_cache(maxsize=8)
def resolve(program: str) -> str:
    """Путь к внешней программе: сначала своя папка bin/, потом PATH."""
    local = BUNDLED_BIN / f"{program}.exe"
    return str(local) if local.is_file() else program


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    cmd = [resolve(cmd[0]), *cmd[1:]]
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")
    kwargs.setdefault("timeout", TIMEOUT)

    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            result = subprocess.run(cmd, **kwargs)
        except PermissionError as e:  # WinError 5
            last = e
        except subprocess.TimeoutExpired as e:
            # Изредка ffprobe встаёт колом и сам уже не выйдет. Ждать вторую
            # такую паузу смысла нет: если повтор тоже завис — дело не в удаче.
            last = e
            if attempt >= 1:
                break
        else:
            if result.returncode not in CRASH_CODES:
                return result
            last = RuntimeError(f"{cmd[0]} рухнул с кодом {result.returncode}")
        time.sleep(PAUSE * (attempt + 1))
    raise RuntimeError(f"не удалось выполнить {cmd[0]} за {ATTEMPTS} попытки: {last}")
