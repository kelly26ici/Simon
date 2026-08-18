# src/services/llm.py

import os
from openai import AsyncOpenAI, RateLimitError, APIStatusError, APIConnectionError, APIError
from loguru import logger

from src.configs.prompts import system_prompt
from src.configs.settings import NVIDIA_API_KEY
from src.tools.registry import registry


client = AsyncOpenAI(
    api_key=NVIDIA_API_KEY,
    base_url="https://integrate.api.nvidia.com/v1",
)

MODEL_NAME = os.getenv("LLM_MODEL", "stepfun-ai/step-3.7-flash")
MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "32768"))
MAX_TOOL_ITERATIONS = int(os.getenv("LLM_MAX_TOOL_ITERATIONS", "10"))


class LLMRateLimitError(Exception):
    """Raised when the upstream LLM returns 429 or rate-limit-like responses."""


class LLMServiceUnavailableError(Exception):
    """Raised when the upstream LLM is unreachable or returns 5xx."""


class LLMError(Exception):
    """Generic fallback for unexpected LLM/API failures."""


def _classify_openai_exception(exc: Exception) -> Exception:
    if isinstance(exc, RateLimitError):
        return LLMRateLimitError(f"NVIDIA API rate limited: {exc}")
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        body = ""
        try:
            body = exc.response.text if exc.response is not None else ""
        except Exception:
            body = ""
        if status and status >= 500:
            return LLMServiceUnavailableError(
                f"NVIDIA API server error {status}: {body}".strip()
            )
        return LLMError(f"NVIDIA API status error {status}: {body}".strip())
    if isinstance(exc, APIConnectionError):
        return LLMServiceUnavailableError(f"NVIDIA API connection error: {exc}")
    if isinstance(exc, APIError):
        return LLMError(f"NVIDIA API error: {exc}")
    return LLMError(f"Unexpected LLM error: {exc}")


def _build_openai_messages(history: list[dict]) -> list[dict]:
    """Builds standard OpenAI Chat Completion messages from history."""
    messages = [
        {
            "role": "system",
            "content": system_prompt,
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

        msg_dict = {"role": role, "content": content_str}

        if "tool_calls" in item:
            msg_dict["tool_calls"] = item["tool_calls"]
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


async def ask_gpt(history: list[dict], max_tool_iterations: int = MAX_TOOL_ITERATIONS):
    """Sends conversation history to NVIDIA NIM Chat Completions API with automatic tool execution."""
    tools = registry.get_llm_declarations()
    messages = _build_openai_messages(history)

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
            "tool_calls": tool_calls,
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
