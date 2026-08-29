"""Tests for database keepalive script in scripts/keep_alive.py."""

from unittest.mock import patch, MagicMock
from scripts.keep_alive import ping_supabase, ping_qdrant


def test_ping_supabase():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'[{"whatsapp_id": "123"}]'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("scripts.keep_alive.supabase_url", "https://example.supabase.co"), \
         patch("scripts.keep_alive.supabase_key", "fake_key"), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = ping_supabase()
        assert res is True


def test_ping_qdrant():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"result": {"collections": [{"name": "properties"}]}}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("scripts.keep_alive.qdrant_url", "https://example.qdrant.io"), \
         patch("scripts.keep_alive.qdrant_api_key", "fake_key"), \
         patch("urllib.request.urlopen", return_value=mock_resp):
        res = ping_qdrant()
        assert res is True
