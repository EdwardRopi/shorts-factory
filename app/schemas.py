"""Контракт сценария. Модель обязана вернуть JSON ровно этой формы."""

import re

from pydantic import BaseModel, Field, field_validator, model_validator

# Иероглифы, хангыль, кана — мелкие модели любят подмешивать их в русский текст.
CJK = re.compile(r"[　-ヿ㐀-䶿一-鿿가-힯]")
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
# Эмодзи и вариационные селекторы: в кадре вместо них будут пустые квадраты.
EMOJI = re.compile(
    "[\U0001f000-\U0001faff☀-➿︎️←-⇿⬀-⯿]"
)


SHOUTING = re.compile(r"\b[А-ЯЁA-Z]{2,}\b")

# Аббревиатуры, которые пишутся капслоком по правилам и кричанием не являются.
ABBREVIATIONS = {
    "ДНК", "РНК", "ВОЗ", "СССР", "США", "РФ", "ООН", "ГОСТ", "СМИ", "ВИЧ",
    "УФ", "ТВ", "ЖКТ", "СПИД", "МЧС", "НАСА", "ЕС", "ОАЭ", "КНР", "ЦРУ",
}


def reject_cjk(value: str, field: str) -> str:
    if CJK.search(value):
        raise ValueError(f"{field}: уберите иероглифы, пишите только на языке ролика — {value!r}")
    return value


def calm_down(text: str) -> str:
    """Убрать крик: капслок и частокол восклицательных знаков.

    Это косметика, из-за которой не стоит выбрасывать готовый сценарий, —
    правим молча, а не гоняем модель на повторную генерацию.
    """
    def unshout(m: re.Match) -> str:
        word = m.group(0)
        return word if word in ABBREVIATIONS else word.capitalize()

    text = SHOUTING.sub(unshout, text)
    text = re.sub(r"!{2,}", "!", text)
    # Один восклицательный знак на фразу — предел приличия.
    if text.count("!") > 1:
        head, _, tail = text.partition("!")
        text = head + "!" + tail.replace("!", ".")
    return text.strip()


class Scene(BaseModel):
    # Номер сцены выводится из порядка в списке, поэтому от модели не требуется:
    # просить её нумеровать вручную — лишний повод для отказа на ровном месте.
    id: int = 0
    voiceover: str = Field(min_length=10, max_length=400)
    search_query_en: str = Field(min_length=3, max_length=120)
    mood: str = Field(default="neutral", max_length=40)
    on_screen_text: str = Field(default="", max_length=60)

    @field_validator("voiceover")
    @classmethod
    def clean_voiceover(cls, v: str) -> str:
        return calm_down(reject_cjk(v.strip(), "voiceover"))

    @field_validator("search_query_en")
    @classmethod
    def latin_words_only(cls, v: str) -> str:
        """Ключ поиска — 2-8 английских слов через пробел, как их вводят на стоке."""
        v = v.replace("-", " ").replace("_", " ").strip()
        v = re.sub(r"\s+", " ", v)
        if CYRILLIC.search(v) or CJK.search(v):
            raise ValueError(f"search_query_en должен быть на английском, получено: {v!r}")
        words = v.split()
        if len(words) < 2:
            raise ValueError(f"search_query_en: нужно минимум 2 английских слова, получено: {v!r}")
        # Длинный запрос стоки всё равно обрежут сами — оставляем первые 8 слов,
        # но не выбрасываем из-за этого весь сценарий.
        return " ".join(words[:8]).lower()

    @field_validator("on_screen_text")
    @classmethod
    def short_caption(cls, v: str) -> str:
        """Надпись на экране: до 5 слов, иначе она не читается в кадре.

        Лишние слова обрезаем молча — это косметика, из-за которой
        не стоит выбрасывать нормальный сценарий и тратить генерацию заново.
        """
        v = reject_cjk(EMOJI.sub("", v), "on_screen_text")
        return " ".join(v.split()[:5])


class Script(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    hook: str = Field(min_length=10, max_length=300)
    scenes: list[Scene] = Field(min_length=3, max_length=10)
    cta: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=600)
    hashtags: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("title", "hook", "cta", "description")
    @classmethod
    def clean_text(cls, v: str) -> str:
        return calm_down(reject_cjk(v.strip(), "текст"))

    @model_validator(mode="after")
    def renumber(self) -> "Script":
        for i, scene in enumerate(self.scenes, start=1):
            scene.id = i
        return self

    @property
    def word_count(self) -> int:
        return sum(len(s.voiceover.split()) for s in self.scenes)

    @property
    def estimated_seconds(self) -> float:
        """Оценка до синтеза речи. Точную длительность даст TTS на шаге 3."""
        return round(self.word_count / 2.0 + 0.3 * len(self.scenes), 1)
