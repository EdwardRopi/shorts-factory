"""Собрать несколько роликов подряд одним процессом.

    python batch.py "тема один" "тема два"

Модель озвучки грузится один раз на весь список, а не на каждый ролик.
"""

from __future__ import annotations

import sys
import time

from app.ai.script import ScriptParams
from app.ai.tts import get_tts
from app.render import render_video

topics = sys.argv[1:]
if not topics:
    sys.exit("укажите темы аргументами")

tts = get_tts()
print(f"движок озвучки: {tts.name} / {tts.voice}", flush=True)

ok, failed = [], []
started_all = time.perf_counter()

for i, topic in enumerate(topics, 1):
    print(f"\n=== {i}/{len(topics)}  {topic}", flush=True)
    try:
        result = render_video(
            ScriptParams(topic=topic, duration=30),
            tts=tts,
            report=lambda key, detail: print(f"    {key:8} {detail}", flush=True),
        )
    except Exception as e:
        print(f"    ОШИБКА: {type(e).__name__}: {e}", flush=True)
        failed.append(topic)
        continue

    print(
        f"    готово: {result.video.name}\n"
        f"    {result.seconds} с · {result.size_mb} МБ · за {result.elapsed} с",
        flush=True,
    )
    ok.append((topic, result))

print(f"\n{'=' * 60}")
print(f"собрано {len(ok)} из {len(topics)} за {(time.perf_counter() - started_all) / 60:.1f} мин")
for topic, r in ok:
    print(f"  {r.seconds:5.1f} с  {r.plan.script.title[:50]:50}  {r.video.name}")
for topic in failed:
    print(f"  не вышло: {topic}")
