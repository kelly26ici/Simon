"""Tests for WhatsApp settings (src/configs/settings.py)."""

import src.configs.settings as s


def test_meta_verify_token_is_str():
    assert isinstance(s.META_VERIFY_TOKEN, str)


def test_meta_graph_api_version_default():
    assert s.META_GRAPH_API_VERSION == "v23.0"


def test_meta_graph_base_url_default():
    assert s.META_GRAPH_BASE_URL == "https://graph.facebook.com"


def test_max_history_is_int():
    assert isinstance(s.MAX_HISTORY, int)


def test_conversation_ttl_seconds_is_int():
    assert isinstance(s.CONVERSATION_TTL_SECONDS, int)
    assert s.CONVERSATION_TTL_SECONDS > 0


def test_whatsapp_max_message_length_default():
    assert s.WHATSAPP_MAX_MESSAGE_LENGTH == 4096


def test_whatsapp_table_mode_is_str():
    assert isinstance(s.WHATSAPP_TABLE_MODE, str)


def test_whatsapp_format_debug_is_bool():
    assert isinstance(s.WHATSAPP_FORMAT_DEBUG, bool)
