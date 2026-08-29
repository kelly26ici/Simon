"""Tests for RedisStore._key() (prefix namespacing) in src/core/redis.py."""

from src.core.redis import RedisStore


def test_key_combines_prefix_and_key():
    store = RedisStore(prefix="conv")
    assert store._key("user_123") == "conv:user_123"


def test_key_uses_correct_prefix():
    store = RedisStore(prefix="session")
    result = store._key("abc")
    assert result.startswith("session:")


def test_key_different_prefixes_different_keys():
    s1 = RedisStore(prefix="a")
    s2 = RedisStore(prefix="b")
    assert s1._key("x") != s2._key("x")
