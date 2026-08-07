"""Единая точка сборки ролика: ей пользуются и CLI, и веб.

Шаги совпадают с конвейером из плана, чтобы прогресс в интерфейсе
описывал то же самое, что происходит в коде.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app import config
from app.ai.script import ScriptParams
from app.ai.transcribe import words_for
from app.ai.tts import TTSProvider, get_tts
from app.pipeline import VideoPlan, build_plan
from app.stock.downloader import download
from app.video.compose import compose
from app.video.music import credit, pick
from app.video.normalize import normalize_video, pad_audio
from app.video.subtitles import build_ass

VIDEO_DIR = config.VIDEO_DIR

STEPS: list[tuple[str, str]] = [
    ("order", "Заказ"),
    ("script", "Сценарий"),
    ("voice", "Озвучка"),
    ("clips", "Поиск"),
    ("media", "Кадрирование"),
    ("subs", "Субтитры"),
    ("compose", "Монтаж"),
    ("done", "Выдача"),
]

Reporter = Callable[[str, str], None]


@dataclass
class RenderResult:
    plan: VideoPlan
    video: Path
    voice: str
    engine: str
    music: str = ""
    seconds: float = 0.0
    size_mb: float = 0.0
    elapsed: float = 0.0
    authors: list[str] = field(default_factory=list)


def slugify(text: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in text.lower())[:40].strip("-")
    # Тема из одних знаков препинания или битой кодировки схлопнется в пустоту,
    # а файл без имени потом не найти.
    return slug or "video-" + hashlib.sha256(text.encode()).hexdigest()[:8]


def render_video(
    params: ScriptParams,
    tts: TTSProvider | None = None,
    use_cache: bool = True,
    with_subs: bool = True,
    with_music: bool = True,
    report: Reporter | None = None,
) -> RenderResult:
    started = time.perf_counter()
    tts = tts or get_tts()

    def step(key: str, detail: str = "") -> None:
        if report:
            report(key, detail)

    step("order", f"{params.duration} с, {params.n_scenes} сцен")

    plan = build_plan(
        params,
        tts=tts,
        use_cache=use_cache,
        on_step=lambda msg: step("script" if "сценар" in msg else
                                 "voice" if "озвуч" in msg else "clips", msg),
    )

    missing = [sp.scene.id for sp in plan.scenes if sp.clip is None]
    if missing:
        raise RuntimeError(f"нет клипов для сцен: {', '.join(map(str, missing))}")

    pairs = []
    for sp in plan.scenes:
        step("media", f"сцена {sp.scene.id} из {len(plan.scenes)}")
        src = download(sp.clip)
        pairs.append((normalize_video(src, sp.duration), pad_audio(sp.audio, sp.duration)))

    subs = None
    if with_subs:
        step("subs", "размечаю по словам")
        scenes_words, offset = [], 0.0
        for sp in plan.scenes:
            scenes_words.append((words_for(sp.audio, sp.scene.voiceover), offset,
                                 sp.scene.on_screen_text))
            offset += sp.duration
        subs = build_ass(scenes_words,
                         config.ROOT / "cache" / "subs" / f"{slugify(params.topic)}.ass")

    track = pick(params.topic) if with_music else None

    step("compose", "склеиваю и нормализую звук")
    out = VIDEO_DIR / f"{slugify(params.topic)}-{int(time.time())}.mp4"
    compose(pairs, out, subtitles=subs, music=track, total_seconds=plan.total_seconds)

    step("done", out.name)
    result = RenderResult(
        plan=plan,
        video=out,
        voice=tts.voice,
        engine=tts.name,
        music=(credit(track) or track.stem) if track else "",
        seconds=plan.total_seconds,
        size_mb=round(out.stat().st_size / 1024 / 1024, 1),
        elapsed=round(time.perf_counter() - started, 1),
        authors=sorted({sp.clip.author for sp in plan.scenes if sp.clip and sp.clip.author}),
    )
    _write_sidecar(result, params)
    return result


def _write_sidecar(result: RenderResult, params: ScriptParams) -> None:
    """Метаданные рядом с роликом.

    Список задач живёт в памяти и обнуляется при перезапуске сервера, а
    библиотека готовых роликов обязана переживать это без потерь.
    """
    meta = {
        "video": result.video.name,
        "topic": params.topic,
        "title": result.plan.script.title,
        "hook": result.plan.script.hook,
        "hashtags": result.plan.script.hashtags,
        "seconds": result.seconds,
        "size_mb": result.size_mb,
        "elapsed": result.elapsed,
        "music": result.music,
        "engine": result.engine,
        "voice": result.voice,
        "authors": result.authors,
        "scenes": [
            {
                "id": sp.scene.id,
                "text": sp.scene.voiceover,
                "caption": sp.scene.on_screen_text,
                "seconds": sp.duration,
                "query": sp.scene.search_query_en,
                "poster": sp.clip.preview if sp.clip else "",
                "author": sp.clip.author if sp.clip else "",
                "provider": sp.clip.provider if sp.clip else "",
            }
            for sp in result.plan.scenes
        ],
    }
    result.video.with_suffix(".json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
