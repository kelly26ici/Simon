import json
import time
from typing import Any, Optional
from redis.asyncio import Redis
from loguru import logger
from src.configs.settings import REDIS_URL

redis_client: Optional[Redis] = None

if REDIS_URL:
    try:
        redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
    except Exception as e:
        logger.warning("Failed to construct Redis client: {}", e)
        redis_client = None

# How long to wait before retrying Redis after a failure (circuit breaker cooldown)
CIRCUIT_BREAKER_COOLDOWN = 60  # seconds


class RedisStore:
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.redis = redis_client
        self._fallback_memory: dict[str, str] = {}
        self._redis_available = True  # Circuit breaker flag
        self._circuit_opened_at: float = 0.0

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    def _circuit_closed(self) -> bool:
        """Check if the circuit breaker has cooled down enough to retry Redis."""
        if not self._redis_available:
            if time.monotonic() - self._circuit_opened_at >= CIRCUIT_BREAKER_COOLDOWN:
                logger.info("Redis circuit breaker cooldown elapsed, retrying Redis")
                self._redis_available = True
        return self._redis_available

    def _open_circuit(self) -> None:
        """Open the circuit breaker and record when it was opened."""
        self._redis_available = False
        self._circuit_opened_at = time.monotonic()

    async def set(self, key: str, data: Any, ex: int = None) -> None:
        k = self._key(key)
        val = json.dumps(data)

        if self.redis and self._circuit_closed():
            try:
                await self.redis.set(k, val, ex=ex)
                return
            except Exception as e:
                logger.warning("Redis set failed, falling back to in-memory: {}", e)
                self._open_circuit()

        self._fallback_memory[k] = val

    async def get(self, key: str) -> Optional[Any]:
        k = self._key(key)
        val = None

        if self.redis and self._circuit_closed():
            try:
                val = await self.redis.get(k)
            except Exception as e:
                logger.warning("Redis get failed, falling back to in-memory: {}", e)
                self._open_circuit()

        if val is None:
            val = self._fallback_memory.get(k)
        if val is not None:
            return json.loads(val)
        return None

    async def delete(self, key: str) -> None:
        k = self._key(key)
        if self.redis and self._circuit_closed():
            try:
                await self.redis.delete(k)
            except Exception as e:
                logger.warning("Redis delete failed: {}", e)
                self._open_circuit()
        self._fallback_memory.pop(k, None)

    async def update(self, key: str, **fields: Any) -> None:
        data = await self.get(key) or {}
        if isinstance(data, dict):
            data.update(fields)
            await self.set(key, data)
        else:
            logger.warning(
                "Cannot update non-dict value at key '{}': {}", key, type(data).__name__
            )
