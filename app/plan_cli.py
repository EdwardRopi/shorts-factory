"""Полный конвейер до монтажа:

    python -m app.plan_cli "Почему коты мурлыкают"
    python -m app.plan_cli "3 ошибки новичка в спортзале" --duration 45 --tts sapi
"""

from __future__ import annotations

import argparse
import sys
import time

from rich.console import Console
from rich.table import Table

from app.ai.script import ScriptParams
from app.ai.tts import TTSError, get_tts
from app.pipeline import VideoPlan, build_plan

console = Console()


def show(plan: VideoPlan, target: int) -> None:
    console.print()
    console.print(f"[bold cyan]{plan.script.title}[/bold cyan]")
    console.print(f"[bold]{plan.script.hook}[/bold]\n")

    table = Table(header_style="bold cyan", expand=True)
    table.add_column("#", width=3, justify="right")
    table.add_column("Озвучка", ratio=4)
    table.add_column("Длит.", width=7, justify="right")
    table.add_column("Клип", ratio=3, style="green")
    table.add_column("Сток", width=8)

    for sp in plan.scenes:
        if sp.clip:
            clip_cell = f"{sp.clip.width}×{sp.clip.height} · {sp.clip.duration:.0f} с · {sp.clip.author}"
            provider = sp.clip.provider
        else:
            clip_cell, provider = "[red]не найден[/red]", "—"
        table.add_row(
            str(sp.scene.id),
            sp.scene.voiceover,
            f"{sp.duration:.1f} с",
            clip_cell,
            provider,
        )
    console.print(table)

    total = plan.total_seconds
    delta = total - target
    mark = "[green]✓[/green]" if abs(delta) <= target * 0.25 else "[yellow]![/yellow]"
    console.print(
        f"{mark} хронометраж по реальной озвучке: [bold]{total} с[/bold] "
        f"при цели {target} с ({delta:+.1f} с) · клипов не найдено: {plan.missing_clips}"
    )
    for w in plan.warnings:
        console.print(f"[yellow]· {w}[/yellow]")


def main() -> int:
    p = argparse.ArgumentParser(description="Сценарий + озвучка + подбор клипов")
    p.add_argument("topic")
    p.add_argument("--duration", type=int, default=30)
    p.add_argument("--lang", default="русский")
    p.add_argument("--tts", default=None, help="silero или sapi")
    p.add_argument("--voice", default=None)
    args = p.parse_args()

    params = ScriptParams(topic=args.topic, duration=args.duration, language=args.lang)
    started = time.perf_counter()

    try:
        tts = get_tts(args.tts, args.voice)
    except TTSError as e:
        console.print(f"[red]{e}[/red]")
        return 1

    with console.status("[cyan]работаю…") as status:
        plan = build_plan(params, tts=tts, on_step=lambda m: status.update(f"[cyan]{m}…"))

    show(plan, args.duration)
    console.print(f"[dim]весь конвейер занял {time.perf_counter() - started:.0f} с[/dim]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
