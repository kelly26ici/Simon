"""Tests for src/clients/supabase_client.py."""

import importlib
from unittest.mock import patch, MagicMock


def test_supabase_client_none_when_no_credentials():
    """When SUPABASE_URL or SUPABASE_KEY is missing, client should be None."""
    with patch("src.configs.settings.SUPABASE_URL", ""), \
         patch("src.configs.settings.SUPABASE_KEY", ""):
        import src.clients.supabase_client as m
        importlib.reload(m)
        assert m.supabase is None


def test_supabase_client_created_when_credentials_present():
    """When both credentials are set, supabase.create_client should be called."""
    mock_client = MagicMock()
    with patch("src.configs.settings.SUPABASE_URL", "https://test.supabase.co"), \
         patch("src.configs.settings.SUPABASE_KEY", "test-key"), \
         patch("supabase.create_client", return_value=mock_client):
        import src.clients.supabase_client as m
        importlib.reload(m)
        assert m.supabase is mock_client
