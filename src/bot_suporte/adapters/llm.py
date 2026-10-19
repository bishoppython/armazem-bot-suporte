"""Clientes de LLM. Qualquer servidor compatível com a API da OpenAI serve."""

import re
from typing import Any, Protocol

import httpx

from bot_suporte.domain.modelos import Uso

_PENSAMENTO = re.compile(r"<think>.*?</think>", re.S)


class LLM(Protocol):
    def conversar(self, mensagens: list[dict[str, str]]) -> tuple[str, Uso]: ...


class Embedder(Protocol):
    def embutir(self, textos: list[str]) -> list[list[float]]: ...


class ClienteOpenAICompat:
    def __init__(self, base_url: str, api_key: str, modelo: str, timeout: float = 120) -> None:
        self.modelo = modelo
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def conversar(self, mensagens: list[dict[str, str]]) -> tuple[str, Uso]:
        corpo: dict[str, Any] = {
            "model": self.modelo,
            "messages": mensagens,
            "temperature": 0.2,
            # Modelos com raciocínio (Qwen3, Gemma) respondem bem mais rápido sem ele.
            "reasoning_effort": "none",
        }
        r = self._http.post("/chat/completions", json=corpo)
        r.raise_for_status()
        dados = r.json()
        texto = _PENSAMENTO.sub("", dados["choices"][0]["message"]["content"] or "").strip()
        uso = dados.get("usage") or {}
        return texto, Uso(uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0))

    def embutir(self, textos: list[str]) -> list[list[float]]:
        r = self._http.post("/embeddings", json={"model": self.modelo, "input": textos})
        r.raise_for_status()
        return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
