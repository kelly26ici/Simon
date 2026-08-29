"""Tests for create_http_client() in src/clients/httpx_client.py."""

import httpx
from src.clients.httpx_client import create_http_client


def test_create_http_client_returns_async_client():
    client = create_http_client()
    assert isinstance(client, httpx.AsyncClient)


def test_create_http_client_follow_redirects():
    client = create_http_client()
    assert client.follow_redirects is True


def test_create_http_client_timeout_connect():
    client = create_http_client()
    assert client.timeout.connect == 10.0


def test_create_http_client_timeout_read():
    client = create_http_client()
    assert client.timeout.read == 30.0


def test_create_http_client_not_closed():
    client = create_http_client()
    assert not client.is_closed
