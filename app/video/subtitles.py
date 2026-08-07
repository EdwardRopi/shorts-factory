"""Генератор ASS-субтитров с пословной подсветкой.

Короткие видео в основном смотрят без звука, поэтому субтитры — не украшение,
а половина продукта. Подсветка текущего слова удерживает взгляд на тексте.
"""

from __future__ import annotations

from pathlib import Path

from app.ai.transcribe import Word

WIDTH, HEIGHT = 1080, 1920

# Цвета в ASS задаются как &HBBGGRR — порядок каналов обратный привычному.
WHITE = "&H00FFFFFF"
ACCENT = "&H0033E5FF"  # тёплый жёлтый для активного слова
BLACK = "&H00000000"

WORDS_PER_LINE = 3

HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Arial,74,{WHITE},{WHITE},{BLACK},{BLACK},-1,0,0,0,100,100,0,0,1,6,3,2,60,60,660,204
Style: Caption,Arial,58,{ACCENT},{ACCENT},{BLACK},{BLACK},-1,0,0,0,100,100,0,0,1,5,2,8,60,60,320,204

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").strip()


def _line(start: float, end: float, style: str, text: str) -> str:
    # Полей ровно девять до текста: Layer, Start, End, Style, Name,
    # MarginL, MarginR, MarginV, Effect. Пропустишь одно — сдвинется колонка
    # и остаток запятых уедет в текст субтитра.
    return f"Dialogue: 0,{_ts(start)},{_ts(end)},{style},,0,0,0,,{text}"


def build_ass(
    scenes: list[tuple[list[Word], float, str]],
    out: Path,
) -> Path:
    """Собрать ASS для всего ролика.

    scenes — список (слова сцены, смещение сцены от начала ролика, надпись).
    Тайминги слов приходят относительно своей сцены, поэтому сдвигаем их.
    """
    events: list[str] = []

    for words, offset, caption in scenes:
        if caption:
            # Надпись висит всю сцену: она усиливает мысль, а не дублирует речь.
            scene_end = offset + (words[-1].end if words else 0)
            events.append(_line(offset, scene_end, "Caption", _escape(caption.upper())))

        for i in range(0, len(words), WORDS_PER_LINE):
            group = words[i:i + WORDS_PER_LINE]
            for j, word in enumerate(group):
                parts = []
                for k, w in enumerate(group):
                    colour = ACCENT if k == j else WHITE
                    parts.append(f"{{\\c{colour}}}{_escape(w.text)}")
                start = offset + word.start
                # Тянем слово до начала следующего, чтобы не было пустых кадров.
                end = offset + (group[j + 1].start if j + 1 < len(group) else word.end)
                if end <= start:
                    end = start + 0.15
                events.append(_line(start, end, "Sub", " ".join(parts)))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HEADER + "\n".join(events) + "\n", encoding="utf-8-sig")
    return out


def filter_path(path: Path) -> str:
    """Путь для фильтра subtitles: прямые слэши и экранированное двоеточие диска."""
    return str(path).replace("\\", "/").replace(":", "\\:")
