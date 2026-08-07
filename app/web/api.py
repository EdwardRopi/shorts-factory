"""HTTP-слой: форма заказа, статус рендера, отдача готовых роликов."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.ai.tts import SapiTTS, SileroTTS
from app.render import STEPS, VIDEO_DIR
from app.web import jobs

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Shorts Factory")


class JobRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    duration: int = Field(default=30, ge=15, le=90)
    voice: str = "xenia"
    music: bool = True
    fresh: bool = False


@app.get("/api/config")
def get_config() -> dict:
    """Голоса и шаги конвейера: интерфейс не должен их дублировать у себя."""
    try:
        voices = [{"id": v, "engine": "silero"} for v in SileroTTS().speakers()
                  if v != "random"]
    except Exception:
        voices = []
    voices.append({"id": SapiTTS().voice, "engine": "sapi"})
    return {
        "voices": voices,
        "steps": [{"key": k, "label": label} for k, label in STEPS],
        "durations": [15, 30, 45, 60],
    }


@app.post("/api/jobs")
def create_job(req: JobRequest) -> dict:
    job = jobs.create(req.topic.strip(), req.duration, req.voice, req.music, req.fresh)
    return job.as_dict()


@app.get("/api/jobs")
def list_jobs() -> dict:
    return {"jobs": [j.as_dict() for j in jobs.recent()]}


@app.get("/api/library")
def library() -> dict:
    """Готовые ролики читаем с диска: они должны пережить перезапуск сервера."""
    items = []
    for meta_path in sorted(VIDEO_DIR.glob("*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if (VIDEO_DIR / meta.get("video", "")).is_file():
            items.append(meta)
    return {"items": items}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "задача не найдена")
    return job.as_dict()


@app.get("/videos/{name}")
def get_video(name: str) -> FileResponse:
    path = (VIDEO_DIR / name).resolve()
    if not path.is_file() or VIDEO_DIR.resolve() not in path.parents:
        raise HTTPException(404, "ролик не найден")
    return FileResponse(path, media_type="video/mp4")


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
