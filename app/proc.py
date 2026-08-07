"""Запуск внешних процессов с защитой от флаки Windows.

На этой машине CreateProcess периодически отвечает WinError 5 «отказано в
доступе» на совершенно нормальную команду — виноват не код, а антивирус или
блокировка файла в момент запуска. Через доли секунды та же команда работает,
поэтому просто повторяем.
"""

from __future__ import annotations

import subprocess
import time

ATTEMPTS = 4
PAUSE = 0.4


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")

    last: OSError | None = None
    for attempt in range(ATTEMPTS):
        try:
            return subprocess.run(cmd, **kwargs)
        except PermissionError as e:  # WinError 5
            last = e
            time.sleep(PAUSE * (attempt + 1))
    raise RuntimeError(f"не удалось запустить {cmd[0]} за {ATTEMPTS} попытки: {last}")
