"""Tests for M-Pesa webhook verification and router in src/tools/mpesa/webhooks.py."""

import pytest
from unittest.mock import patch
from fastapi import HTTPException
from src.tools.mpesa.webhooks import _check_secret, router


def test_check_secret_valid():
    with patch("src.tools.mpesa.webhooks.MPESA_WEBHOOK_SECRET", "test_secret"):
        # Should not raise
        _check_secret("test_secret")


def test_check_secret_invalid_raises_404():
    with patch("src.tools.mpesa.webhooks.MPESA_WEBHOOK_SECRET", "test_secret"):
        with pytest.raises(HTTPException) as exc:
            _check_secret("wrong_secret")
        assert exc.value.status_code == 404


def test_mpesa_router_prefix():
    assert router.prefix == "/mpesa"
