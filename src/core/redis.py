import json
from typing import Any, Optional
from redis.asyncio import Redis
from loguru import logger
from src.configs.settings import REDIS_URL

try:
    redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
except Exception as e:
    logger.warning("Failed to initialize Redis client: {}", e)
    redis_client = None


class RedisStore:
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.redis = redis_client
        self._fallback_memory: dict[str, str] = {}

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def set(self, key: str, data: Any, ex: int = None) -> None:
        k = self._key(key)
        val = json.dumps(data)
        if self.redis:
            try:
                await self.redis.set(k, val, ex=ex)
                return
            except Exception as e:
                logger.warning("Redis set failed, using in-memory fallback: {}", e)
        self._fallback_memory[k] = val

    async def get(self, key: str) -> Optional[Any]:
        k = self._key(key)
        val = None
        if self.redis:
            try:
                val = await self.redis.get(k)
            except Exception as e:
                logger.warning("Redis get failed, checking in-memory fallback: {}", e)
        if val is None:
            val = self._fallback_memory.get(k)
        if val:
            return json.loads(val)
        return None

    async def delete(self, key: str) -> None:
        k = self._key(key)
        if self.redis:
            try:
                await self.redis.delete(k)
            except Exception as e:
                logger.warning("Redis delete failed: {}", e)
        self._fallback_memory.pop(k, None)

    async def update(self, key: str, **fields) -> None:
        data = await self.get(key) or {}
        if isinstance(data, dict):
            data.update(fields)
            await self.set(key, data)
