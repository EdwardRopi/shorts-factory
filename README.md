# shorts-factory

Генератор коротких вертикальных видео (Reels / YouTube Shorts): тема на входе — готовый ролик 1080×1920 на выходе.

Полный план разработки — в PDF на рабочем столе: «План разработки Reels и Shorts — кратко, 10 страниц».

## Где мы сейчас

| Шаг | Что | Статус |
|---|---|---|
| 1 | Генератор сценариев (LLM → строгий JSON) | **готово** |
| 2 | Поиск клипов (Pexels + Pixabay, кэш 24 ч) | **готово**, нет загрузчика файлов |
| 3 | Озвучка и тайминги | **готово** на SAPI, Silero ждёт torch |
| — | Конвейер: тема → сценарий → голос → клипы | **готово** |
| 4 | Сборка ролика на FFmpeg | **готово** |
| 5 | Субтитры и музыка | **готово**, музыку нужно положить в `assets/music` |
| — | Живой голос вместо SAPI | дальше |
| 6 | Веб-приложение | |
| 7 | Продакшн | |

## Что выяснилось на практике

- **У Voxtral TTS нет русского.** Все 10 голосов — `en_us` и `en_gb`. Проверено
  обратной транскрибацией: «Байкал содержит двадцать процентов…» вернулось как
  «Bichel Santa Hit 2000% of other Presendo Vote Planete». Для русского используем
  локальные движки, Voxtral останется для англоязычных роликов.
- **Реальный темп речи — 1,7 слова в секунду** (SAPI Irina), а не 2,2–2,4.
  Отсюда ориентир по словам для модели.
- **В системе прописан прокси**, перехватывающий localhost. Все локальные
  HTTP-клиенты создаются с `trust_env=False`, иначе Ollama отвечает 503.

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Нужна запущенная Ollama и скачанная модель:

```powershell
ollama pull mistral
```

## Использование

```powershell
# один сценарий
.\.venv\Scripts\python.exe -m app.script_cli "5 фактов о Байкале"

# другая длительность, сохранить JSON в out/
.\.venv\Scripts\python.exe -m app.script_cli "Почему коты мурлыкают" --duration 45 --save

# прогнать 10 тестовых тем и посмотреть хуки глазами
.\.venv\Scripts\python.exe -m app.script_cli --batch prompts/topics.txt

# готовый ролик одной командой
.\.venv\Scripts\python.exe -m app.render_cli "Почему коты мурлыкают"
.\.venv\Scripts\python.exe -m app.render_cli "Тема" --duration 45 --no-music

# план без монтажа: сценарий + озвучка + подобранные клипы
.\.venv\Scripts\python.exe -m app.plan_cli "Почему коты мурлыкают"

# только подбор клипов по готовому ключу
.\.venv\Scripts\python.exe -m app.stock_cli "cat purring close up" --seconds 5

# какие модели доступны по ключу Mistral
.\.venv\Scripts\python.exe -m app.models_cli

# сравнить модели
.\.venv\Scripts\python.exe -m app.script_cli "Самое дорогое вещество в мире" --model qwen2.5:3b
```

## Устройство

```
app/
  schemas.py          контракт сценария: Script и Scene на Pydantic
  config.py           настройки из .env
  ai/providers.py     абстракция LLM: OllamaProvider и MistralProvider
  ai/script.py        сборка промпта, генерация, ретраи с показом ошибки модели
  script_cli.py       CLI и вывод в консоль
prompts/
  script_ru.txt       системный промпт — правится чаще всего
  topics.txt          10 тестовых тем
out/                  сохранённые сценарии (в git не попадают)
```

Локальная модель — только для отладки: 7B без GPU думает десятки секунд.
На проде переключаемся на API одной строкой в `.env`:

```
LLM_PROVIDER=mistral
MISTRAL_API_KEY=...
```

## Правила проекта

- Ключи только в `.env`, он в `.gitignore`. В репозиторий не попадает ни один токен.
- Промпт живёт в отдельном файле, а не в коде: его правят чаще всего остального.
- Любой внешний сервис прячется за своим интерфейсом, чтобы смена вендора была правкой одной строки.
