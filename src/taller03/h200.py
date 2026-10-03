"""Cliente OpenAI-compatible para el LLM y embeddings alojados en la H200."""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from typing import Any


class H200:
    """Cliente sin API key para los endpoints vLLM y embeddings de la H200.

    El servidor usa ``Bearer local`` como valor de compatibilidad, no como una
    credencial. La conectividad normalmente requiere GlobalProtect.
    """

    HOST = os.environ.get("H200_HOST", "172.28.230.10")
    LLM = int(os.environ.get("H200_LLM_PORT", "12555"))
    EMB = int(os.environ.get("H200_EMB_PORT", "11434"))

    def __init__(self, timeout: float = 180, host: str | None = None,
                 llm_port: int | None = None, embedding_port: int | None = None):
        self.host = host or self.HOST
        self.llm_port = llm_port or self.LLM
        self.embedding_port = embedding_port or self.EMB
        self.timeout = timeout
        self.modelo = self._get(self.llm_port, "v1/models")["data"][0]["id"]
        modelos_emb = self._get(self.embedding_port, "v1/models")["data"]
        ids = [modelo["id"] for modelo in modelos_emb]
        prefix = os.environ.get("H200_EMBEDDING_PREFIX", "bge-m3")
        self.modelo_emb = next((modelo for modelo in ids if modelo.startswith(prefix)), None)
        if self.modelo_emb is None:
            raise RuntimeError(f"No se encontró un modelo de embeddings con prefijo {prefix!r}: {ids}")

    def _pedir(self, puerto: int, ruta: str, cuerpo: dict[str, Any] | None = None,
               timeout: float | None = None) -> dict[str, Any]:
        request = urllib.request.Request(
            f"http://{self.host}:{puerto}/{ruta}",
            data=None if cuerpo is None else json.dumps(cuerpo).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            detail = error.read(500).decode("utf-8", errors="replace")
            raise RuntimeError(f"La H200 respondió HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", error)
            raise RuntimeError(
                f"Sin respuesta de {self.host}:{puerto} ({reason}). ¿Está GlobalProtect conectada?"
            ) from error
        except TimeoutError as error:
            raise RuntimeError(f"Tiempo agotado al consultar {self.host}:{puerto}") from error

    def _get(self, puerto: int, ruta: str) -> dict[str, Any]:
        return self._pedir(puerto, ruta, timeout=8)

    def chat(self, mensajes: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
             json_mode: bool = False, max_tokens: int = 4096) -> dict[str, Any]:
        """Envía una conversación y devuelve respuesta, tools, uso y latencia."""
        body: dict[str, Any] = {
            "model": self.modelo,
            "messages": mensajes,
            "temperature": 0,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": True},
        }
        if tools:
            body["tools"] = tools
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        response = self._pedir(self.llm_port, "v1/chat/completions", body)
        choice = response["choices"][0]
        message = choice["message"]
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []
        reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
        return {
            "mensaje": message,
            "contenido": content,
            "tool_calls": tool_calls,
            "razonamiento": reasoning,
            "fin": choice.get("finish_reason"),
            "uso": response.get("usage", {}),
            "latencia_s": round(time.perf_counter() - started, 2),
        }

    def embeddings(self, textos: str | list[str]) -> list[list[float]]:
        """Calcula embeddings normalizados para un texto o una lista de textos."""
        entradas = [textos] if isinstance(textos, str) else textos
        response = self._pedir(
            self.embedding_port,
            "v1/embeddings",
            {"model": self.modelo_emb, "input": entradas},
        )
        vectors = [
            item["embedding"]
            for item in sorted(response["data"], key=lambda item: item["index"])
        ]
        return [self._normalize(vector) for vector in vectors]

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


__all__ = ["H200"]