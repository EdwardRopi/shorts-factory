"""Оркестратор: тема -> сценарий -> озвучка -> тайминги -> клипы.

Порядок принципиален. Сначала синтезируем речь и меряем её реальную
длительность, и только потом ищем видео под получившийся хронометраж.
Обратный порядок гарантирует рассинхрон голоса и картинки.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.ai.script import ScriptParams, generate_script
from app.ai.tts import TTSProvider, get_tts
from app.schemas import Scene, Script
from app.stock.base import Clip
from app.stock.finder import ClipFinder

# Пауза после реплики, чтобы сцены не склеивались встык.
SCENE_PAD = 0.3


@dataclass
class ScenePlan:
    scene: Scene
    audio: Path
    audio_seconds: float
    clip: Clip | None = None
    query_used: str = ""

    @property
    def duration(self) -> float:
        """Длительность сцены в готовом ролике."""
        return round(self.audio_seconds + SCENE_PAD, 3)


@dataclass
class VideoPlan:
    script: Script
    scenes: list[ScenePlan] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_seconds(self) -> float:
        return round(sum(s.duration for s in self.scenes), 2)

    @property
    def missing_clips(self) -> int:
        return sum(1 for s in self.scenes if s.clip is None)


def build_plan(
    params: ScriptParams,
    tts: TTSProvider | None = None,
    finder: ClipFinder | None = None,
    on_step=None,
    use_cache: bool = True,
) -> VideoPlan:
    tts = tts or get_tts()
    finder = finder or ClipFinder()

    def step(msg: str) -> None:
        if on_step:
            on_step(msg)

    step("генерирую сценарий")
    script = generate_script(params, use_cache=use_cache)
    plan = VideoPlan(script=script)

    step(f"озвучиваю {len(script.scenes)} сцен ({tts.name})")
    for scene in script.scenes:
        path, seconds = tts.say(scene.voiceover)
        plan.scenes.append(ScenePlan(scene=scene, audio=path, audio_seconds=seconds))

    step("подбираю клипы под реальные тайминги")
    used: set[str] = set()
    for sp in plan.scenes:
        clips, query = finder.search_with_fallback(sp.scene.search_query_en, sp.duration)
        sp.query_used = query
        # Один и тот же клип дважды в ролике сразу выдаёт автоматическую сборку.
        for c in clips:
            if c.key not in used:
                used.add(c.key)
                sp.clip = c
                break
        if sp.clip is None:
            plan.warnings.append(
                f"сцена {sp.scene.id}: не нашлось клипа по «{sp.scene.search_query_en}»"
            )

    plan.warnings.extend(finder.errors)
    return plan
