# src/services/llm.py

from __future__ import annotations

import os
from typing import Any, List, Optional, Tuple
from openai import (
    AsyncOpenAI,
    RateLimitError,
    APIStatusError,
    APIConnectionError,
    APIError,
    AuthenticationError,
    PermissionDeniedError,
    NotFoundError,
    BadRequestError,
)
from loguru import logger

from src.configs.prompts import system_prompt
from src.configs.settings import (
    NVIDIA_API_KEY,
    GROQ_API_KEY,
    OPENROUTER_API_KEY,
    LLM_PROVIDER,
    LLM_BASE_URL,
    LLM_API_KEY,
    LLM_MODEL,
)
from src.configs.constants import GROQ_MODEL, OPENROUTER_MODEL, NVIDIA_MODEL
from src.tools.registry import registry


class LLMRateLimitError(Exception):
    """Raised when the upstream LLM returns 429 or rate-limit-like responses."""


class LLMServiceUnavailableError(Exception):
    """Raised when the upstream LLM is unreachable or returns 5xx."""


class LLMAuthenticationError(Exception):
    """Raised when the upstream LLM returns 401/403 (invalid key or forbidden/credits exhausted)."""


class LLMError(Exception):
    """Generic fallback for unexpected LLM/API failures."""


def resolve_llm_config() -> Tuple[str, str, str, str]:
    """
    Resolves the (provider, base_url, api_key, model_name) to use based on configuration
    and available API keys.

    Priority:
    1. Explicit custom LLM_BASE_URL + LLM_API_KEY
    2. Explicit LLM_PROVIDER environment variable
    3. Auto-detection: OpenRouter (full tool-call support + high TPM) → Groq → NVIDIA
    """
    # 1. Custom explicit configuration
    if LLM_BASE_URL and LLM_API_KEY:
        model = LLM_MODEL or "gpt-4o-mini"
        return "custom", LLM_BASE_URL, LLM_API_KEY, model

    # 2. Explicit provider selection
    provider = (LLM_PROVIDER or "").lower().strip()
    if provider == "groq" and GROQ_API_KEY:
        return "groq", "https://api.groq.com/openai/v1", GROQ_API_KEY, LLM_MODEL or GROQ_MODEL
    if provider == "openrouter" and OPENROUTER_API_KEY:
        return "openrouter", "https://openrouter.ai/api/v1", OPENROUTER_API_KEY, LLM_MODEL or OPENROUTER_MODEL
    if provider == "nvidia" and NVIDIA_API_KEY:
        return "nvidia", "https://integrate.api.nvidia.com/v1", NVIDIA_API_KEY, LLM_MODEL or NVIDIA_MODEL

    # 3. Auto-detection priority:
    # OpenRouter → Groq → NVIDIA
    # OpenRouter is preferred: broader model support, full function-calling spec, no strict TPM
    if OPENROUTER_API_KEY:
        return "openrouter", "https://openrouter.ai/api/v1", OPENROUTER_API_KEY, LLM_MODEL or OPENROUTER_MODEL
    if GROQ_API_KEY:
        return "groq", "https://api.groq.com/openai/v1", GROQ_API_KEY, LLM_MODEL or GROQ_MODEL
    if NVIDIA_API_KEY:
        return "nvidia", "https://integrate.api.nvidia.com/v1", NVIDIA_API_KEY, LLM_MODEL or NVIDIA_MODEL

    # Default fallback
    return "groq", "https://api.groq.com/openai/v1", "", LLM_MODEL or GROQ_MODEL


_active_provider, _active_base_url, _active_key, _active_model = resolve_llm_config()

# Module-level client (used by default and patched by unit tests)
client = AsyncOpenAI(
    api_key=_active_key or "missing_key",
    base_url=_active_base_url,
)

MODEL_NAME = _active_model
MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))
MAX_TOOL_ITERATIONS = int(os.getenv("LLM_MAX_TOOL_ITERATIONS", "10"))


def _classify_openai_exception(exc: Exception) -> Exception:
    """Map upstream OpenAI exceptions into semantic application error classes."""
    if isinstance(exc, RateLimitError):
        return LLMRateLimitError(f"LLM API rate limited: {exc}")
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return LLMAuthenticationError(f"LLM API authentication/permission error: {exc}")
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        body = ""
        try:
            body = exc.response.text if exc.response is not None else ""
        except Exception:
            body = ""
        if status in (401, 403):
            return LLMAuthenticationError(f"LLM API forbidden/unauthorized {status}: {body}".strip())
        if status and status >= 500:
            return LLMServiceUnavailableError(
                f"LLM API server error {status}: {body}".strip()
            )
        return LLMError(f"LLM API status error {status}: {body}".strip())
    if isinstance(exc, APIConnectionError):
        return LLMServiceUnavailableError(f"LLM API connection error: {exc}")
    if isinstance(exc, APIError):
        return LLMError(f"LLM API error: {exc}")
    return LLMError(f"Unexpected LLM error: {exc}")


def _build_openai_messages(history: list[dict], customer_context: Optional[str] = None) -> list[dict]:
    """Builds standard OpenAI Chat Completion messages from history with dynamic customer context."""
    sys_content = system_prompt
    if customer_context:
        sys_content += f"\n\n--- CURRENT CONVERSATION CONTEXT ---\n{customer_context}"

    messages = [
        {
            "role": "system",
            "content": sys_content,
        }
    ]
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role", "user")
        content = item.get("content", "")

        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    if "text" in part:
                        text_parts.append(str(part["text"]))
                    elif "input_text" in part:
                        text_parts.append(str(part["input_text"]))
                elif isinstance(part, str):
                    text_parts.append(part)
            content_str = "\n".join(text_parts) if text_parts else str(content)
        else:
            content_str = str(content) if content is not None else ""

        msg_dict: dict[str, Any] = {"role": role}

        # For assistant messages with tool calls, content can be None
        if role == "assistant" and "tool_calls" in item and not content_str:
            msg_dict["content"] = None
        else:
            msg_dict["content"] = content_str

        if "tool_calls" in item:
            # Ensure tool_calls are serialized dicts
            raw_calls = item["tool_calls"]
            msg_dict["tool_calls"] = [
                tc.model_dump() if hasattr(tc, "model_dump") else tc
                for tc in raw_calls
            ]
        if "tool_call_id" in item:
            msg_dict["tool_call_id"] = item["tool_call_id"]
        if "name" in item:
            msg_dict["name"] = item["name"]

        messages.append(msg_dict)

    return messages


def _format_tools(tools: list[dict]) -> list[dict]:
    """Formats tool declarations for OpenAI chat completions."""
    formatted = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if "function" in tool and isinstance(tool["function"], dict):
            formatted.append(tool)
        elif tool.get("type") == "function" and "name" in tool:
            func_dict = {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters", {}),
            }
            if "strict" in tool:
                func_dict["strict"] = tool["strict"]
            formatted.append({
                "type": "function",
                "function": func_dict,
            })
        else:
            formatted.append(tool)
    return formatted


async def ask_gpt(
    history: list[dict],
    customer_context: Optional[str] = None,
    max_tool_iterations: int = MAX_TOOL_ITERATIONS,
):
    """Sends conversation history to OpenAI-compatible Chat Completions API with automatic tool execution."""
    tools = registry.get_llm_declarations()
    messages = _build_openai_messages(history, customer_context=customer_context)

    last_error: Exception | None = None
    response = None

    for iteration in range(max_tool_iterations):
        kwargs: dict = {
            "model": MODEL_NAME,
            "messages": messages,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
        if tools:
            kwargs["tools"] = _format_tools(tools)
            kwargs["tool_choice"] = "auto"

        try:
            response = await client.chat.completions.create(**kwargs)
        except RateLimitError as exc:
            last_error = _classify_openai_exception(exc)
            logger.warning("LLM rate limited on iteration {}: {}", iteration, exc)
            raise last_error
        except APIStatusError as exc:
            last_error = _classify_openai_exception(exc)
            status = getattr(exc, "status_code", None)
            logger.error("LLM API status error {} on iteration {}: {}", status, iteration, exc)
            raise last_error
        except APIConnectionError as exc:
            last_error = _classify_openai_exception(exc)
            logger.error("LLM connection error on iteration {}: {}", iteration, exc)
            raise last_error
        except APIError as exc:
            last_error = _classify_openai_exception(exc)
            logger.error("LLM API error on iteration {}: {}", iteration, exc)
            raise last_error
        except Exception as exc:
            last_error = _classify_openai_exception(exc)
            logger.exception("Unexpected error calling LLM on iteration {}", iteration)
            raise last_error

        choices = getattr(response, "choices", None) or []
        if not choices:
            setattr(response, "output_text", "")
            return response

        first_choice = choices[0]
        msg = getattr(first_choice, "message", None)
        finish_reason = getattr(first_choice, "finish_reason", None)

        output_text = getattr(msg, "content", None) or ""
        setattr(response, "output_text", output_text)

        tool_calls = getattr(msg, "tool_calls", None) or []

        logger.info(
            "LLM response iteration={} finish_reason={} output_text_len={} tool_calls_len={}",
            iteration,
            finish_reason,
            len(output_text),
            len(tool_calls),
        )

        if not tool_calls:
            return response

        assistant_msg = {
            "role": "assistant",
            "content": output_text or None,
            "tool_calls": [
                tc.model_dump() if hasattr(tc, "model_dump") else tc
                for tc in tool_calls
            ],
        }
        messages.append(assistant_msg)

        for tc in tool_calls:
            call_id = getattr(tc, "id", None) or (tc.get("id") if isinstance(tc, dict) else None)
            func = getattr(tc, "function", None)
            if func:
                name = getattr(func, "name", None)
                args = getattr(func, "arguments", None)
            elif isinstance(tc, dict) and "function" in tc:
                name = tc["function"].get("name")
                args = tc["function"].get("arguments")
            else:
                call_id = tc.get("call_id") if isinstance(tc, dict) else call_id
                name = tc.get("name") if isinstance(tc, dict) else None
                args = tc.get("arguments") if isinstance(tc, dict) else None

            try:
                tool_output_item = await registry.execute(call_id, name, args)
            except Exception as exc:
                logger.exception("Tool execution failed during LLM iteration {}", iteration)
                raise

            if isinstance(tool_output_item, dict) and "output" in tool_output_item:
                tool_result_content = tool_output_item["output"]
            else:
                tool_result_content = str(tool_output_item)

            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": tool_result_content,
            })

    assert last_error is None, (
        "last_error was set but no exception was raised — "
        "a raise was removed from an except branch"
    )
    return response
