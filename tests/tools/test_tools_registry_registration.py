"""Tests for tool registration in src/tools/registry.py."""

import pytest
from pydantic import BaseModel
from src.tools.registry import ToolRegistry


class DummySchema(BaseModel):
    query: str


def test_register_new_tool():
    reg = ToolRegistry()

    @reg.register("search_dummy", DummySchema)
    async def dummy_tool(payload: DummySchema):
        return {"result": payload.query}

    names = reg.get_registered_tool_names()
    assert "search_dummy" in names


def test_register_duplicate_tool_raises_value_error():
    reg = ToolRegistry()

    @reg.register("search_duplicate", DummySchema)
    async def tool1(payload: DummySchema):
        return {}

    with pytest.raises(ValueError, match="already registered"):
        @reg.register("search_duplicate", DummySchema)
        async def tool2(payload: DummySchema):
            return {}


def test_get_llm_declarations_returns_function_definitions():
    reg = ToolRegistry()

    @reg.register("weather", DummySchema)
    async def get_weather(payload: DummySchema):
        """Fetch weather data."""
        return {}

    decls = reg.get_llm_declarations()
    assert len(decls) == 1
    assert decls[0]["name"] == "weather"
    assert decls[0]["description"] == "Fetch weather data."
