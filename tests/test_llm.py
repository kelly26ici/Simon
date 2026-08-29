"""Unit tests for the LLM service layer (ask_llm / ask_gpt alias).

Covers
------
- Basic happy-path response with no tool calls.
- Tool-call loop: model returns a tool call, tool executes, model returns
  the final answer on the next iteration.
- Tool execution failure is serialised as a structured error payload back
  to the LLM, NOT propagated to the caller (by design).
- API error classification: 5xx -> LLMServiceUnavailableError,
  429 -> LLMRateLimitError, 422 -> LLMError.
"""
from __future__ import annotations

import httpx
from unittest.mock import AsyncMock, patch

import pytest

import src.services.llm as llm_service
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
    """Build a minimal AsyncMock mimicking an OpenAI ChatCompletion result."""
    msg = AsyncMock()
    msg.content = output_text
    msg.tool_calls = tool_calls or None

    choice = AsyncMock()
    choice.message = msg
    choice.finish_reason = "tool_calls" if tool_calls else "stop"

    r = AsyncMock()
    r.choices = [choice]
    r.output_text = output_text
    return r


def _make_tool_call(
    call_id: str = "call_abc",
    name: str = "search_properties",
    arguments: str = "{}",
):
    func = AsyncMock()
    func.name = name
    func.arguments = arguments

    tc = AsyncMock()
    tc.id = call_id
    tc.function = func
    return tc


def _api_status_error(status: int, message: str = "error"):
    """Build an APIStatusError with a real-looking httpx.Response."""
    resp = httpx.Response(
        status_code=status,
        headers={"content-type": "application/json"},
        json={"error": {"message": message}},
        request=httpx.Request(
            "POST", "https://integrate.api.nvidia.com/v1/chat/completions"
        ),
    )
    return APIStatusError(message=message, response=resp, body=None)


# ─── Provider model resolution ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "configured_model",
    [
        "stepfun-ai/step-3.7-flash",
        "poolside/laguna-xs-2.1",
        "nvidia_nim/poolside/laguna-xs-2.1",
        "nvidia_nim/deepseek-ai/deepseek-v4-flash-0731",
    ],
)
def test_nvidia_resolution_replaces_invalid_model_override(monkeypatch, configured_model):
    monkeypatch.setattr(llm_service, "NVIDIA_API_KEY", "test-key")
    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "nvidia")
    monkeypatch.setattr(llm_service, "LLM_MODEL", configured_model)

    provider, _base_url, _api_key, model = llm_service.resolve_llm_config()

    assert provider == "nvidia"
    assert model == "deepseek-ai/deepseek-v4-flash-0731"


def test_nvidia_resolution_preserves_active_model_override(monkeypatch):
    monkeypatch.setattr(llm_service, "NVIDIA_API_KEY", "test-key")
    monkeypatch.setattr(llm_service, "LLM_PROVIDER", "nvidia")
    monkeypatch.setattr(llm_service, "LLM_MODEL", "some-active-nvidia-model")

    _provider, _base_url, _api_key, model = llm_service.resolve_llm_config()

    assert model == "some-active-nvidia-model"


# ─── Happy path (no tool calls) ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ask_gpt_basic():
    mock_response = _make_response(output_text="Hello there!")
    with patch(
        "src.services.llm.client.chat.completions.create", AsyncMock(return_value=mock_response)
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
        "src.services.llm.client.chat.completions.create", side_effect=fake_create
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
    request = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    exc = APIConnectionError(request=request)
    result = _classify_openai_exception(exc)
    assert isinstance(result, LLMServiceUnavailableError)


# ─── Regression: tool-call loop must not waste extra API calls ────────────────


@pytest.mark.asyncio
async def test_ask_gpt_tool_call_then_answer_exactly_two_calls():
    """After one tool call + tool execution, the model is called exactly once more.

    Reproduces the bug where the loop ran extra iterations after tool resolution,
    causing empty output_text on the wasted call and unnecessary rate-limit burn.
    """
    tool_call = _make_tool_call(
        name="search_properties", arguments='{"query": "2br"}'
    )
    first_response = _make_response(output_text="", tool_calls=[tool_call])
    second_response = _make_response(output_text="Here are 3 matching properties.")

    call_count = 0
    captured_kwargs = []

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        captured_kwargs.append(kwargs)
        return first_response if call_count == 1 else second_response

    fake_tool_output = {
        "type": "function_call_output",
        "call_id": "call_abc",
        "output": '[{"id": 1, "title": "2BR Apt, Kilimani", "price": 50000}]',
    }

    with patch(
        "src.services.llm.client.chat.completions.create", side_effect=fake_create
    ), patch(
        "src.tools.registry.registry.execute",
        AsyncMock(return_value=fake_tool_output),
    ):
        res = await ask_gpt(
            [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Find me a 2br in Kilimani"}],
                }
            ],
            max_tool_iterations=3,
        )

    assert res.output_text == "Here are 3 matching properties."
    assert call_count == 2  # first call + one follow-up — no wasted third call

    # Verify the second request actually carried the tool result back to the model
    assert len(captured_kwargs) == 2
    second_messages = captured_kwargs[1]["messages"]
    roles = [
        msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
        for msg in second_messages
    ]
    assert "tool" in roles, (
        "Second ChatCompletions API request must include the tool role item"
    )


@pytest.mark.asyncio
async def test_ask_gpt_tool_call_then_answer_does_not_loop_idly():
    """With max_tool_iterations=2 the loop must complete cleanly, not raise."""
    tool_call = _make_tool_call(name="search_properties", arguments='{"query": "2br"}')
    first_response = _make_response(output_text="", tool_calls=[tool_call])
    second_response = _make_response(output_text="Done.")

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
        "src.services.llm.client.chat.completions.create", side_effect=fake_create
    ), patch(
        "src.tools.registry.registry.execute",
        AsyncMock(return_value=fake_tool_output),
    ):
        res = await ask_gpt(
            [{"role": "user", "content": [{"type": "input_text", "text": "Find 2br"}]}],
            max_tool_iterations=2,
        )

    assert res.output_text == "Done."
    assert call_count == 2


# ─── Error propagation in ask_gpt ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ask_gpt_500_raises_service_unavailable():
    with patch(
        "src.services.llm.client.chat.completions.create",
        side_effect=_api_status_error(502, "Bad Gateway"),
    ):
        with pytest.raises(LLMServiceUnavailableError, match="502"):
            await ask_gpt(
                [{"role": "user", "content": [{"type": "input_text", "text": "Hi"}]}],
            )


@pytest.mark.asyncio
async def test_ask_gpt_422_raises_generic_llm_error():
    with patch(
        "src.services.llm.client.chat.completions.create",
        side_effect=_api_status_error(422, "Unprocessable Entity"),
    ):
        with pytest.raises(LLMError, match="422"):
            await ask_gpt(
                [{"role": "user", "content": [{"type": "input_text", "text": "Hi"}]}],
            )


@pytest.mark.asyncio
async def test_tool_execution_failure_is_returned_to_llm_not_raised():
    """Tool runtime errors must be serialised as a structured error payload
    into the next LLM turn — NOT propagated to the caller.

    Previously the test expected a RuntimeError to bubble out of ask_llm, but
    the intended design (as stated in the docstring of ask_llm) is to pass the
    failure back to the model so it can retry, use a fallback tool, or explain
    to the customer why it cannot complete the request.
    """
    tool_call = _make_tool_call(name="some_tool")
    response_with_tool = _make_response(output_text="", tool_calls=[tool_call])
    final_response = _make_response(output_text="Sorry, I ran into a problem with that tool.")

    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        # First call triggers the tool.
        # Second call receives the error payload and produces the final answer.
        return response_with_tool if call_count == 1 else final_response

    captured_messages = []

    async def fake_create_capturing(**kwargs):
        nonlocal call_count
        call_count += 1
        captured_messages.extend(kwargs.get("messages", []))
        return response_with_tool if call_count == 1 else final_response

    with patch(
        "src.services.llm.client.chat.completions.create",
        side_effect=fake_create_capturing,
    ), patch(
        "src.tools.registry.registry.execute",
        side_effect=RuntimeError("tool boom"),
    ):
        result = await ask_gpt(
            [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Hi"}],
                }
            ],
            max_tool_iterations=3,
        )

    # The loop must NOT raise — it returns the LLM's follow-up answer.
    assert result is not None
    # The LLM was called at least twice (once to get the tool call, once with the error payload).
    assert call_count >= 2
    # The captured messages for the second LLM call must contain a "tool" role message
    # with an error payload so the model can reason about what went wrong.
    tool_role_messages = [
        m for m in captured_messages if isinstance(m, dict) and m.get("role") == "tool"
    ]
    assert len(tool_role_messages) >= 1, (
        "A 'tool' role message containing the error payload must be sent back to the LLM"
    )
    import json as _json
    tool_content = tool_role_messages[0].get("content", "")
    parsed = _json.loads(tool_content) if isinstance(tool_content, str) else tool_content
    assert "error" in parsed, "Tool error payload must include an 'error' key"
    assert "tool boom" in parsed.get("detail", ""), (
        "Tool error payload must include the original exception message in 'detail'"
    )

