"""Tests for tool execution in src/tools/registry.py."""

import json
import pytest
from pydantic import BaseModel, Field
from src.tools.registry import ToolRegistry


class AddSchema(BaseModel):
    a: int = Field(..., description="First number")
    b: int = Field(..., description="Second number")


@pytest.mark.asyncio
async def test_execute_tool_success():
    reg = ToolRegistry()

    @reg.register("add_numbers", AddSchema)
    async def add(payload: AddSchema):
        return {"sum": payload.a + payload.b}

    result = await reg.execute("call_123", "add_numbers", '{"a": 5, "b": 10}')
    assert result["type"] == "function_call_output"
    assert result["call_id"] == "call_123"
    assert json.loads(result["output"]) == {"sum": 15}


@pytest.mark.asyncio
async def test_execute_unregistered_tool_raises_key_error():
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        await reg.execute("call_456", "missing_tool", '{}')


@pytest.mark.asyncio
async def test_execute_invalid_schema_arguments_returns_error_output():
    reg = ToolRegistry()

    @reg.register("add_strict", AddSchema)
    async def add(payload: AddSchema):
        return {"sum": payload.a + payload.b}

    result = await reg.execute("call_789", "add_strict", '{"a": "not_an_int"}')
    assert result["type"] == "function_call_output"
    parsed = json.loads(result["output"])
    assert "error" in parsed
