"""Tests for RedisStore circuit-breaker logic in src/core/redis.py."""

import time
import pytest
from unittest.mock import AsyncMock, patch
from src.core.redis import RedisStore, CIRCUIT_BREAKER_COOLDOWN


@pytest.fixture
def store_with_mock_redis():
    s = RedisStore(prefix="cb")
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(side_effect=Exception("connection refused"))
    mock_redis.get = AsyncMock(side_effect=Exception("connection refused"))
    s.redis = mock_redis
    return s


@pytest.mark.asyncio
async def test_circuit_opens_on_redis_failure(store_with_mock_redis):
    store = store_with_mock_redis
    await store.set("k", "v")
    assert not store._redis_available


@pytest.mark.asyncio
async def test_fallback_used_after_circuit_opens(store_with_mock_redis):
    store = store_with_mock_redis
    await store.set("k", "value_fb")
    result = await store.get("k")
    assert result == "value_fb"


@pytest.mark.asyncio
async def test_circuit_closed_on_fresh_store():
    store = RedisStore(prefix="fresh")
    store.redis = None
    assert store._circuit_closed()


@pytest.mark.asyncio
async def test_circuit_still_open_before_cooldown(store_with_mock_redis):
    store = store_with_mock_redis
    await store.set("k", "v")  # triggers open
    store._circuit_opened_at = time.monotonic()  # reset timer
    assert not store._circuit_closed()


@pytest.mark.asyncio
async def test_circuit_auto_resets_after_cooldown(store_with_mock_redis):
    store = store_with_mock_redis
    await store.set("k", "v")  # triggers open
    store._circuit_opened_at = time.monotonic() - CIRCUIT_BREAKER_COOLDOWN - 1
    assert store._circuit_closed()
