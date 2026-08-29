# src/services/llm.py

from __future__ import annotations

import asyncio
import os
import re
import time
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
    LLM_RESET_COOLDOWN_SECONDS,
)
from src.configs.constants import (
    GROQ_MODEL,
    OPENROUTER_MODEL,
    NVIDIA_MODEL,
    DEFAULT_NVIDIA_MODEL,
    NVIDIA_CASCADE_MODELS,
    MODEL_RESET_COOLDOWN_SECONDS,
)
from src.tools.registry import registry


class LLMRateLimitError(Exception):
    """Raised when the upstream LLM returns 429 or rate-limit-like responses."""


class LLMServiceUnavailableError(Exception):
    """Raised when the upstream LLM is unreachable or returns 5xx."""


class LLMAuthenticationError(Exception):
    """Raised when the upstream LLM returns 401/403 (invalid key or forbidden/credits exhausted)."""


class LLMError(Exception):
    """Generic fallback for unexpected LLM/API failures."""


_INVALID_NVIDIA_MODEL_OVERRIDES = frozenset(
    {
        "stepfun-ai/step-3.7-flash",
        "nvidia_nim/poolside/laguna-xs-2.1",
        "nvidia_nim/deepseek-ai/deepseek-v4-flash-0731",
    }
)


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


class ModelCascadeManager:
    """Manages dynamic LLM model failover, auto-shifting on error, and 1-hour cooldown auto-reset."""

    def __init__(
        self,
        primary_model: str = DEFAULT_NVIDIA_MODEL,
        cascade_models: list[str] | None = None,
        reset_cooldown_seconds: float = MODEL_RESET_COOLDOWN_SECONDS,
    ):
        self.primary_model = primary_model
        raw_cascade = list(cascade_models or NVIDIA_CASCADE_MODELS)
        if self.primary_model not in raw_cascade:
            raw_cascade.insert(0, self.primary_model)
        else:
            # Ensure primary_model is at index 0
            raw_cascade.remove(self.primary_model)
            raw_cascade.insert(0, self.primary_model)
        self.cascade: list[str] = raw_cascade
        self.reset_cooldown_seconds: float = reset_cooldown_seconds
        self._current_index: int = 0
        self._last_demote_time: float | None = None

    def _check_auto_reset(self) -> None:
        """If 1 hour has elapsed since last demote/failover, auto-reset back to primary model."""
        if self._current_index != 0 and self._last_demote_time is not None:
            elapsed = time.monotonic() - self._last_demote_time
            if elapsed >= self.reset_cooldown_seconds:
                old_model = self.cascade[self._current_index]
                self._current_index = 0
                self._last_demote_time = None
                logger.info(
                    "Auto-reset cooldown expired ({:.0f}s >= {:.0f}s) | Reshifting active LLM model from '{}' back to primary '{}'",
                    elapsed,
                    self.reset_cooldown_seconds,
                    old_model,
                    self.primary_model,
                )

    def get_active_model(self) -> str:
        """Returns the current active model ID."""
        self._check_auto_reset()
        if 0 <= self._current_index < len(self.cascade):
            return self.cascade[self._current_index]
        return self.primary_model

    def get_candidates(self) -> list[str]:
        """Returns candidate model IDs in priority order for the current in-flight request."""
        self._check_auto_reset()
        idx = self._current_index
        return self.cascade[idx:] + self.cascade[:idx]

    def record_failure(self, failed_model: str, exc: Exception) -> str:
        """Advances active model to the next one in the cascade upon error and records demote timestamp."""
        sanitized_err = _sanitize(str(exc))
        err_type = type(exc).__name__

        if failed_model in self.cascade:
            idx = self.cascade.index(failed_model)
            next_idx = (idx + 1) % len(self.cascade)
            self._current_index = next_idx
            self._last_demote_time = time.monotonic()
            next_model = self.cascade[next_idx]
            logger.warning(
                "LLM model '{}' encountered {} ({}). Auto-shifting active model to next in cascade: '{}'. Auto-reshift to '{}' scheduled in {:.0f}m.",
                failed_model,
                err_type,
                sanitized_err,
                next_model,
                self.primary_model,
                self.reset_cooldown_seconds / 60,
            )
            return next_model
        return self.get_active_model()

    def record_success(self, model: str) -> None:
        """Logs successful generation with model."""
        logger.debug("LLM model '{}' generation succeeded.", model)

    def reset_to_primary(self) -> None:
        """Resets active model back to primary top model."""
        self._current_index = 0
        self._last_demote_time = None
        logger.info("Manually reset active model to primary: '{}'", self.primary_model)


# Global cascade manager instance
cascade_manager = ModelCascadeManager(
    primary_model=DEFAULT_NVIDIA_MODEL,
    cascade_models=NVIDIA_CASCADE_MODELS,
    reset_cooldown_seconds=float(LLM_RESET_COOLDOWN_SECONDS),
)


def _nvidia_model() -> str:
    if LLM_MODEL and LLM_MODEL not in _INVALID_NVIDIA_MODEL_OVERRIDES:
        return LLM_MODEL
    if LLM_MODEL in _INVALID_NVIDIA_MODEL_OVERRIDES:
        logger.warning(
            "Ignoring invalid NVIDIA model override '{}' and using '{}'",
            LLM_MODEL,
            cascade_manager.get_active_model(),
        )
    return cascade_manager.get_active_model()


def resolve_llm_config() -> Tuple[str, str, str, str]:
    """
    Resolves the (provider, base_url, api_key, model_name) to use based on configuration
    and available API keys.
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
        return "nvidia", "https://integrate.api.nvidia.com/v1", NVIDIA_API_KEY, _nvidia_model()

    # 3. Auto-detection priority:
    # NVIDIA → OpenRouter → Groq
    if NVIDIA_API_KEY:
        return "nvidia", "https://integrate.api.nvidia.com/v1", NVIDIA_API_KEY, _nvidia_model()
    if OPENROUTER_API_KEY:
        return "openrouter", "https://openrouter.ai/api/v1", OPENROUTER_API_KEY, LLM_MODEL or OPENROUTER_MODEL
    if GROQ_API_KEY:
        return "groq", "https://api.groq.com/openai/v1", GROQ_API_KEY, LLM_MODEL or GROQ_MODEL

    return "nvidia", "https://integrate.api.nvidia.com/v1", "", _nvidia_model()


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
    TEMPERATURE = 0.7


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

        if role == "assistant" and "tool_calls" in item and not content_str:
            msg_dict["content"] = None
        else:
            msg_dict["content"] = content_str

        if "tool_calls" in item:
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


def _clean_output_text(raw_text: str | None, msg: Any = None) -> str:
    """Extracts and sanitizes assistant text, stripping <think> tags and pulling reasoning if needed."""
    text = raw_text or ""
    if not text and msg is not None:
        reasoning = getattr(msg, "reasoning_content", None)
        if reasoning:
            text = str(reasoning)

    if text:
        # Strip <think>...</think> chain-of-thought blocks so user receives clean answer
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return text


async def _execute_turn_with_model(
    model_name: str,
    base_messages: list[dict],
    tools: list[dict],
    max_tool_iterations: int,
) -> Any:
    """Executes a full turn (including tool calling loop) using a specific model."""
    import json as _json

    messages = [dict(m) for m in base_messages]
    response = None

    for iteration in range(max_tool_iterations):
        kwargs: dict = {
            "model": model_name,
            "messages": messages,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": TEMPERATURE,
        }
        if tools:
            kwargs["tools"] = _format_tools(tools)
            kwargs["tool_choice"] = "auto"

        response = await client.chat.completions.create(**kwargs)

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise LLMError(f"Model '{model_name}' returned empty choices list.")

        first_choice = choices[0]
        msg = getattr(first_choice, "message", None)
        finish_reason = getattr(first_choice, "finish_reason", None)

        raw_output_text = getattr(msg, "content", None) or ""
        output_text = _clean_output_text(raw_output_text, msg)
        setattr(response, "output_text", output_text)

        tool_calls = getattr(msg, "tool_calls", None) or []

        if not tool_calls:
            # If no tools called and output_text is empty, raise to trigger next cascade model
            if not output_text and finish_reason != "tool_calls":
                raise LLMError(f"Model '{model_name}' returned empty content with finish_reason={finish_reason}")

            logger.success(
                "LLM completion succeeded | model={} iteration={} finish_reason={} output_len={}",
                model_name,
                iteration,
                finish_reason,
                len(output_text),
            )
            return response

        logger.info(
            "LLM requested {} tool call(s) on iteration {} | model={} finish_reason={}",
            len(tool_calls),
            iteration,
            model_name,
            finish_reason,
        )

        assistant_msg = {
            "role": "assistant",
            "content": raw_output_text or None,
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


async def ask_llm(
    history: list[dict],
    customer_context: Optional[str] = None,
    max_tool_iterations: int = MAX_TOOL_ITERATIONS,
):
    """Sends conversation history to OpenAI-compatible Chat Completions API with automatic tool execution,
    in-flight model cascading failover, and automatic 1-hour cooldown reset back to primary (Kimi K3).

    If an active model encounters any error (rate limit 429, 5xx, timeout, or auth error),
    the system automatically and seamlessly fails over to the next capable model in the cascade
    to answer the user's message without asking them to re-type.
    """
    tools = registry.get_llm_declarations()
    messages = _build_openai_messages(history, customer_context=customer_context)

    # In explicit custom or non-nvidia modes with fixed override, use single model
    if LLM_BASE_URL and LLM_API_KEY:
        candidate_models = [LLM_MODEL or "gpt-4o-mini"]
    elif LLM_PROVIDER and LLM_PROVIDER.lower() in ("groq", "openrouter"):
        candidate_models = [MODEL_NAME]
    else:
        candidate_models = cascade_manager.get_candidates()

    last_exc: Optional[Exception] = None

    for attempt_idx, model_name in enumerate(candidate_models):
        logger.info(
            "Attempting LLM completion with model '{}' (candidate {}/{})",
            model_name,
            attempt_idx + 1,
            len(candidate_models),
        )
        try:
            response = await _execute_turn_with_model(
                model_name=model_name,
                base_messages=messages,
                tools=tools,
                max_tool_iterations=max_tool_iterations,
            )
            cascade_manager.record_success(model_name)
            return response
        except (RateLimitError, APIStatusError, APIConnectionError, APIError, Exception) as exc:
            last_exc = exc
            logger.warning(
                "Model '{}' failed during execution: {}. Failing over to next candidate in cascade...",
                model_name,
                _sanitize(str(exc)),
            )
            cascade_manager.record_failure(model_name, exc)
            continue

    # If all models in the cascade failed
    if last_exc:
        logger.error("All candidate models in cascade exhausted. Final error: {}", _sanitize(str(last_exc)))
        raise _classify_openai_exception(last_exc)

    raise LLMError("LLM failed to return a response from any model in cascade.")


# ---------------------------------------------------------------------------
# Backwards-compatibility alias
# ---------------------------------------------------------------------------
ask_gpt = ask_llm
