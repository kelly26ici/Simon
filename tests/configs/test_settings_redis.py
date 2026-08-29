"""Tests for Redis / Supabase / Telegram settings (src/configs/settings.py)."""

import src.configs.settings as s


def test_redis_url_defined():
    assert hasattr(s, "REDIS_URL")
    assert isinstance(s.REDIS_URL, str)


def test_supabase_url_defined():
    assert hasattr(s, "SUPABASE_URL")


def test_supabase_key_defined():
    assert hasattr(s, "SUPABASE_KEY")


def test_telegram_bot_token_defined():
    assert hasattr(s, "TELEGRAM_BOT_TOKEN")


def test_simon_chat_id_defined():
    assert hasattr(s, "SIMON_CHAT_ID")


def test_render_base_url_default():
    assert hasattr(s, "RENDER_BASE_URL")
    assert "onrender.com" in s.RENDER_BASE_URL
