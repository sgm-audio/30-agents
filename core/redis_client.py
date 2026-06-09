"""
Redis client for inter-agent messaging, state, and task queuing.
"""
import json
from typing import Any, Optional

import redis.asyncio as aioredis
import structlog

from core.config import settings

log = structlog.get_logger(__name__)


class RedisClient:
    """Async Redis wrapper for agent state and messaging."""

    def __init__(self):
        kwargs: dict[str, Any] = {
            "host": settings.redis_host,
            "port": settings.redis_port,
            "db": settings.redis_db,
            "decode_responses": True,
        }
        if settings.redis_password:
            kwargs["password"] = settings.redis_password
        self._pool = aioredis.ConnectionPool(**kwargs)
        self._r = aioredis.Redis(connection_pool=self._pool)

    async def ping(self) -> bool:
        try:
            return await self._r.ping()
        except Exception as e:
            log.debug("redis.ping.error", error=str(e))
            return False

    # ---- Key-Value ----
    async def set(self, key: str, value: Any, ex: Optional[int] = None):
        data = json.dumps(value) if not isinstance(value, str) else value
        await self._r.set(key, data, ex=ex)

    async def get(self, key: str) -> Optional[Any]:
        val = await self._r.get(key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val

    async def delete(self, key: str):
        await self._r.delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self._r.exists(key))

    # ---- Hash (agent state) ----
    async def hset(self, name: str, mapping: dict):
        serialized = {k: json.dumps(v) for k, v in mapping.items()}
        await self._r.hset(name, mapping=serialized)

    async def hget(self, name: str, field: str) -> Optional[Any]:
        val = await self._r.hget(name, field)
        if val is None:
            return None
        try:
            return json.loads(val)
        except Exception as e:
            log.debug("redis.json_parse_error", key=name, field=field, error=str(e))
            return val

    async def hgetall(self, name: str) -> dict:
        raw = await self._r.hgetall(name)
        result = {}
        for k, v in raw.items():
            try:
                result[k] = json.loads(v)
            except Exception as e:
                log.debug("redis.json_parse_error", key=name, field=k, error=str(e))
                result[k] = v
        return result

    # ---- List (task queue) ----
    async def lpush(self, key: str, *values):
        serialized = [json.dumps(v) for v in values]
        await self._r.lpush(key, *serialized)

    async def rpop(self, key: str) -> Optional[Any]:
        val = await self._r.rpop(key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except Exception as e:
            log.debug("redis.json_parse_error", key=key, error=str(e))
            return val

    async def brpop(self, key: str, timeout: int = 5) -> Optional[Any]:
        result = await self._r.brpop(key, timeout=timeout)
        if result is None:
            return None
        _, val = result
        try:
            return json.loads(val)
        except Exception as e:
            log.debug("redis.json_parse_error", key=key, error=str(e))
            return val

    async def llen(self, key: str) -> int:
        return await self._r.llen(key)

    # ---- Pub/Sub ----
    async def publish(self, channel: str, message: Any):
        data = json.dumps(message)
        await self._r.publish(channel, data)

    def pubsub(self):
        """Return a Redis pub/sub object for channel subscriptions."""
        return self._r.pubsub()

    # ---- Expiry / TTL ----
    async def expire(self, key: str, seconds: int):
        await self._r.expire(key, seconds)

    async def ttl(self, key: str) -> int:
        return await self._r.ttl(key)

    async def close(self):
        await self._pool.disconnect()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()


# Module-level singleton
# NOTE: same async single-threaded race as get_graph(); acceptable here
_redis: Optional[RedisClient] = None


def get_redis() -> RedisClient:
    global _redis
    if _redis is None:
        _redis = RedisClient()
    return _redis
