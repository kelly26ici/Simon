from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Type

from loguru import logger
from pydantic import BaseModel, ValidationError


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

    def register(self, name: str, schema: Type[BaseModel], *, strict: bool = True):
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
                "strict": strict,
            }
            self._tools[name] = Tool(name=name, schema=schema, handler=func, declaration=declaration)
            logger.success("Registered tool '{}'.", name)
            return func
        return decorator

    def get_llm_declarations(self) -> list[dict[str, Any]]:
        """Returns tool definitions in Responses API format."""
        return [tool.declaration for tool in self._tools.values()]

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
            logger.warning("Bad arguments for tool '{}': {}", tool_name, e)
            return self._output(call_id, {"error": f"Invalid arguments supplied to '{tool_name}'."})

        logger.debug("Executing tool '{}' with arguments {}", tool_name, validated_args.model_dump())

        try:
            result = await tool.handler(validated_args)
        except Exception:
            logger.exception("Handler for tool '{}' raised an unexpected error.", tool_name)
            return self._output(call_id, {"error": f"Tool '{tool_name}' failed during execution."})

        logger.success("Tool '{}' executed successfully.", tool_name)
        return self._output(call_id, result)

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