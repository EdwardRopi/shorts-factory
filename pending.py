"""Какие темы списка ещё не собраны.

Считать готовые файлы нельзя: после перезапуска тема может собраться второй
раз, и счётчик покажет полный комплект там, где половины списка нет. Сверяем
именно темы — по тому же slug, каким назван файл ролика.

    python pending.py prompts/space.txt "out/videos/факты про космос"

Печатает число оставшихся тем и складывает их в файл рядом со списком,
чтобы batch.py собрал ровно их.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from app import config
from app.render import slugify

# Темы, на которых сборка стабильно глохнет. Иначе сторож будет вечно биться
# в одну и ту же вместо того, чтобы доделать остальные.
FAILED_SUFFIX = ".failed.txt"


def read_topics(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def made_slugs(folder: Path) -> set[str]:
    if not folder.exists():
        return set()
    return {re.sub(r"-\d+$", "", p.stem) for p in folder.glob("*.mp4")}


def main() -> int:
    if len(sys.argv) < 3:
        sys.exit("нужно: pending.py <список тем> <папка роликов>")

    prompts = Path(sys.argv[1])
    if not prompts.is_absolute():
        prompts = config.ROOT / prompts
    folder = Path(sys.argv[2])
    if not folder.is_absolute():
        folder = config.ROOT / folder

    done = made_slugs(folder)
    failed_file = prompts.with_suffix(FAILED_SUFFIX)
    failed = set(read_topics(failed_file)) if failed_file.exists() else set()

    left = [t for t in read_topics(prompts)
            if slugify(t) not in done and t not in failed]

    out = prompts.with_suffix(".pending.txt")
    out.write_text("\n".join(left) + ("\n" if left else ""), encoding="utf-8")

    print(len(left))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
