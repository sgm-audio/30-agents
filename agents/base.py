"""
BaseAgent: every one of the 30 agents inherits from this.

Each agent is an async callable that takes AgentState and returns
a partial AgentState update.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import settings
from core.graph import AgentState
from core.memory import get_memory
from core.ollama_client import get_ollama
from core.redis_client import get_redis

log = structlog.get_logger(__name__)


def extract_json(text: str) -> dict:
    """Extract the first JSON object from text."""
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
    raise ValueError("No JSON object found in text")


class BaseAgent(ABC):
    """
    Abstract base for all agents.

    Subclasses must implement:
      - name: str  (unique agent identifier)
      - description: str
      - system_prompt: str
      - async execute(state) -> dict  (return partial state update)
    """

    name: str = "base_agent"
    description: str = "Base agent"
    # NOTE: Subclasses set model at class level (e.g. `model = settings.model_fast`).
    # This is evaluated once at import time, which is intentional — model selection
    # is a static property of the agent class, not per-instance.
    model: str = ""  # empty → uses settings.model_fast
    system_prompt: str = "You are a helpful AI assistant."

    def __init__(self):
        self._log = structlog.get_logger(self.name)
        self._model = self.model or settings.model_fast

    def error_result(self, message: str) -> dict[str, Any]:
        """Return a consistent error state that routes back to orchestrator."""
        return {"error": message, "result": message, "next_agent": "orchestrator"}

    # ──────────────────────────────────────────
    # Abstract interface
    # ──────────────────────────────────────────
    @abstractmethod
    async def execute(self, state: AgentState) -> dict[str, Any]:
        """Process state, return partial state update dict."""
        ...

    # ──────────────────────────────────────────
    # Callable interface (LangGraph node)
    # ──────────────────────────────────────────
    async def __call__(self, state: AgentState) -> dict[str, Any]:
        task = state.get("task", "")
        if not task or not task.strip():
            return self.error_result(f"Agent '{self.name}' received empty or missing task.")

        start = time.perf_counter()
        self._log.info("agent.start", task=task[:60])

        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(Exception),
                stop=stop_after_attempt(settings.agent_retry_max),
                wait=wait_exponential(multiplier=1, min=2, max=30),
                reraise=True,
            ):
                with attempt:
                    result = await self.execute(state)

        except Exception as exc:
            self._log.error("agent.failed", error=str(exc))
            return {"error": str(exc), "next_agent": "orchestrator"}

        elapsed = time.perf_counter() - start
        self._log.info("agent.done", elapsed=f"{elapsed:.2f}s")

        # Track metrics in Redis
        try:
            redis = get_redis()
            await redis.hset(
                f"agent:metrics:{self.name}",
                {"last_run": time.time(), "last_elapsed": elapsed},
            )
        except Exception as e:
            log.debug("redis.metrics.write_failed", error=str(e))

        return result

    # ──────────────────────────────────────────
    # Convenience helpers
    # ──────────────────────────────────────────
    async def llm(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        options: Optional[dict] = None,
    ) -> str:
        """Single-turn LLM call."""
        ollama = get_ollama()
        return await ollama.generate(
            model=model or self._model,
            prompt=prompt,
            system=system or self.system_prompt,
            options=options,
        )

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        options: Optional[dict] = None,
    ) -> str:
        """Multi-turn chat call."""
        ollama = get_ollama()
        return await ollama.chat(
            model=model or self._model,
            messages=messages,
            options=options,
        )

    async def remember(
        self,
        text: str,
        metadata: Optional[dict] = None,
        namespace: Optional[str] = None,
    ) -> str:
        """Store text in vector memory."""
        mem = get_memory()
        return await mem.store(
            text=text,
            metadata=metadata,
            namespace=namespace or self.name,
        )

    async def recall(
        self,
        query: str,
        n: int = 5,
        namespace: Optional[str] = None,
    ) -> list[dict]:
        """Retrieve relevant memories."""
        mem = get_memory()
        return await mem.search(
            query=query,
            n_results=n,
            namespace=namespace or self.name,
        )

    async def state_set(self, key: str, value: Any, ttl: int = 3600):
        """Persist agent state in Redis."""
        redis = get_redis()
        await redis.set(f"state:{self.name}:{key}", value, ex=ttl)

    async def state_get(self, key: str) -> Optional[Any]:
        """Retrieve agent state from Redis."""
        redis = get_redis()
        return await redis.get(f"state:{self.name}:{key}")

    def build_messages(
        self,
        task: str,
        context: Optional[dict] = None,
        history: Optional[list] = None,
    ) -> list[dict]:
        """Helper to build a messages list for chat()."""
        msgs = [{"role": "system", "content": self.system_prompt}]
        if history:
            msgs.extend(history)
        user_content = task
        if context:
            ctx_str = "\n".join(f"{k}: {v}" for k, v in context.items())
            user_content = f"Context:\n{ctx_str}\n\nTask: {task}"
        msgs.append({"role": "user", "content": user_content})
        return msgs
