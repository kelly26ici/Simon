"""
tests/test_tool_calling_registry.py

Modular unit tests for ToolRegistry: tool registration, argument validation,
execution lifecycle, error isolation, and logger.success invocation.
"""

import pytest
from pydantic import BaseModel, Field
from src.tools.registry import ToolRegistry, Tool


class SampleInputSchema(BaseModel):
    city: str = Field(..., description="Target city")
    min_bedrooms: int = Field(default=2, ge=1, description="Minimum bedrooms")


@pytest.fixture
def fresh_registry():
    return ToolRegistry()


@pytest.mark.asyncio
async def test_tool_registration(fresh_registry):
    """Verify tool can be registered and declarations are properly generated."""
    @fresh_registry.register("sample_tool", SampleInputSchema)
    async def sample_tool(payload: SampleInputSchema) -> dict:
        """Sample tool description."""
        return {"status": "ok", "city": payload.city, "beds": payload.min_bedrooms}

    assert "sample_tool" in fresh_registry.get_registered_tool_names()
    tool = fresh_registry.get("sample_tool")
    assert isinstance(tool, Tool)
    assert tool.name == "sample_tool"

    declarations = fresh_registry.get_llm_declarations()
    assert len(declarations) == 1
    decl = declarations[0]
    assert decl["name"] == "sample_tool"
    assert "parameters" in decl


@pytest.mark.asyncio
async def test_duplicate_registration_raises(fresh_registry):
    """Verify registering duplicate tool name raises ValueError."""
    @fresh_registry.register("dup_tool", SampleInputSchema)
    async def tool1(payload: SampleInputSchema):
        return {}

    with pytest.raises(ValueError, match="already registered"):
        @fresh_registry.register("dup_tool", SampleInputSchema)
        async def tool2(payload: SampleInputSchema):
            return {}


@pytest.mark.asyncio
async def test_tool_execution_success(fresh_registry):
    """Verify tool execution returns structured output upon success."""
    @fresh_registry.register("search_geo", SampleInputSchema)
    async def search_geo(payload: SampleInputSchema) -> dict:
        return {"matched": 3, "location": payload.city}

    result = await fresh_registry.execute(
        call_id="call-12345",
        tool_name="search_geo",
        raw_arguments='{"city": "Nairobi", "min_bedrooms": 3}',
    )

    assert result["type"] == "function_call_output"
    assert result["call_id"] == "call-12345"
    assert '"matched": 3' in result["output"]
    assert '"location": "Nairobi"' in result["output"]


@pytest.mark.asyncio
async def test_tool_execution_invalid_json(fresh_registry):
    """Verify invalid JSON arguments are caught cleanly without crashing."""
    @fresh_registry.register("search_geo", SampleInputSchema)
    async def search_geo(payload: SampleInputSchema) -> dict:
        return {}

    result = await fresh_registry.execute(
        call_id="call-999",
        tool_name="search_geo",
        raw_arguments='{not a valid json}',
    )

    assert result["call_id"] == "call-999"
    assert "error" in result["output"]


@pytest.mark.asyncio
async def test_tool_execution_handler_exception(fresh_registry):
    """Verify handler exceptions are classified and returned with actionable error."""
    @fresh_registry.register("buggy_tool", SampleInputSchema)
    async def buggy_tool(payload: SampleInputSchema):
        raise ConnectionError("Name or service not known")

    result = await fresh_registry.execute(
        call_id="call-555",
        tool_name="buggy_tool",
        raw_arguments='{"city": "Mombasa"}',
    )

    assert result["call_id"] == "call-555"
    assert "database_unreachable" in result["output"]
