"""Список доступных моделей Mistral: python -m app.models_cli

ID моделей и цены меняются — сверяться стоит с живым ответом API,
а не с документацией недельной давности.
"""

import httpx

from app import config

r = httpx.get(
    "https://api.mistral.ai/v1/models",
    headers={"Authorization": f"Bearer {config.MISTRAL_API_KEY}"},
    timeout=30,
)
if r.status_code != 200:
    print(f"HTTP {r.status_code}: {r.text[:300]}")
    raise SystemExit(1)

ids = sorted(m["id"] for m in r.json().get("data", []))
chat = [i for i in ids if not any(x in i for x in ("embed", "ocr", "moderation", "voxtral", "tts"))]
print(f"всего моделей: {len(ids)}\n")
print("для чата:")
for i in chat:
    print(" ", i)
print("\nостальные:")
for i in ids:
    if i not in chat:
        print(" ", i)
