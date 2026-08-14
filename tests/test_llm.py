"""Unit tests for the LLM service layer (ask_gpt).

Covers
------
- Basic happy-path response with no tool calls.
- Tool-call loop: model returns a tool call, tool executes, model returns
  the final answer on the next iteration.
- Tool execution failure propagates without swallowing.
- API error classification: 5xx -> LLMServiceUnavailableError,
  429 -> LLMRateLimitError, 422 -> LLMError.
"""
from __future__ import annotations

import httpx
from unittest.mock import AsyncMock, patch

import pytest

from src.services.llm import (
    ask_gpt,
    LLMError,
    LLMServiceUnavailableError,
    LLMRateLimitError,
    _classify_openai_exception,
)
from openai import RateLimitError, APIStatusError, APIConnectionError


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_response(output_text: str = "done", tool_calls=None):
    """Build a minimal AsyncMock mimicking an OpenAI Responses API result."""
    r = AsyncMock()
    r.output = tool_calls or []
    r.output_text = output_text
    return r


def _make_tool_call(
    call_id: str = "call_abc",
    name: str = "search_properties",
    arguments: str = "{}",
):
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": name,
        "arguments": arguments,
    }


def _api_status_error(status: int, message: str = "error"):
    """Build an APIStatusError with a real-looking httpx.Response."""
    resp = httpx.Response(
        status_code=status,
        headers={"content-type": "application/json"},
        json={"error": {"message": message}},
        request=httpx.Request(
            "POST", "https://api.groq.com/openai/v1/responses"
        ),
    )
    return APIStatusError(message=message, response=resp, body=None)


# ─── Happy path (no tool calls) ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ask_gpt_basic():
    mock_response = _make_response(output_text="Hello there!")
    with patch(
        "src.services.llm.client.responses.create", return_value=mock_response
    ):
        res = await ask_gpt(
            [{"role": "user", "content": [{"type": "input_text", "text": "Hi"}]}],
        )
    assert res.output_text == "Hello there!"


# ─── Tool-call loop ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ask_gpt_triggers_tool_then_returns_answer():
    """Iteration 1: model returns a tool call.
    Tool executes. Iteration 2: model returns plain-text answer."""
    tool_call = _make_tool_call(
        name="search_properties", arguments='{"query": "2br"}'
    )
    first_response = _make_response(output_text="", tool_calls=[tool_call])
    second_response = _make_response(output_text="I found 3 apartments.")

    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        return first_response if call_count == 1 else second_response

    fake_tool_output = {
        "type": "function_call_output",
        "call_id": "call_abc",
        "output": "[]",
    }

    with patch(
        "src.services.llm.client.responses.create", side_effect=fake_create
    ), patch(
        "src.tools.registry.registry.execute",
        AsyncMock(return_value=fake_tool_output),
    ) as mock_exec:
        res = await ask_gpt(
            [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Find me a 2br"}],
                }
            ],
            max_tool_iterations=3,
        )

    assert res.output_text == "I found 3 apartments."
    assert call_count == 2  # first call + follow-up after tool result
    mock_exec.assert_awaited_once()
    _, exec_name, exec_args = mock_exec.await_args.args
    assert exec_name == "search_properties"
    assert "2br" in exec_args


# ─── Error classification (unit-level, no network) ──────────────────────────


def test_classify_api_status_500_wraps_as_service_unavailable():
    exc = _api_status_error(500, "Server error")
    result = _classify_openai_exception(exc)
    assert isinstance(result, LLMServiceUnavailableError)


def test_classify_api_status_422_wraps_as_generic_llm_error():
    exc = _api_status_error(422, "Unprocessable Entity")
    result = _classify_openai_exception(exc)
    assert isinstance(result, LLMError)
    assert "422" in str(result)


def test_classify_rate_limit_error_wraps_as_rate_limit():
    status_err = _api_status_error(429, "Rate limited")
    exc = RateLimitError(
        message="Rate limited",
        response=status_err.response,
        body=None,
    )
    result = _classify_openai_exception(exc)
    assert isinstance(result, LLMRateLimitError)


def test_classify_connection_error_wraps_as_unavailable():
    """_classify_openai_exception maps APIConnectionError -> LLMServiceUnavailableError."""
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/responses")
    exc = APIConnectionError(request=request)
    result = _classify_openai_exception(exc)
    assert isinstance(result, LLMServiceUnavailableError)


# ─── Error propagation in ask_gpt ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ask_gpt_500_raises_service_unavailable():
    with patch(
        "src.services.llm.client.responses.create",
        side_effect=_api_status_error(502, "Bad Gateway"),
    ):
        with pytest.raises(LLMServiceUnavailableError, match="502"):
            await ask_gpt(
                [{"role": "user", "content": [{"type": "input_text", "text": "Hi"}]}],
            )


@pytest.mark.asyncio
async def test_ask_gpt_422_raises_generic_llm_error():
    with patch(
        "src.services.llm.client.responses.create",
        side_effect=_api_status_error(422, "Unprocessable Entity"),
    ):
        with pytest.raises(LLMError, match="422"):
            await ask_gpt(
                [{"role": "user", "content": [{"type": "input_text", "text": "Hi"}]}],
            )


@pytest.mark.asyncio
async def test_tool_execution_failure_propagates():
    """If registry.execute raises, ask_gpt must not swallow it."""
    tool_call = _make_tool_call(name="some_tool")
    response_with_tool = _make_response(output_text="", tool_calls=[tool_call])

    with patch(
        "src.services.llm.client.responses.create",
        return_value=response_with_tool,
    ), patch(
        "src.tools.registry.registry.execute",
        side_effect=RuntimeError("tool boom"),
    ):
        with pytest.raises(RuntimeError, match="tool boom"):
            await ask_gpt(
                [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": "Hi"}],
                    }
                ],
                max_tool_iterations=3,
            )
