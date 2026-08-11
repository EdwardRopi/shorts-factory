"""Очередь задач для веба.

Один воркер в потоке: рендер упирается в CPU, и параллельные ffmpeg
только мешают друг другу. На проде это место занимает Redis + RQ,
интерфейс от замены не изменится.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.ai.script import ScriptParams
from app.ai.tts import get_tts
from app.render import STEPS, VIDEO_DIR, render_video

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="render")
_lock = threading.Lock()
_jobs: dict[str, "Job"] = {}


@dataclass
class Job:
    id: str
    topic: str
    duration: int
    voice: str
    folder: str = ""
    status: str = "queued"  # queued | running | done | failed
    step: str = "order"
    detail: str = ""
    error: str = ""
    result: dict[str, Any] | None = None
    scenes: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        done_index = next((i for i, (k, _) in enumerate(STEPS) if k == self.step), 0)
        return {
            "id": self.id,
            "topic": self.topic,
            "duration": self.duration,
            "voice": self.voice,
            "folder": self.folder,
            "status": self.status,
            "step": self.step,
            "step_index": done_index,
            "detail": self.detail,
            "error": self.error,
            "scenes": self.scenes,
            "warnings": self.warnings,
            "result": self.result,
        }


def create(topic: str, duration: int, voice: str, music: bool, fresh: bool,
           folder: str = "") -> Job:
    job = Job(id=uuid.uuid4().hex[:12], topic=topic, duration=duration, voice=voice,
              folder=folder)
    with _lock:
        _jobs[job.id] = job
    _pool.submit(_run, job, music, fresh)
    return job


def get(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def recent(limit: int = 24) -> list[Job]:
    return list(reversed(list(_jobs.values())))[:limit]


def _run(job: Job, music: bool, fresh: bool) -> None:
    job.status = "running"

    def report(key: str, detail: str) -> None:
        job.step = key
        job.detail = detail

    try:
        params = ScriptParams(topic=job.topic, duration=job.duration)
        result = render_video(
            params,
            tts=get_tts(voice=job.voice),
            use_cache=not fresh,
            report=report,
            out_dir=VIDEO_DIR / job.folder if job.folder else None,
        )
        job.scenes = [
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
        ]
        job.warnings = result.plan.warnings
        job.result = {
            # Путь относительно VIDEO_DIR, а не одно имя: ролики лежат по папкам,
            # и ровно такой путь ждёт роут /videos/{name:path}.
            "video": result.video.relative_to(VIDEO_DIR).as_posix(),
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
        }
        job.status = "done"
        job.step = "done"
    except Exception as e:  # воркер не имеет права падать молча
        job.status = "failed"
        job.error = f"{type(e).__name__}: {e}"
        traceback.print_exc()
