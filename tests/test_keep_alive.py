"""
Unit tests for keep_alive script and uptime lifespan manager.
"""

from unittest.mock import MagicMock, patch

from scripts.keep_alive import ping_qdrant, ping_supabase


def test_ping_supabase_missing_creds():
    with patch("scripts.keep_alive.supabase_url", ""), patch(
        "scripts.keep_alive.supabase_key", ""
    ):
        assert ping_supabase() is False


def test_ping_supabase_success():
    with (
        patch("scripts.keep_alive.supabase_url", "https://test.supabase.co"),
        patch("scripts.keep_alive.supabase_key", "eyJtestkey"),
        patch("urllib.request.urlopen") as mock_urlopen,
    ):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'[{"whatsapp_id": "123"}]'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        assert ping_supabase() is True


def test_ping_qdrant_missing_url():
    with patch("scripts.keep_alive.qdrant_url", ""):
        assert ping_qdrant() is False


def test_ping_qdrant_success():
    with (
        patch("scripts.keep_alive.qdrant_url", "https://test.qdrant.io"),
        patch("scripts.keep_alive.qdrant_api_key", "test-key"),
        patch("urllib.request.urlopen") as mock_urlopen,
    ):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = (
            b'{"result":{"collections":[{"name":"properties"}]},"status":"ok"}'
        )
        mock_urlopen.return_value.__enter__.return_value = mock_response

        assert ping_qdrant() is True
