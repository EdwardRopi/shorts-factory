"""Проверка подбора клипов:

    python -m app.stock_cli "aerial view deep blue lake"
    python -m app.stock_cli "hands typing laptop night" --seconds 6
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.table import Table

from app.stock.base import Clip
from app.stock.finder import ClipFinder

console = Console()


def show(query: str, clips: list[Clip], need: float) -> None:
    if not clips:
        console.print(f"[yellow]по запросу «{query}» подходящих клипов нет[/yellow]")
        return

    table = Table(title=f"«{query}» · нужно {need} с", header_style="bold cyan", expand=True)
    table.add_column("Оценка", width=6, justify="right")
    table.add_column("Сток", width=8)
    table.add_column("Формат", width=11)
    table.add_column("Размер", width=11)
    table.add_column("Длит.", width=6, justify="right")
    table.add_column("Автор", ratio=2)
    table.add_column("Файл", ratio=4, style="dim")

    for c in clips[:8]:
        table.add_row(
            f"{c.score(need):.1f}",
            c.provider,
            "вертикаль" if c.is_portrait else "горизонт",
            f"{c.width}×{c.height}",
            f"{c.duration:.0f} с",
            c.author,
            c.file_url.split("?")[0][-46:],
        )
    console.print(table)

    by_provider = {}
    for c in clips:
        by_provider[c.provider] = by_provider.get(c.provider, 0) + 1
    breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(by_provider.items()))
    console.print(f"[green]подходящих: {len(clips)}[/green] ({breakdown})  ·  показаны лучшие 8")


def main() -> int:
    p = argparse.ArgumentParser(description="Подбор стоковых клипов под сцену")
    p.add_argument("query", help="английский поисковый запрос")
    p.add_argument("--seconds", type=float, default=5.0, help="сколько секунд нужно под сцену")
    p.add_argument("--limit", type=int, default=15, help="сколько кандидатов запросить")
    args = p.parse_args()

    finder = ClipFinder()
    if not finder.providers:
        console.print("[red]нет ни одного ключа стока в .env[/red]")
        return 1

    clips, used_query = finder.search_with_fallback(args.query, args.seconds)
    for err in finder.errors:
        console.print(f"[yellow]{err}[/yellow]")
    if used_query != args.query:
        console.print(f"[yellow]полный ключ ничего не дал, сработал сокращённый: «{used_query}»[/yellow]")

    show(used_query, clips, args.seconds)
    return 0 if clips else 1


if __name__ == "__main__":
    sys.exit(main())
