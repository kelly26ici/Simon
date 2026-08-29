"""Tests for verify_signature() in src/messages/validator.py."""

import hmac
import hashlib
from unittest.mock import patch
from src.messages.validator import verify_signature

SECRET = "my_test_secret"
PAYLOAD = b'{"test": "data"}'


def _make_sig(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_valid_signature_returns_true():
    sig = _make_sig(PAYLOAD, SECRET)
    with patch("src.messages.validator.META_APP_SECRET", SECRET):
        assert verify_signature(PAYLOAD, sig) is True


def test_invalid_signature_returns_false():
    with patch("src.messages.validator.META_APP_SECRET", SECRET):
        assert verify_signature(PAYLOAD, "sha256=deadbeef") is False


def test_missing_sha256_prefix_returns_false():
    sig = _make_sig(PAYLOAD, SECRET)
    bare_sig = sig.replace("sha256=", "")
    with patch("src.messages.validator.META_APP_SECRET", SECRET):
        assert verify_signature(PAYLOAD, bare_sig) is False


def test_no_secret_returns_false():
    with patch("src.messages.validator.META_APP_SECRET", ""):
        assert verify_signature(PAYLOAD, "sha256=anything") is False
