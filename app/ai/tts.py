"""Синтез речи.

Русского голоса у Voxtral нет — проверено обратной транскрибацией: модель
читает кириллицу английской фонетикой. Поэтому для русского используем
локальные движки, а Voxtral оставляем для англоязычных роликов.

Порядок предпочтения для русского:
  1. Silero  — локально, бесплатно, живая интонация (нужен torch)
  2. SAPI    — встроенный в Windows голос Irina, работает всегда, звучит роботично
"""

from __future__ import annotations

import hashlib
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from app import config, proc

AUDIO_CACHE = config.ROOT / "cache" / "audio"


class TTSError(RuntimeError):
    pass


def audio_duration(path: Path) -> float:
    """Точная длительность файла. Именно она задаёт длительность сцены."""
    out = proc.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)]
    )
    return round(float(out.stdout.strip()), 3)


class TTSProvider(ABC):
    name: str
    voice: str

    @abstractmethod
    def _synthesize(self, text: str, path: Path) -> None:
        """Записать речь в path (wav)."""

    def say(self, text: str) -> tuple[Path, float]:
        """Синтезировать с кэшированием. Возвращает файл и его длительность."""
        digest = hashlib.sha256(f"{self.name}|{self.voice}|{text}".encode()).hexdigest()[:20]
        path = AUDIO_CACHE / f"{self.name}-{digest}.wav"
        if not path.exists() or path.stat().st_size == 0:
            AUDIO_CACHE.mkdir(parents=True, exist_ok=True)
            self._synthesize(text, path)
        if not path.exists() or path.stat().st_size == 0:
            raise TTSError(f"{self.name}: синтез не дал файла")
        return path, audio_duration(path)


class SapiTTS(TTSProvider):
    """Штатный движок Windows. Ничего не нужно ставить, но голос заметно синтетический."""

    name = "sapi"

    def __init__(self, voice: str = "Microsoft Irina Desktop", rate: int = 1):
        self.voice = voice
        self.rate = rate  # -10..10, по умолчанию чуть быстрее обычного

    def _synthesize(self, text: str, path: Path) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8-sig") as f:
            f.write(text)
            txt = f.name

        script = f"""
        Add-Type -AssemblyName System.Speech
        $t = Get-Content -Raw -Encoding UTF8 '{txt}'
        $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
        $s.SelectVoice('{self.voice}')
        $s.Rate = {self.rate}
        $s.SetOutputToWaveFile('{path}')
        $s.Speak($t)
        $s.Dispose()
        """
        r = proc.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
        Path(txt).unlink(missing_ok=True)
        if r.returncode != 0:
            raise TTSError(f"SAPI: {r.stderr[:300]}")


class SileroTTS(TTSProvider):
    """Локальная нейросетевая озвучка. Модель качается один раз, дальше офлайн."""

    name = "silero"

    # v5 крупнее и звучит естественнее v4; версия вынесена в поле,
    # чтобы можно было откатиться одной строкой.
    VERSION = "v5_ru"
    _model_cache: dict[str, object] = {}

    def __init__(self, voice: str = "xenia", sample_rate: int = 48000,
                 version: str | None = None):
        self.voice = voice
        self.sample_rate = sample_rate
        self.version = version or self.VERSION

    @property
    def model_path(self) -> Path:
        return config.ROOT / "cache" / "models" / f"{self.version}.pt"

    @property
    def model_url(self) -> str:
        return f"https://models.silero.ai/models/tts/ru/{self.version}.pt"

    def _fetch_model(self) -> Path:
        """Качаем файл модели сами.

        torch.hub здесь бесполезен: он ходит через urllib, тот подхватывает
        системный прокси и падает с KeyError: 'Authorization'.
        """
        path = self.model_path
        if path.exists() and path.stat().st_size > 0:
            return path

        import httpx

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        try:
            with httpx.Client(trust_env=False, timeout=3600, follow_redirects=True) as c:
                with c.stream("GET", self.model_url) as r:
                    r.raise_for_status()
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_bytes(1 << 16):
                            f.write(chunk)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            raise TTSError(f"не скачалась модель Silero: {e}") from e
        tmp.replace(path)
        return path

    def _load(self):
        if self.version not in self._model_cache:
            try:
                import torch
            except ImportError as e:
                raise TTSError("Silero требует torch: pip install torch") from e

            path = self._fetch_model()
            torch.set_num_threads(4)
            model = torch.package.PackageImporter(str(path)).load_pickle(
                "tts_models", "model"
            )
            model.to(torch.device("cpu"))
            self._model_cache[self.version] = model
        return self._model_cache[self.version]

    def speakers(self) -> list[str]:
        return list(getattr(self._load(), "speakers", []))

    def _synthesize(self, text: str, path: Path) -> None:
        model = self._load()
        # put_accent и put_yo снимают главную беду синтеза на русском:
        # неверное ударение и «е» вместо «ё». Разница слышна сразу.
        model.save_wav(
            text=text,
            speaker=self.voice,
            sample_rate=self.sample_rate,
            put_accent=True,
            put_yo=True,
            audio_path=str(path),
        )


def get_tts(name: str | None = None, voice: str | None = None) -> TTSProvider:
    """Silero, если доступен, иначе штатный голос Windows."""
    if name == "sapi":
        return SapiTTS(voice or "Microsoft Irina Desktop")
    if name == "silero":
        return SileroTTS(voice or "xenia")

    try:
        import torch  # noqa: F401
        return SileroTTS(voice or "xenia")
    except ImportError:
        return SapiTTS(voice or "Microsoft Irina Desktop")
