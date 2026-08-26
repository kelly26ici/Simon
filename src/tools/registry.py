from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Type

from loguru import logger
from pydantic import BaseModel, ValidationError


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


@dataclass(slots=True)
class Tool:
    """Represents a single LLM tool."""
    name: str
    schema: Type[BaseModel]
    handler: Callable[[BaseModel], Awaitable[Any]]
    declaration: dict[str, Any]


class ToolRegistry:
    """Registers, validates and executes LLM tools for the Responses API."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, schema: Type[BaseModel], *, strict: bool = False):
        """
        Decorator used to register a tool.
        Example:
            @registry.register("weather", WeatherSchema)
            async def weather(payload: WeatherSchema):
                ...
        """
        def decorator(func: Callable[[BaseModel], Awaitable[Any]]):
            if name in self._tools:
                logger.warning("Attempted to register duplicate tool '{}'.", name)
                raise ValueError(f"Tool '{name}' is already registered.")

            params_schema = schema.model_json_schema()
            if strict:
                params_schema["additionalProperties"] = False

            declaration = {
                "type": "function",
                "name": name,
                "description": (func.__doc__ or "").strip(),
                "parameters": params_schema,
            }
            if strict:
                declaration["strict"] = True

            self._tools[name] = Tool(name=name, schema=schema, handler=func, declaration=declaration)
            logger.success("Registered tool '{}'.", name)
            return func
        return decorator

    def get_llm_declarations(self) -> list[dict[str, Any]]:
        """Returns tool definitions in Responses API format."""
        return [tool.declaration for tool in self._tools.values()]

    def get_registered_tool_names(self) -> list[str]:
        """Returns the list of registered tool names."""
        return list(self._tools.keys())

    def get(self, name: str) -> Tool:
        """Returns a registered tool."""
        tool = self._tools.get(name)
        if tool is None:
            logger.warning("Unknown tool requested: '{}'.", name)
            raise KeyError(f"Tool '{name}' is not registered.")
        return tool

    async def execute(self, call_id: str, tool_name: str, raw_arguments: str) -> dict[str, Any]:
        """
        Handles a single `function_call` item from a Responses API output,
        and returns a `function_call_output` item ready to append to input.
        """
        tool = self.get(tool_name)  # KeyError bubbles up untouched

        try:
            args_dict = json.loads(raw_arguments)
            validated_args = tool.schema.model_validate(args_dict)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("Bad arguments for tool '{}': {}", tool_name, _sanitize(str(e)))
            return self._output(call_id, {"error": f"Invalid arguments supplied to '{tool_name}'."})

        logger.debug("Executing tool '{}' with arguments {}", tool_name, validated_args.model_dump())

        try:
            result = await tool.handler(validated_args)
        except Exception as exc:
            logger.exception("Handler for tool '{}' raised an unexpected error.", tool_name)
            # Surface a legible, actionable cause to the model. The previous generic
            # message ("Tool 'X' failed during execution.") gave the agent nothing to
            # act on, so it would retry the same doomed tool in a loop. We keep the
            # detail short and structured; classify the common infra failure modes so
            # the agent can tell the customer "the database is unavailable" vs "the
            # data isn't there" and stop retrying.
            error_cls = type(exc).__name__
            detail = _sanitize(str(exc).strip() or repr(exc))
            cause = self._classify_error(exc)
            return self._output(call_id, {
                "error": f"Tool '{tool_name}' failed: {cause}",
                "error_type": error_cls,
                "detail": detail,
                "retry_useful": cause != "database_unreachable",
            })

        logger.success("Tool '{}' executed successfully.", tool_name)
        return self._output(call_id, result)

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        """Map an exception to a short, agent-actionable cause label.

        The categories drive `retry_useful`: a transient DNS/connection failure
        is worth a retry; a missing-table / missing-row error is not, because
        retrying the exact same call will produce the exact same failure and
        the agent should stop and inform the customer instead.
        """
        name = type(exc).__name__
        msg = str(exc)

        # Supabase/PostgREST schema-cache misses (e.g. PGRST205 'Could not find
        # the table ... in the schema cache') and similar forced-50 lookups.
        if "PGRST205" in msg or "schema cache" in msg:
            return "database_table_missing"
        if name == "APIError" and "PGRST" in msg:
            return "database_query_rejected"

        # Connectivity / DNS failures (httpx.ConnectError, gaierror, etc.).
        if name in {"ConnectError", "ConnectTimeout", "ReadTimeout", "TimeoutError"}:
            return "database_unreachable"
        if "Name or service not known" in msg or "gaierror" in msg.lower():
            return "database_unreachable"

        return "unexpected_error"

    @staticmethod
    def _output(call_id: str, result: Any) -> dict[str, Any]:
        # My tool handlers return plain strings, plain dicts, OR pydantic
        # models (send_stk_push/check_transaction_status both do) - the
        # original version here did json.dumps(result) for anything that
        # wasn't a string, which blows up on a BaseModel instance since
        # json.dumps has no idea how to serialize it. Every successful
        # M-Pesa tool call was going to crash on this line.
        if isinstance(result, str):
            output = result
        elif isinstance(result, BaseModel):
            output = result.model_dump_json()
        else:
            output = json.dumps(result)

        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output,
        }


registry = ToolRegistry()