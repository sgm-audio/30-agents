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
            r = await self._client.get("/", timeout=5.0)
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

    async def _ensure_reachable(self) -> None:
        """Fast-fail when Ollama is down instead of retrying ~60s per call."""
        if not await self.health():
            raise RuntimeError(f"Ollama unreachable at {self.host}")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ConnectError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def list_models(self) -> list[str]:
        await self._ensure_reachable()
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

        await self._ensure_reachable()
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
        await self._ensure_reachable()
        r = await self._client.post("/api/chat", json=payload)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "")

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ConnectError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def embed(self, model: str, text: str) -> list[float]:
        await self._ensure_reachable()
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


class NimClient:
    """OpenAI-compatible client for NVIDIA NIM (integrate.api.nvidia.com/v1)."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = base_url or settings.nim_base_url
        self.api_key = api_key or settings.nim_api_key
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=settings.ollama_timeout)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def health(self) -> bool:
        try:
            r = await self._client.get("/models", headers=self._headers(), timeout=10.0)
            return r.status_code == 200
        except Exception:
            return False

    async def wait_ready(self, max_wait: int = 60) -> bool:
        deadline = time.time() + max_wait
        while time.time() < deadline:
            if await self.health():
                return True
            await asyncio.sleep(2)
        return False

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ConnectError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def list_models(self) -> list[str]:
        r = await self._client.get("/models", headers=self._headers())
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]

    async def model_exists(self, model: str) -> bool:
        models = await self.list_models()
        return model in models

    @staticmethod
    def _to_openai_messages(messages: list[dict]) -> list[dict]:
        """Translate Ollama-style messages (incl. `images` field) to OpenAI format."""
        out = []
        for m in messages:
            content = m.get("content", "")
            images = m.get("images") or []
            if images:
                parts = [{"type": "text", "text": content}]
                for b64 in images:
                    parts.append(
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                    )
                out.append({"role": m.get("role", "user"), "content": parts})
            else:
                out.append({"role": m.get("role", "user"), "content": content})
        return out

    def _options(self, options: Optional[dict]) -> dict:
        opts = {}
        if options:
            for k in ("temperature", "top_p", "max_tokens", "seed", "stop"):
                if options.get(k) is not None:
                    opts[k] = options[k]
        return opts

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ConnectError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def _chat_completion(
        self, model: str, messages: list[dict], options: Optional[dict] = None
    ) -> str:
        payload = {"model": model, "messages": self._to_openai_messages(messages), "stream": False}
        payload.update(self._options(options))
        r = await self._client.post("/chat/completions", json=payload, headers=self._headers())
        r.raise_for_status()
        d = r.json()
        msg = d.get("choices", [{}])[0].get("message", {})
        return msg.get("content") or ""

    async def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        stream: bool = False,
        options: Optional[dict] = None,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self._chat_completion(model, messages, options)

    async def chat(
        self, model: str, messages: list[dict], stream: bool = False, options: Optional[dict] = None
    ) -> str:
        return await self._chat_completion(model, messages, options)

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.ConnectError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
    )
    async def embed(self, model: str, text: str) -> list[float]:
        r = await self._client.post(
            "/embeddings", json={"model": model, "input": [text]}, headers=self._headers()
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            raise ValueError("Empty embedding response from NIM")
        return data[0].get("embedding", [])

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()


# Module-level singleton
# NOTE: same async single-threaded race as get_graph(); acceptable here
_llm: Optional[object] = None


def get_ollama():
    """Return the configured LLM client: NimClient when llm_backend == 'nim', else OllamaClient."""
    global _llm
    if _llm is None:
        _llm = NimClient() if settings.llm_backend == "nim" else OllamaClient()
    return _llm
