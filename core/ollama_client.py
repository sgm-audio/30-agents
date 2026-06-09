"""
Ollama client wrapper with health-check, retry, and model management.
"""
import asyncio
import time
from typing import Any, AsyncIterator, Optional

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import settings

log = structlog.get_logger(__name__)


class OllamaClient:
    """Thin async wrapper around the Ollama HTTP API."""

    def __init__(self, host: Optional[str] = None):
        self.host = host or settings.ollama_host
        self._client = httpx.AsyncClient(base_url=self.host, timeout=settings.ollama_timeout)

    async def health(self) -> bool:
        """Return True if Ollama is reachable."""
        try:
            r = await self._client.get("/")
            return r.status_code == 200
        except Exception as e:
            log.debug("ollama.health.error", error=str(e))
            return False

    async def wait_ready(self, max_wait: int = 60) -> bool:
        """Block until Ollama is ready or timeout."""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            if await self.health():
                log.info("ollama.ready")
                return True
            await asyncio.sleep(2)
        log.error("ollama.timeout", max_wait=max_wait)
        return False

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ConnectError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def list_models(self) -> list[str]:
        r = await self._client.get("/api/tags")
        r.raise_for_status()
        data = r.json()
        return [m["name"] for m in data.get("models", [])]

    async def model_exists(self, model: str) -> bool:
        models = await self.list_models()
        # normalize: "gemma3:4b" matches "gemma3:4b" exactly or prefix
        return any(m == model or m.startswith(model.split(":")[0]) for m in models)

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ConnectError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        stream: bool = False,
        options: Optional[dict] = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            "options": options or {},
        }
        if system:
            payload["system"] = system

        r = await self._client.post("/api/generate", json=payload)
        r.raise_for_status()
        return r.json().get("response", "")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ConnectError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def chat(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        options: Optional[dict] = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": options or {},
        }
        r = await self._client.post("/api/chat", json=payload)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ConnectError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def embed(self, model: str, text: str) -> list[float]:
        payload = {"model": model, "input": text}
        r = await self._client.post("/api/embed", json=payload)
        r.raise_for_status()
        data = r.json()
        # newer Ollama returns {"embeddings": [[...]]}
        embeddings = data.get("embeddings", data.get("embedding", []))
        if not embeddings:
            raise ValueError("Empty embedding response from Ollama")
        if isinstance(embeddings[0], list):
            return embeddings[0]
        return embeddings

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()


# Module-level singleton
# NOTE: same async single-threaded race as get_graph(); acceptable here
_ollama: Optional[OllamaClient] = None


def get_ollama() -> OllamaClient:
    global _ollama
    if _ollama is None:
        _ollama = OllamaClient()
    return _ollama
