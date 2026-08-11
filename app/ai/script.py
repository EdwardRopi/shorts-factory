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

# «XIX» — тоже латиница, и Silero прочитает её по буквам. Отклонять правильно,
# но модели нужно объяснить это отдельно: подсказка про торговые марки ей тут
# не помогает, и она молча повторяет ту же цифру все три попытки.
ROMAN_NUMERAL = re.compile(r"^[IVXLCDM]+$", re.IGNORECASE)

# Темп речи, измеренный на реальном синтезе пяти реплик разной длины:
# Silero baya даёт 2,1 слова в секунду, xenia — 2,4, SAPI Irina — 1,7.
# Ориентируемся на голос по умолчанию. Это только оценка для промпта: точную
# длительность сцены задаёт готовый файл озвучки.
WORDS_PER_SECOND = 2.1

# Сколько бы слов ни попросили, модель приносит меньше. Просим с запасом,
# иначе ролик выходит короче заказанного на треть. Коэффициент подобран
# замерами: на 1.25 начинался перелёт до 36 секунд при цели 30.
UNDERSHOOT = 1.15


@dataclass
class ScriptParams:
    topic: str
    duration: int = 30
    language: str = "русский"

    @property
    def n_scenes(self) -> int:
        return max(3, min(8, round(self.duration / 6)))

    @property
    def natural_words(self) -> int:
        """Сколько слов физически нужно, чтобы заполнить хронометраж."""
        return round(self.duration * WORDS_PER_SECOND)

    @property
    def total_words(self) -> int:
        """Сколько слов просим у модели — с запасом на её систематический недобор."""
        return round(self.natural_words * UNDERSHOOT)

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
        found = sorted(set(latin))[:5]
        how = (
            "Названия и марки запиши кириллицей по произношению "
            "(Midjourney → Мидджорни, iPhone → айфон), остальное переведи."
        )
        if any(ROMAN_NUMERAL.match(word) for word in found):
            how = "Римские цифры пиши словами: «XIX век» → «девятнадцатый век». " + how
        raise LLMError(
            f"В русском тексте латиница: {', '.join(found)}. "
            f"Диктор не сможет это произнести. {how} Латиница допустима "
            f"только в поле search_query_en."
        )


def check_length(script: Script, params: ScriptParams) -> None:
    """Недобор по словам — самая частая проблема: ролик выйдет короче заказанного.

    Сверяемся с реальной потребностью, а не с завышенным запросом: просим мы
    с запасом, но браковать сценарий за то, что он не дотянул до запаса, глупо.
    """
    target = params.natural_words
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
    nudge: str = "",
) -> Script:
    """Сгенерировать сценарий. При невалидном ответе показываем модели её ошибку.

    Результат кэшируется: повторный прогон той же темы должен давать тот же
    сценарий, иначе кэш озвучки и клипов обнуляется на каждом запуске.
    """
    provider = provider or get_provider()

    # С подсказкой кэш не трогаем: мы как раз и хотим другой, более длинный текст.
    use_cache = use_cache and not nudge
    cached = _cache_path(params, provider.name)
    if use_cache and cached.exists():
        try:
            return Script.model_validate_json(cached.read_text(encoding="utf-8"))
        except (ValidationError, OSError):
            cached.unlink(missing_ok=True)
    system = build_prompt(params)
    user = f"Сделай сценарий на тему: {params.topic}"
    if nudge:
        user += f"\n\n{nudge}"
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
