"""Монтаж сцены: нарезка на планы, триптих и наезд камеры.

Раньше сцена была одним клипом, растянутым на все свои 5-6 секунд, и за
30-секундный ролик зритель видел пять неподвижных картинок. Здесь сцена
собирается из нескольких планов разной природы, а кадр всё время едет.

Длительность сцены задаёт озвучка и менять её нельзя: сумма планов всегда
равна ей ровно, иначе поедет синхрон с голосом.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from app import config
from app.video.ffmpeg import probe_duration, run

SCENE_CACHE = config.ROOT / "cache" / "scenes"

WIDTH, HEIGHT, FPS = 1080, 1920, 30
BANDS = 3
BAND_H = HEIGHT // BANDS  # 640: горизонтальный клип 16:9 по ширине 1080 даёт 608,
                          # то есть в полосу попадает почти целый кадр, а не обрезок

# Целевая длина плана. Меньше двух секунд — рябит, больше трёх — засыпаешь.
SHOT_TARGET = 2.4
MIN_SHOTS, MAX_SHOTS = 2, 4

# Триптих держим коротким: это акцент, а не режим просмотра.
TRIPTYCH_MAX = 2.2

# Наезд: план начинается крупнее и за четверть секунды садится в кадр,
# потом медленно подъезжает до конца плана.
PUNCH_FROM, PUNCH_FRAMES, DRIFT_TO = 1.12, 7, 1.05

# Версия схемы монтажа. Входит в ключ кэша: без неё правки фильтров не видны,
# потому что сцены берутся из cache/scenes от прошлых прогонов.
SCHEME = "v2-montage"


@dataclass
class Shot:
    """Один план внутри сцены."""

    kind: str  # "single" | "triptych"
    duration: float
    sources: list[int] = field(default_factory=list)  # индексы в списке источников
    offsets: list[float] = field(default_factory=list)  # откуда брать внутри клипа

    @property
    def token(self) -> str:
        srcs = ",".join(f"{s}@{o:.1f}" for s, o in zip(self.sources, self.offsets))
        return f"{self.kind}:{self.duration:.3f}:{srcs}"


def plan_shots(duration: float, n_sources: int, triptych: bool = False) -> list[Shot]:
    """Разложить сцену на планы.

    Планы равной длины: рваный ритм внутри сцены выглядит сбоем, а не приёмом.
    Источники раздаются по кругу, чтобы соседние планы не были одним и тем же
    клипом, когда есть из чего выбирать.
    """
    if duration <= 0:
        raise ValueError("длительность сцены должна быть больше нуля")
    n_sources = max(1, n_sources)

    count = max(MIN_SHOTS, min(MAX_SHOTS, round(duration / SHOT_TARGET)))
    triptych = triptych and n_sources >= BANDS

    shots: list[Shot] = []
    if triptych:
        # Триптих откусывает свой кусок с начала, остальное делят обычные планы.
        head = min(TRIPTYCH_MAX, duration / 2)
        shots.append(Shot("triptych", round(head, 3), list(range(BANDS)), [0.0] * BANDS))
        duration -= head
        count = max(1, count - 1)

    each = duration / count
    for i in range(count):
        # Последний план добирает остаток, чтобы сумма сошлась в точности.
        d = round(duration - each * i, 3) if i == count - 1 else round(each, 3)
        shots.append(Shot("single", d, [i % n_sources], [0.0]))

    _spread_offsets(shots)
    return shots


def _spread_offsets(shots: list[Shot]) -> None:
    """Повторно взятому клипу сдвигаем точку входа.

    Один и тот же кусок дважды в ролике читается как склейка по ошибке.
    """
    seen: dict[int, int] = {}
    for shot in shots:
        for i, src in enumerate(shot.sources):
            times = seen.get(src, 0)
            shot.offsets[i] = round(times * (SHOT_TARGET + 0.6), 3)
            seen[src] = times + 1


def pick_triptych_scene(n_scenes: int) -> int:
    """В каком месте ролика ставить триптих.

    Один раз за ролик и ближе к середине: в начале он спорит с хуком, в конце —
    с выводом.
    """
    return max(0, n_scenes // 2)


def build_scene(sources: list[Path], duration: float, shots: list[Shot]) -> Path:
    """Собрать видеоряд сцены ровно на duration секунд, без звука."""
    if not sources:
        raise ValueError("нет ни одного клипа для сцены")

    key = "|".join([SCHEME, f"{duration:.3f}", *map(str, sources),
                    *(s.token for s in shots)])
    out = SCENE_CACHE / f"scene-{hashlib.sha256(key.encode()).hexdigest()[:24]}.mp4"
    SCENE_CACHE.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 0:
        return out

    limits = {p: probe_duration(p) for p in set(sources)}

    args: list[str] = []
    steps: list[str] = []
    labels: list[str] = []
    idx = 0

    for n, shot in enumerate(shots):
        parts = []
        for src_i, offset in zip(shot.sources, shot.offsets):
            src = sources[min(src_i, len(sources) - 1)]
            # Сдвиг за пределы клипа оставил бы план без единого кадра.
            room = max(0.0, limits[src] - shot.duration - 0.2)
            start = min(offset, room)
            args += ["-stream_loop", "-1", "-ss", f"{start:.3f}",
                     "-t", f"{shot.duration:.3f}", "-i", str(src)]
            parts.append(idx)
            idx += 1

        if shot.kind == "triptych":
            for band, stream in enumerate(parts):
                steps.append(
                    f"[{stream}:v]{_fill(WIDTH, BAND_H)},setpts=PTS-STARTPTS[b{n}_{band}]"
                )
            stack = "".join(f"[b{n}_{band}]" for band in range(len(parts)))
            steps.append(
                f"{stack}vstack=inputs={len(parts)},"
                # Тонкие тёмные щели между полосами: так деление читается как
                # приём, а не как склеенные встык случайные кадры.
                f"drawbox=y={BAND_H - 2}:w={WIDTH}:h=4:color=black@0.8:t=fill,"
                f"drawbox=y={2 * BAND_H - 2}:w={WIDTH}:h=4:color=black@0.8:t=fill[v{n}]"
            )
        else:
            steps.append(
                f"[{parts[0]}:v]{_fill(WIDTH, HEIGHT)},{_punch(shot.duration)},"
                f"setpts=PTS-STARTPTS[v{n}]"
            )
        labels.append(f"[v{n}]")

    steps.append(f"{''.join(labels)}concat=n={len(shots)}:v=1:a=0[vcat]")
    # Доли кадра на стыках планов могут не добрать миллисекунды до нужной длины.
    # Дотягиваем последним кадром и режем ровно по метке — сцена обязана быть
    # той же длины, что и её озвучка.
    steps.append("[vcat]tpad=stop_mode=clone:stop_duration=1,format=yuv420p[vout]")

    run([
        *args,
        "-filter_complex", ";".join(steps),
        "-map", "[vout]", "-an",
        "-t", f"{duration:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-video_track_timescale", "30000",
        str(out),
    ], f"монтаж сцены ({len(shots)} планов)")
    return out


def _fill(w: int, h: int) -> str:
    """Заполнить кадр w×h без полей и без искажения пропорций."""
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},fps={FPS}")


def _punch(duration: float) -> str:
    """Наезд камеры: рывок в начале плана и медленный подъезд дальше."""
    total = max(PUNCH_FRAMES + 1, round(duration * FPS))
    tail = total - PUNCH_FRAMES
    z = (f"if(lt(on\\,{PUNCH_FRAMES})\\,"
         f"{PUNCH_FROM}-{PUNCH_FROM - 1:.3f}*on/{PUNCH_FRAMES}\\,"
         f"1+{DRIFT_TO - 1:.3f}*(on-{PUNCH_FRAMES})/{tail})")
    return (f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={WIDTH}x{HEIGHT}:fps={FPS}")
