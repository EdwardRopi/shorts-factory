"""Генерация сценария: тема + параметры -> провалидированный объект Script."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app import config
from app.ai.providers import LLMError, LLMProvider, get_provider
from app.schemas import CYRILLIC, Script

SCRIPT_CACHE = config.ROOT / "cache" / "scripts"

# Латинское слово от трёх букв. Двухбуквенные пропускаем: это обычно
# единицы измерения вроде «мм» в латинской раскладке или римские цифры.
LATIN_WORD = re.compile(r"\b[A-Za-z]{3,}\b")

# Темп речи, измеренный на реальном синтезе: Silero xenia даёт около 2,0 слов
# в секунду, SAPI Irina — 1,7. Ориентируемся на основной движок. Это только
# оценка для промпта: точную длительность сцены задаёт готовый файл озвучки.
WORDS_PER_SECOND = 2.0


@dataclass
class ScriptParams:
    topic: str
    duration: int = 30
    language: str = "русский"

    @property
    def n_scenes(self) -> int:
        return max(3, min(8, round(self.duration / 6)))

    @property
    def total_words(self) -> int:
        return round(self.duration * WORDS_PER_SECOND)

    @property
    def words_per_scene(self) -> int:
        return max(6, round(self.total_words / self.n_scenes))


def build_prompt(params: ScriptParams) -> str:
    template = (config.PROMPTS_DIR / "script_ru.txt").read_text(encoding="utf-8")
    return template.format(
        topic=params.topic,
        duration=params.duration,
        n_scenes=params.n_scenes,
        words=params.words_per_scene,
        total_words=params.total_words,
        min_words=round(params.total_words * 0.8),
        language=params.language,
    )


def unwrap(raw: dict) -> dict:
    """Снять лишнюю обёртку вокруг сценария.

    Модель иногда отвечает {"video": {...}} или {"script": {...}} вместо
    плоского объекта. Содержимое при этом корректное, и выбрасывать
    нормальную генерацию из-за одного лишнего уровня вложенности глупо.
    """
    if "scenes" in raw:
        return raw
    if len(raw) == 1:
        inner = next(iter(raw.values()))
        if isinstance(inner, dict) and "scenes" in inner:
            return inner
    return raw


def check_language(script: Script, params: ScriptParams) -> None:
    """Мелкие модели любят ответить по-английски, что бы им ни велели.

    Ловим это здесь: текст ошибки уйдёт модели следующей попыткой.
    """
    if "рус" not in params.language.lower():
        return
    spoken = " ".join(s.voiceover for s in script.scenes) + script.hook
    if not CYRILLIC.search(spoken):
        raise LLMError(
            "Весь текст написан не по-русски. Поля title, hook, voiceover, "
            "on_screen_text, cta и hashtags должны быть на русском языке. "
            "На английском остаётся только search_query_en."
        )

    # Латиница в озвучке — не косметика: русский синтезатор читает английское
    # слово по буквам или коверкает, и сцена звучит сломанной.
    latin = LATIN_WORD.findall(" ".join([script.title, script.hook, spoken]))
    if latin:
        raise LLMError(
            f"В русском тексте латиница: {', '.join(sorted(set(latin))[:5])}. "
            f"Замени эти слова русскими — диктор не сможет их произнести. "
            f"Латиница допустима только в поле search_query_en."
        )


def check_length(script: Script, params: ScriptParams) -> None:
    """Недобор по словам — самая частая проблема: ролик выйдет вдвое короче заказанного."""
    target = params.total_words
    got = script.word_count
    if got < target * 0.7:
        raise LLMError(
            f"Слишком короткий текст: {got} слов вместо нужных {target}. "
            f"Ролик получится примерно {script.estimated_seconds} с вместо {params.duration} с. "
            f"Разверни каждую реплику до {params.words_per_scene} слов, добавив деталей и следствий."
        )
    if got > target * 1.4:
        raise LLMError(
            f"Слишком длинный текст: {got} слов вместо {target}. Сократи реплики."
        )


def _cache_path(params: ScriptParams, provider_name: str) -> Path:
    key = f"{provider_name}|{params.topic}|{params.duration}|{params.language}"
    return SCRIPT_CACHE / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.json"


def generate_script(
    params: ScriptParams,
    provider: LLMProvider | None = None,
    attempts: int = 3,
    use_cache: bool = True,
) -> Script:
    """Сгенерировать сценарий. При невалидном ответе показываем модели её ошибку.

    Результат кэшируется: повторный прогон той же темы должен давать тот же
    сценарий, иначе кэш озвучки и клипов обнуляется на каждом запуске.
    """
    provider = provider or get_provider()

    cached = _cache_path(params, provider.name)
    if use_cache and cached.exists():
        try:
            return Script.model_validate_json(cached.read_text(encoding="utf-8"))
        except (ValidationError, OSError):
            cached.unlink(missing_ok=True)
    system = build_prompt(params)
    user = f"Сделай сценарий на тему: {params.topic}"
    schema = Script.model_json_schema()

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            raw = provider.complete_json(system, user, schema)
            script = Script.model_validate(unwrap(raw))
            check_language(script, params)
            check_length(script, params)
            if use_cache:
                SCRIPT_CACHE.mkdir(parents=True, exist_ok=True)
                cached.write_text(script.model_dump_json(indent=2), encoding="utf-8")
            return script
        except (ValidationError, LLMError) as e:
            last_error = e
            # Следующей попытке скармливаем текст ошибки — так модель обычно чинится сама.
            user = (
                f"Сделай сценарий на тему: {params.topic}\n\n"
                f"Предыдущий ответ был отклонён валидатором (попытка {attempt}). "
                f"Ошибка:\n{str(e)[:800]}\n"
                f"Исправь и верни JSON строго по схеме."
            )

    raise LLMError(f"Не удалось получить валидный сценарий за {attempts} попытки: {last_error}")
