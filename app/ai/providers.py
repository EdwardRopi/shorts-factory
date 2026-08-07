"""Абстракция над LLM.

Локально работаем через Ollama бесплатно, на проде — через API Mistral.
Смена провайдера — это переменная LLM_PROVIDER в .env, а не правка кода.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

import httpx

from app import config


class LLMError(RuntimeError):
    pass


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        """Вернуть распарсенный JSON-ответ модели. Схема задаёт форму ответа."""


class OllamaProvider(LLMProvider):
    """Локальная модель. Ollama умеет структурированный вывод по JSON-схеме."""

    def __init__(self, host: str | None = None, model: str | None = None):
        self.host = (host or config.OLLAMA_HOST).rstrip("/")
        self.model = model or config.OLLAMA_MODEL
        self.name = f"ollama:{self.model}"

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0.85, "top_p": 0.9, "num_ctx": 8192},
        }
        try:
            # trust_env=False обязателен: в системе Windows прописан прокси, который
            # перехватывает даже localhost и отвечает 503, не доходя до Ollama.
            with httpx.Client(trust_env=False, timeout=600) as client:
                r = client.post(f"{self.host}/api/chat", json=payload)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError(f"Ollama недоступна ({self.host}): {e}") from e

        content = r.json().get("message", {}).get("content", "")
        return _loads(content)


class MistralProvider(LLMProvider):
    """Облачный Mistral. Понадобится на проде — локально 7B думает слишком долго."""

    URL = "https://api.mistral.ai/v1/chat/completions"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or config.MISTRAL_API_KEY
        self.model = model or config.MISTRAL_MODEL
        self.name = f"mistral:{self.model}"
        if not self.api_key:
            raise LLMError("MISTRAL_API_KEY не задан в .env")

    def complete_json(self, system: str, user: str, schema: dict) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.8,
        }
        try:
            r = httpx.post(
                self.URL,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=180,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise LLMError(f"Mistral API: {e}") from e

        return _loads(r.json()["choices"][0]["message"]["content"])


def _loads(content: str) -> dict:
    """Снять возможные markdown-заборы и распарсить JSON."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        raise LLMError(f"Модель вернула не JSON: {e}\n---\n{content[:600]}") from e


def get_provider(name: str | None = None, model: str | None = None) -> LLMProvider:
    name = (name or config.LLM_PROVIDER).lower()
    if name == "ollama":
        return OllamaProvider(model=model)
    if name == "mistral":
        return MistralProvider(model=model)
    raise LLMError(f"Неизвестный провайдер: {name}")
