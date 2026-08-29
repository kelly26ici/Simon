"""Tests for M-Pesa settings (src/configs/settings.py)."""

import src.configs.settings as s


def test_mpesa_base_url_is_sandbox():
    assert "sandbox.safaricom.co.ke" in s.MPESA_BASE_URL


def test_mpesa_base_url_is_string():
    assert isinstance(s.MPESA_BASE_URL, str)


def test_consumer_key_is_defined():
    assert hasattr(s, "CONSUMER_KEY")


def test_consumer_secret_is_defined():
    assert hasattr(s, "CONSUMER_SECRET")


def test_mpesa_webhook_secret_is_defined():
    assert hasattr(s, "MPESA_WEBHOOK_SECRET")
