"""Сравнение голосов: один файл, где каждый голос представляется сам.

    python -m app.voices_cli
    python -m app.voices_cli --version v4_ru --text "Своя фраза"
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console

from app import config
from app.ai.tts import SileroTTS
from app.video.ffmpeg import run

console = Console()

DEFAULT_TEXT = (
    "Учёные считают, что частота мурчания ускоряет заживление костей. "
    "Именно поэтому кошки восстанавливаются быстрее других животных."
)


def main() -> int:
    p = argparse.ArgumentParser(description="Прослушать все голоса Silero подряд")
    p.add_argument("--version", default=None, help="v5_ru или v4_ru")
    p.add_argument("--text", default=DEFAULT_TEXT)
    args = p.parse_args()

    probe = SileroTTS(version=args.version)
    console.print(f"[cyan]модель {probe.version}, загружаю…[/cyan]")
    names = [s for s in probe.speakers() if s != "random"]
    console.print(f"голоса: {', '.join(names)}")

    parts = []
    for name in names:
        engine = SileroTTS(voice=name, version=args.version)
        # Голос сначала называет себя — иначе в общем файле не разобрать, кто есть кто.
        intro, _ = engine.say(f"Меня зовут {name}.")
        body, seconds = engine.say(args.text)
        parts += [intro, body]
        console.print(f"  {name:9} {seconds:5.2f} с  ({len(args.text.split()) / seconds:.2f} слов/с)")

    out = config.OUT_DIR / f"voices-{probe.version}.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)

    args_ff: list[str] = []
    for part in parts:
        args_ff += ["-i", str(part)]
    streams = "".join(f"[{i}:a]" for i in range(len(parts)))
    run([
        *args_ff,
        "-filter_complex", f"{streams}concat=n={len(parts)}:v=0:a=1[a]",
        "-map", "[a]", "-c:a", "libmp3lame", "-b:a", "192k", str(out),
    ], "склейка образцов")

    console.print(f"\n[bold green]послушай:[/bold green] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
