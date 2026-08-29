"""Tests for RedisStore fallback in-memory behavior (no live Redis)."""

import pytest
from src.core.redis import RedisStore


@pytest.fixture
def store():
    s = RedisStore(prefix="test")
    s.redis = None  # Force in-memory fallback
    return s


@pytest.mark.asyncio
async def test_set_and_get_string(store):
    await store.set("key1", "hello")
    result = await store.get("key1")
    assert result == "hello"


@pytest.mark.asyncio
async def test_set_and_get_dict(store):
    await store.set("user", {"name": "Alice", "age": 30})
    result = await store.get("user")
    assert result == {"name": "Alice", "age": 30}


@pytest.mark.asyncio
async def test_get_missing_key_returns_none(store):
    result = await store.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_delete_removes_key(store):
    await store.set("to_delete", "value")
    await store.delete("to_delete")
    result = await store.get("to_delete")
    assert result is None


@pytest.mark.asyncio
async def test_update_merges_fields(store):
    await store.set("profile", {"name": "Bob"})
    await store.update("profile", age=25)
    result = await store.get("profile")
    assert result["name"] == "Bob"
    assert result["age"] == 25


@pytest.mark.asyncio
async def test_update_creates_key_if_missing(store):
    await store.update("fresh", value="new")
    result = await store.get("fresh")
    assert result == {"value": "new"}
