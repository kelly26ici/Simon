# src/services/llm.py

import os
from openai import AsyncOpenAI, RateLimitError, APIStatusError, APIConnectionError, APIError
from loguru import logger

from src.configs.prompts import system_prompt
from src.configs.settings import GROQ_API_KEY
from src.tools.registry import registry


client = AsyncOpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

MODEL_NAME = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
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
        return LLMRateLimitError(f"Groq rate limited: {exc}")
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        body = ""
        try:
            body = exc.response.text if exc.response is not None else ""
        except Exception:
            body = ""
        if status and status >= 500:
            return LLMServiceUnavailableError(
                f"Groq server error {status}: {body}".strip()
            )
        return LLMError(f"Groq API status error {status}: {body}".strip())
    if isinstance(exc, APIConnectionError):
        return LLMServiceUnavailableError(f"Groq connection error: {exc}")
    if isinstance(exc, APIError):
        return LLMError(f"Groq API error: {exc}")
    return LLMError(f"Unexpected LLM error: {exc}")


async def ask_gpt(history: list[dict], max_tool_iterations: int = MAX_TOOL_ITERATIONS):
    """Sends conversation history to the Groq Responses API with automatic tool execution."""
    tools = registry.get_llm_declarations()

    input_items = [
        {
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": system_prompt,
                }
            ],
        },
        *history,
    ]

    last_error: Exception | None = None
    for iteration in range(max_tool_iterations):
        kwargs: dict = {
            "model": MODEL_NAME,
            "input": input_items,
            "store": False,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await client.responses.create(**kwargs)
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

        # ── Structural logging: safe, no keys or private data ─────────────────
        status = getattr(response, "status", None)
        output = getattr(response, "output", None) or []
        output_types = [getattr(item, "type", None) if not isinstance(item, dict) else item.get("type") for item in output]
        output_text_value = getattr(response, "output_text", None)
        logger.info(
            "LLM response iteration={} status={} output_types={} output_text_len={}",
            iteration,
            status,
            output_types,
            len(output_text_value) if isinstance(output_text_value, str) else -1,
        )

        # ── Recover from a reasoning-model budget timeout ─────────────────────
        # gpt-oss-120b (reasoning model) may return status=incomplete with an
        # empty result when the reasoning chain hits its internal budget before
        # emitting the final message or function_call.  We re-inject a short
        # continuation prompt and let the next iteration resume from where the
        # model left off, instead of silently returning an empty response.
        if status == "incomplete" and not output_types:
            logger.warning(
                "LLM returned status=incomplete with empty output on iteration {}; "
                "injecting continuation prompt and retrying",
                iteration,
            )
            input_items.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Continue and produce your response now.",
                        }
                    ],
                }
            )
            continue
        # ──────────────────────────────────────────────────────────────────────

        function_calls = [
            item for item in output
            if getattr(item, "type", None) == "function_call" or (isinstance(item, dict) and item.get("type") == "function_call")
        ]

        if not function_calls:
            return response

        for fc in function_calls:
            call_id = getattr(fc, "call_id", None) or (fc.get("call_id") if isinstance(fc, dict) else None)
            name = getattr(fc, "name", None) or (fc.get("name") if isinstance(fc, dict) else None)
            args = getattr(fc, "arguments", None) or (fc.get("arguments") if isinstance(fc, dict) else None)

            input_items.append({
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": args if isinstance(args, str) else str(args),
            })

            try:
                tool_output_item = await registry.execute(call_id, name, args)
            except Exception as exc:
                logger.exception("Tool execution failed during LLM iteration {}", iteration)
                raise

            input_items.append(tool_output_item)

    # The loop body always raises on error paths; `last_error` is only set
    # inside `except` blocks that immediately raise, so it is guaranteed
    # `None` here. The assertion catches any future accidental removal of
    # a `raise` from an except branch, instead of silently returning a
    # stale response from a previous iteration.
    assert last_error is None, (
        "last_error was set but no exception was raised — "
        "a raise was removed from an except branch"
    )
    return response
