"""Полный цикл до готового MP4:

    python -m app.render_cli "Почему коты мурлыкают"
    python -m app.render_cli "3 ошибки новичка в спортзале" --duration 45
"""

from __future__ import annotations

import argparse
import sys
import time

from rich.console import Console

from app import config
from app.ai.script import ScriptParams
from app.ai.transcribe import words_for
from app.ai.tts import TTSError, get_tts
from app.pipeline import build_plan
from app.plan_cli import show
from app.stock.downloader import DownloadError, download
from app.video.compose import compose
from app.video.ffmpeg import FFmpegError, probe_duration
from app.video.music import credit, pick
from app.video.normalize import normalize_video, pad_audio
from app.video.subtitles import build_ass

console = Console()
VIDEO_DIR = config.OUT_DIR / "videos"


def slugify(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower())[:40].strip("-")


def main() -> int:
    p = argparse.ArgumentParser(description="Тема -> готовый вертикальный ролик")
    p.add_argument("topic")
    p.add_argument("--duration", type=int, default=30)
    p.add_argument("--lang", default="русский")
    p.add_argument("--tts", default=None, help="silero или sapi")
    p.add_argument("--voice", default=None)
    p.add_argument("--no-subs", action="store_true", help="собрать без субтитров")
    p.add_argument("--no-music", action="store_true", help="собрать без музыки")
    p.add_argument("--fresh", action="store_true", help="сгенерировать сценарий заново")
    args = p.parse_args()

    params = ScriptParams(topic=args.topic, duration=args.duration, language=args.lang)
    started = time.perf_counter()

    try:
        tts = get_tts(args.tts, args.voice)
    except TTSError as e:
        console.print(f"[red]{e}[/red]")
        return 1

    with console.status("[cyan]работаю…") as status:
        plan = build_plan(params, tts=tts, use_cache=not args.fresh,
                          on_step=lambda m: status.update(f"[cyan]{m}…"))

        pairs = []
        for sp in plan.scenes:
            if sp.clip is None:
                console.print(f"[red]сцена {sp.scene.id} без клипа — собрать ролик нельзя[/red]")
                return 1
            status.update(f"[cyan]сцена {sp.scene.id}: качаю клип…")
            try:
                src = download(sp.clip)
            except DownloadError as e:
                console.print(f"[red]{e}[/red]")
                return 1

            status.update(f"[cyan]сцена {sp.scene.id}: готовлю кадр…")
            try:
                video = normalize_video(src, sp.duration)
                audio = pad_audio(sp.audio, sp.duration)
            except FFmpegError as e:
                console.print(f"[red]{e}[/red]")
                return 1
            pairs.append((video, audio))

        subs = None
        if not args.no_subs:
            status.update("[cyan]размечаю субтитры по словам…")
            scenes_words = []
            offset = 0.0
            for sp in plan.scenes:
                words = words_for(sp.audio, sp.scene.voiceover)
                scenes_words.append((words, offset, sp.scene.on_screen_text))
                offset += sp.duration
            subs = build_ass(scenes_words, config.ROOT / "cache" / "subs" /
                             f"{slugify(args.topic)}.ass")

        track = None if args.no_music else pick(args.topic)

        status.update("[cyan]собираю ролик…")
        out = VIDEO_DIR / f"{slugify(args.topic)}-{int(time.time())}.mp4"
        try:
            compose(pairs, out, subtitles=subs, music=track,
                    total_seconds=plan.total_seconds)
        except FFmpegError as e:
            console.print(f"[red]{e}[/red]")
            return 1

    show(plan, args.duration)
    size_mb = out.stat().st_size / 1024 / 1024
    console.print()
    console.print(f"[bold green]готово:[/bold green] {out}")
    console.print(
        f"[dim]{probe_duration(out)} с · {size_mb:.1f} МБ · "
        f"весь цикл {time.perf_counter() - started:.0f} с[/dim]"
    )

    authors = {sp.clip.author for sp in plan.scenes if sp.clip and sp.clip.author}
    console.print(f"[dim]Видео: Pexels / Pixabay. Авторы: {', '.join(sorted(authors))}[/dim]")
    if track:
        line = credit(track) or track.stem
        console.print(f"[dim]Музыка: {line}[/dim]")
    console.print(f"[dim]Голос: {tts.name} / {tts.voice}[/dim]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
