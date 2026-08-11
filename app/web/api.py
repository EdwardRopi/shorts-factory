"""HTTP-слой: форма заказа, статус рендера, отдача готовых роликов."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import config
from app.ai.tts import SapiTTS, SileroTTS
from app.render import STEPS, VIDEO_DIR
from app.web import jobs

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Shorts Factory")


@app.on_event("startup")
def warm_up() -> None:
    """Грузим модель озвучки заранее, в главном потоке.

    Если этого не сделать, torch инициализируется уже внутри рабочего потока
    очереди и роняет весь процесс segfault'ом на первой же задаче.
    """
    if config.DEMO_MODE:
        print("[warmup] витрина: сборка выключена, модель не грузим")
        return
    try:
        SileroTTS()._load()
        print("[warmup] модель озвучки готова")
    except Exception as e:
        print(f"[warmup] Silero недоступен, останется SAPI: {e}")


class JobRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    duration: int = Field(default=30, ge=15, le=90)
    voice: str = "xenia"
    music: bool = True
    fresh: bool = False
    folder: str = ""


# Символы, запрещённые в именах папок Windows, плюс разделители пути.
_BAD_IN_NAME = set('\\/:*?"<>|')


def safe_folder(name: str) -> str:
    """Имя папки из пользовательского ввода.

    Поле приходит из браузера, поэтому в нём может оказаться что угодно, вплоть
    до `..\\..\\Windows`. Оставляем ровно одно звено пути без служебных символов.
    Пустое поле — не корень: иначе ролики снова копятся кучей в out/videos.
    """
    cleaned = "".join(" " if c in _BAD_IN_NAME else c for c in name).strip(" .")
    return cleaned[:60].strip() or "разное"


@app.get("/api/config")
def get_config() -> dict:
    """Голоса и шаги конвейера: интерфейс не должен их дублировать у себя."""
    try:
        voices = [{"id": v, "engine": "silero"} for v in SileroTTS().speakers()
                  if v != "random"]
    except Exception:
        voices = []
    voices.append({"id": SapiTTS().voice, "engine": "sapi"})
    if config.DEMO_MODE and not voices[:-1]:
        voices = [{"id": v, "engine": "silero"} for v in
                  ("xenia", "baya", "kseniya", "aidar", "eugene")]
    return {
        "voices": voices,
        "steps": [{"key": k, "label": label} for k, label in STEPS],
        "durations": [15, 30, 45, 60],
        "demo": config.DEMO_MODE,
    }


@app.post("/api/jobs")
def create_job(req: JobRequest) -> dict:
    if config.DEMO_MODE:
        raise HTTPException(
            503,
            "Это витрина: сборка здесь выключена. Ролик весит серверу минуту "
            "процессорного времени и полтора гигабайта памяти под модель озвучки, "
            "чего на бесплатном хостинге нет. Готовые ролики ниже собраны локально.",
        )
    job = jobs.create(req.topic.strip(), req.duration, req.voice, req.music, req.fresh,
                      folder=safe_folder(req.folder))
    return job.as_dict()


@app.get("/api/jobs")
def list_jobs() -> dict:
    return {"jobs": [j.as_dict() for j in jobs.recent()]}


@app.get("/api/library")
def library() -> dict:
    """Готовые ролики читаем с диска: они должны пережить перезапуск сервера.

    Ролики разложены по тематическим подпапкам, поэтому обходим дерево целиком,
    а в meta["video"] кладём путь относительно VIDEO_DIR — его же ждёт /videos/.
    """
    items = []
    for meta_path in sorted(VIDEO_DIR.rglob("*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        video = meta_path.parent / meta.get("video", "")
        if video.is_file():
            meta["video"] = video.relative_to(VIDEO_DIR).as_posix()
            items.append(meta)
    return {"items": items}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "задача не найдена")
    return job.as_dict()


@app.get("/videos/{name:path}")
def get_video(name: str) -> FileResponse:
    path = (VIDEO_DIR / name).resolve()
    if not path.is_file() or VIDEO_DIR.resolve() not in path.parents:
        raise HTTPException(404, "ролик не найден")
    return FileResponse(path, media_type="video/mp4")


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
