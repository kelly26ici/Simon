"""Tests for the web chat route in src/routes/chat.py.

These mirror the style of tests/routes/test_routes_properties.py: a minimal
FastAPI app with only the chat router, and the LLM / DB / Redis dependencies
patched so no real external call is made.
"""

from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from src.routes.chat import router


def _mock_db():
    """A mock of the src.services.db.DatabaseClient with async save_message."""
    m = MagicMock()
    m.save_message = AsyncMock()
    return m


@contextmanager
def _patched_chat(mock_db, api_key="secret-key", reply=None, ask_llm_side_effect=None):
    """Patch the chat route's dependencies; yields the ask_llm AsyncMock."""
    ask_mock = (
        AsyncMock(side_effect=ask_llm_side_effect)
        if ask_llm_side_effect is not None
        else AsyncMock(return_value=reply)
    )
    patches = [
        patch("src.routes.chat.SAMANTHA_WEB_API_KEY", api_key),
        patch("src.routes.chat.append_message", new=AsyncMock()),
        patch("src.routes.chat.get_history", new=AsyncMock(return_value=[])),
        patch("src.routes.chat._build_customer_context_string", new=AsyncMock(return_value="ctx")),
        patch("src.routes.chat.ask_llm", new=ask_mock),
        patch("src.routes.chat.db", new=mock_db),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield ask_mock


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def fake_reply():
    """Simulates the object ask_llm returns (has .output_text)."""
    return SimpleNamespace(output_text="Here are some homes I found for you.")


@pytest.mark.asyncio
async def test_chat_requires_api_key_when_configured(app, fake_reply):
    """When SAMANTHA_WEB_API_KEY is set, a missing/incorrect key yields 401."""
    mock_db = _mock_db()
    with _patched_chat(mock_db, api_key="secret-key", reply=fake_reply):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # No key at all
            resp = await client.post("/api/chat/", json={"message": "hi"})
            assert resp.status_code == 401

            # Wrong key
            resp = await client.post(
                "/api/chat/",
                json={"message": "hi"},
                headers={"X-API-Key": "wrong-key"},
            )
            assert resp.status_code == 401

            # Body never ran, so nothing was persisted
            assert mock_db.save_message.await_count == 0


@pytest.mark.asyncio
async def test_chat_succeeds_with_valid_key(app, fake_reply):
    """A valid-key request returns 200 with {reply, session_id}."""
    mock_db = _mock_db()
    with _patched_chat(mock_db, api_key="secret-key", reply=fake_reply) as ask_mock:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/chat/",
                json={"message": "3 bedroom house in Karen"},
                headers={"X-API-Key": "secret-key"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["reply"] == "Here are some homes I found for you."
            assert data["session_id"].startswith("web-")

            # ask_llm invoked once with session history + context
            assert ask_mock.await_count == 1
            kwargs = ask_mock.call_args.kwargs
            assert kwargs["customer_context"] == "ctx"

            # user then assistant message persisted to Supabase
            assert mock_db.save_message.await_count == 2


@pytest.mark.asyncio
async def test_chat_open_when_api_key_unset(app, fake_reply):
    """When SAMANTHA_WEB_API_KEY is empty, the endpoint is open (dev mode)."""
    mock_db = _mock_db()
    with _patched_chat(mock_db, api_key="", reply=fake_reply):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/chat/", json={"message": "hello"})
            assert resp.status_code == 200
            assert "reply" in resp.json()


@pytest.mark.asyncio
async def test_chat_reuses_client_session_id(app, fake_reply):
    """If the client supplies a session_id it is reused (not regenerated)."""
    mock_db = _mock_db()
    with _patched_chat(mock_db, api_key="secret-key", reply=fake_reply):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/chat/",
                json={"session_id": "web-visitor-99", "message": "hello"},
                headers={"X-API-Key": "secret-key"},
            )
            assert resp.status_code == 200
            assert resp.json()["session_id"] == "web-visitor-99"


@pytest.mark.asyncio
async def test_chat_llm_failure_returns_503(app):
    """A typed LLM error surfaces as 503 so the widget can show a fallback."""
    from src.services.llm import LLMServiceUnavailableError

    mock_db = _mock_db()
    with _patched_chat(
        mock_db,
        api_key="secret-key",
        reply=None,
        ask_llm_side_effect=LLMServiceUnavailableError("down"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/chat/",
                json={"message": "hello"},
                headers={"X-API-Key": "secret-key"},
            )
            assert resp.status_code == 503
