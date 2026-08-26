# src/services/llm.py

from __future__ import annotations

import os
import re
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
    LLM_TEMPERATURE,
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


_SECRET_PATTERNS = [
    ("api_key", r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{20,})['\"]?"),
    ("token", r"(?i)(token|access_token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{20,})['\"]?"),
    ("password", r"(?i)(password|passkey|pass)\s*[:=]\s*['\"]?([^\s'\"]{8,})['\"]?"),
    ("secret", r"(?i)(secret)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{20,})['\"]?"),
]


def _sanitize(text: str) -> str:
    sanitized = text
    for _name, pattern in _SECRET_PATTERNS:
        sanitized = re.sub(pattern, r"\1: [REDACTED]", sanitized)
    return sanitized


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
    # NVIDIA → OpenRouter → Groq
    # NVIDIA is preferred: aligns with project’s step‑function flash model and lower latency.
    if NVIDIA_API_KEY:
        return "nvidia", "https://integrate.api.nvidia.com/v1", NVIDIA_API_KEY, LLM_MODEL or NVIDIA_MODEL
    if OPENROUTER_API_KEY:
        return "openrouter", "https://openrouter.ai/api/v1", OPENROUTER_API_KEY, LLM_MODEL or OPENROUTER_MODEL
    if GROQ_API_KEY:
        return "groq", "https://api.groq.com/openai/v1", GROQ_API_KEY, LLM_MODEL or GROQ_MODEL

    # Default fallback to NVIDIA model (even without key, will raise auth later)
    return "nvidia", "https://integrate.api.nvidia.com/v1", "", LLM_MODEL or NVIDIA_MODEL


_active_provider, _active_base_url, _active_key, _active_model = resolve_llm_config()

# Module-level client (used by default and patched by unit tests)
client = AsyncOpenAI(
    api_key=_active_key or "missing_key",
    base_url=_active_base_url,
)

MODEL_NAME = _active_model
MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))
MAX_TOOL_ITERATIONS = int(os.getenv("LLM_MAX_TOOL_ITERATIONS", "10"))

try:
    _raw_temp = float(LLM_TEMPERATURE)
    TEMPERATURE = max(0.0, min(2.0, _raw_temp))
except (TypeError, ValueError):
    TEMPERATURE = 2.0


def _classify_openai_exception(exc: Exception) -> Exception:
    """Map upstream OpenAI exceptions into semantic application error classes."""
    sanitized = _sanitize(str(exc))
    if isinstance(exc, RateLimitError):
        return LLMRateLimitError(f"LLM API rate limited: {sanitized}")
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return LLMAuthenticationError(f"LLM API authentication/permission error: {sanitized}")
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        body = ""
        try:
            body = exc.response.text if exc.response is not None else ""
        except Exception:
            body = ""
        body = _sanitize(body)
        if status in (401, 403):
            return LLMAuthenticationError(f"LLM API forbidden/unauthorized {status}: {body}".strip())
        if status and status >= 500:
            return LLMServiceUnavailableError(
                f"LLM API server error {status}: {body}".strip()
            )
        return LLMError(f"LLM API status error {status}: {body}".strip())
    if isinstance(exc, APIConnectionError):
        return LLMServiceUnavailableError(f"LLM API connection error: {sanitized}")
    if isinstance(exc, APIError):
        return LLMError(f"LLM API error: {sanitized}")
    return LLMError(f"Unexpected LLM error: {sanitized}")


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


async def ask_llm(
    history: list[dict],
    customer_context: Optional[str] = None,
    max_tool_iterations: int = MAX_TOOL_ITERATIONS,
):
    """Sends conversation history to OpenAI-compatible Chat Completions API with automatic tool execution.

    LLM-level errors (rate limit, auth, connection) are raised as typed exceptions
    (LLMRateLimitError, LLMAuthenticationError, LLMServiceUnavailableError, LLMError)
    so callers can produce specific customer-facing messages.

    Tool execution errors are NOT raised — they are serialised as structured error
    payloads in the tool-result message so the LLM can decide how to respond
    (retry with different args, fall back to another tool, or explain to the customer).
    """
    tools = registry.get_llm_declarations()
    messages = _build_openai_messages(history, customer_context=customer_context)

    import json as _json

    response = None

    for iteration in range(max_tool_iterations):
        kwargs: dict = {
            "model": MODEL_NAME,
            "messages": messages,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": TEMPERATURE,
        }
        if tools:
            kwargs["tools"] = _format_tools(tools)
            kwargs["tool_choice"] = "auto"

        try:
            response = await client.chat.completions.create(**kwargs)
        except RateLimitError as exc:
            logger.warning("LLM rate limited on iteration {}: {}", iteration, _sanitize(str(exc)))
            raise _classify_openai_exception(exc)
        except APIStatusError as exc:
            status = getattr(exc, "status_code", None)
            logger.error("LLM API status error {} on iteration {}: {}", status, iteration, _sanitize(str(exc)))
            raise _classify_openai_exception(exc)
        except APIConnectionError as exc:
            logger.error("LLM connection error on iteration {}: {}", iteration, _sanitize(str(exc)))
            raise _classify_openai_exception(exc)
        except APIError as exc:
            logger.error("LLM API error on iteration {}: {}", iteration, _sanitize(str(exc)))
            raise _classify_openai_exception(exc)
        except Exception as exc:
            logger.exception("Unexpected error calling LLM on iteration {}", iteration)
            raise _classify_openai_exception(exc)

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

        if not tool_calls:
            logger.success(
                "LLM completion succeeded | iteration={} model={} finish_reason={} output_len={}",
                iteration,
                MODEL_NAME,
                finish_reason,
                len(output_text),
            )
            return response

        logger.info(
            "LLM requested {} tool call(s) on iteration {} | finish_reason={}",
            len(tool_calls),
            iteration,
            finish_reason,
        )

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
                logger.success("Tool '{}' [call_id={}] completed during iteration {}", name, call_id, iteration)
            except Exception as exc:
                # Do NOT propagate tool errors — serialise them as a structured
                # error tool-result so the LLM can reason about the failure and
                # decide whether to retry, use a fallback tool, or explain to the
                # customer.  Crashing the loop here would give the customer a
                # generic error message with no actionable context.
                error_detail = _sanitize(str(exc).strip() or repr(exc))
                logger.error(
                    "Tool '{}' [call_id={}] raised during iteration {}: {}",
                    name, call_id, iteration, error_detail,
                )
                tool_output_item = {
                    "output": _json.dumps({
                        "error": f"Tool '{name}' raised an unexpected exception.",
                        "error_type": type(exc).__name__,
                        "detail": error_detail,
                        "retry_useful": True,
                    })
                }

            if isinstance(tool_output_item, dict) and "output" in tool_output_item:
                tool_result_content = tool_output_item["output"]
            else:
                tool_result_content = str(tool_output_item)

            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": tool_result_content,
            })

    return response


# ---------------------------------------------------------------------------
# Backwards-compatibility alias — remove once all call-sites are updated.
# ---------------------------------------------------------------------------
ask_gpt = ask_llm
