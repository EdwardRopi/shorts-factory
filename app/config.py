import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Какой провайдер LLM использовать: ollama (локально, бесплатно) или mistral (API).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

PROMPTS_DIR = ROOT / "prompts"
OUT_DIR = ROOT / "out"

# Витрина: интерфейс работает, сборка выключена. Нужен для бесплатного хостинга,
# где нет ни памяти под модель озвучки, ни процессорного времени под ffmpeg.
DEMO_MODE = os.getenv("DEMO_MODE", "").lower() in ("1", "true", "yes")

# Откуда брать готовые ролики. На витрине это папка demo/, лежащая в репозитории.
VIDEO_DIR = ROOT / os.getenv("VIDEO_DIR", "out/videos")
