"""Tests for header and URL helpers in src/messages/sender.py."""

from unittest.mock import patch
from src.messages.sender import _get_headers, _get_messages_url


def test_get_headers_contains_authorization():
    with patch("src.messages.sender.META_ACCESS_TOKEN", "test-token"):
        headers = _get_headers()
    assert headers["Authorization"] == "Bearer test-token"


def test_get_headers_contains_content_type():
    with patch("src.messages.sender.META_ACCESS_TOKEN", "test-token"):
        headers = _get_headers()
    assert headers["Content-Type"] == "application/json"


def test_get_messages_url_uses_graph_base():
    with patch("src.messages.sender.META_GRAPH_BASE_URL", "https://graph.facebook.com"), \
         patch("src.messages.sender.META_GRAPH_API_VERSION", "v23.0"), \
         patch("src.messages.sender.META_PHONE_NUMBER_ID", "98765"):
        url = _get_messages_url()
    assert "graph.facebook.com" in url
    assert "v23.0" in url
    assert "98765" in url


def test_get_messages_url_override_phone_id():
    with patch("src.messages.sender.META_GRAPH_BASE_URL", "https://graph.facebook.com"), \
         patch("src.messages.sender.META_GRAPH_API_VERSION", "v23.0"), \
         patch("src.messages.sender.META_PHONE_NUMBER_ID", "default-id"):
        url = _get_messages_url(phone_number_id="custom-id")
    assert "custom-id" in url
    assert "default-id" not in url


def test_extract_error_details_from_http_status_error():
    import httpx
    from unittest.mock import MagicMock
    from src.messages.sender import _extract_error_details
    mock_response = MagicMock()
    mock_response.json.return_value = {"error": {"code": 190, "message": "Invalid token"}}
    exc = httpx.HTTPStatusError("Error", request=MagicMock(), response=mock_response)
    details = _extract_error_details(exc)
    assert details.get("code") == 190
