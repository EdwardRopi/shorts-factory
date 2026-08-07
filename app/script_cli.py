"""CLI шага 1: тема -> сценарий в консоль.

    python -m app.script_cli "5 фактов о Байкале"
    python -m app.script_cli "Почему коты мурлыкают" --duration 45 --save
    python -m app.script_cli --batch prompts/topics.txt
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app import config
from app.ai.providers import LLMError, get_provider
from app.ai.script import ScriptParams, generate_script
from app.schemas import Script

console = Console()


def show(script: Script, params: ScriptParams, elapsed: float, provider_name: str) -> None:
    console.print()
    console.print(Panel(
        f"[bold]{script.hook}[/bold]",
        title=f"[cyan]{script.title}[/cyan]",
        subtitle=f"хук · {provider_name} · {elapsed:.1f} с",
        border_style="cyan",
    ))

    table = Table(show_lines=False, header_style="bold cyan", expand=True)
    table.add_column("#", width=3, justify="right")
    table.add_column("Озвучка", ratio=5)
    table.add_column("Ключ поиска (EN)", ratio=3, style="green")
    table.add_column("На экране", ratio=2, style="yellow")
    for s in script.scenes:
        table.add_row(str(s.id), s.voiceover, s.search_query_en, s.on_screen_text)
    console.print(table)

    if script.cta:
        console.print(f"[bold]CTA:[/bold] {script.cta}")
    if script.hashtags:
        console.print(f"[dim]{' '.join(script.hashtags)}[/dim]")

    target = params.duration
    est = script.estimated_seconds
    ok = abs(est - target) <= target * 0.25
    mark = "[green]✓[/green]" if ok else "[yellow]![/yellow]"
    console.print(
        f"{mark} сцен: {len(script.scenes)} (просили {params.n_scenes}) · "
        f"слов: {script.word_count} · "
        f"оценка длительности: {est} с при цели {target} с"
    )


def save(script: Script, params: ScriptParams) -> Path:
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = "".join(c if c.isalnum() else "-" for c in params.topic.lower())[:40].strip("-")
    path = config.OUT_DIR / f"{slug}-{int(time.time())}.json"
    path.write_text(script.model_dump_json(indent=2), encoding="utf-8")
    return path


def run_one(topic: str, args, provider) -> Script | None:
    params = ScriptParams(topic=topic, duration=args.duration, language=args.lang)
    started = time.perf_counter()
    try:
        script = generate_script(params, provider=provider, use_cache=not args.fresh)
    except LLMError as e:
        console.print(f"[red]✗ {topic}[/red]\n{e}")
        return None
    elapsed = time.perf_counter() - started

    if args.json:
        print(json.dumps(script.model_dump(), ensure_ascii=False, indent=2))
    else:
        show(script, params, elapsed, provider.name)

    if args.save:
        console.print(f"[dim]сохранено: {save(script, params)}[/dim]")
    return script


def main() -> int:
    p = argparse.ArgumentParser(description="Генератор сценариев для Reels и Shorts")
    p.add_argument("topic", nargs="?", help="тема ролика")
    p.add_argument("--duration", type=int, default=30, help="длительность в секундах (по умолчанию 30)")
    p.add_argument("--lang", default="русский", help="язык озвучки")
    p.add_argument("--provider", default=None, help="ollama или mistral")
    p.add_argument("--model", default=None, help="имя модели, например mistral или qwen2.5:7b")
    p.add_argument("--batch", type=Path, help="файл со списком тем, по одной в строке")
    p.add_argument("--save", action="store_true", help="сохранить JSON в out/")
    p.add_argument("--fresh", action="store_true", help="не брать сценарий из кэша")
    p.add_argument("--json", action="store_true", help="печатать сырой JSON вместо таблицы")
    args = p.parse_args()

    if not args.topic and not args.batch:
        p.error("укажите тему или --batch с файлом тем")

    try:
        provider = get_provider(args.provider, args.model)
    except LLMError as e:
        console.print(f"[red]{e}[/red]")
        return 1

    topics = [args.topic] if args.topic else [
        line.strip() for line in args.batch.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

    ok = 0
    started = time.perf_counter()
    for i, topic in enumerate(topics, 1):
        if len(topics) > 1:
            console.rule(f"[bold]{i}/{len(topics)}[/bold] {topic}")
        if run_one(topic, args, provider):
            ok += 1

    if len(topics) > 1:
        total = time.perf_counter() - started
        console.print()
        console.print(
            f"[bold]Итог:[/bold] {ok} из {len(topics)} тем прошли валидацию · "
            f"{total:.0f} с всего, {total / len(topics):.0f} с на тему"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
