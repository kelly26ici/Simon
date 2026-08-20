"""
tests/test_nvidia_integration.py

Integration tests for NVIDIA NIM OpenAI-compatible API.
Tests live connectivity, model catalog availability, chat completions,
and function/tool calling with stepfun-ai/step-3.7-flash.
"""

import os
import pytest
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv(override=True)

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = "stepfun-ai/step-3.7-flash"


@pytest.fixture
def nvidia_client():
    if not NVIDIA_API_KEY:
        pytest.skip("NVIDIA_API_KEY is not configured")
    return AsyncOpenAI(
        api_key=NVIDIA_API_KEY,
        base_url=NVIDIA_BASE_URL,
        timeout=30.0,
    )


@pytest.mark.asyncio
async def test_nvidia_models_list(nvidia_client):
    """Verify NVIDIA NIM API key is authorized and returns available model list."""
    models_response = await nvidia_client.models.list()
    model_ids = [m.id for m in models_response.data]
    assert len(model_ids) > 0
    assert NVIDIA_MODEL in model_ids


@pytest.mark.asyncio
async def test_nvidia_chat_completion(nvidia_client):
    """Verify standard chat completion works with stepfun-ai/step-3.7-flash."""
    response = await nvidia_client.chat.completions.create(
        model=NVIDIA_MODEL,
        messages=[
            {"role": "user", "content": "Respond with exactly the single word: OK"}
        ],
        max_tokens=50,
        temperature=0.1,
    )
    choice = response.choices[0]
    assert choice.message.content is not None
    assert "OK" in choice.message.content.upper()


@pytest.mark.asyncio
async def test_nvidia_tool_calling(nvidia_client):
    """Verify NVIDIA model properly executes function/tool calling."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculate_mortgage",
                "description": "Calculate monthly mortgage payments in Kenya",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "property_price": {
                            "type": "number",
                            "description": "Total price in KES",
                        },
                        "down_payment_percentage": {
                            "type": "number",
                            "description": "Percentage down payment",
                        },
                    },
                    "required": ["property_price"],
                },
            },
        }
    ]

    response = await nvidia_client.chat.completions.create(
        model=NVIDIA_MODEL,
        messages=[
            {
                "role": "user",
                "content": "Please calculate the mortgage for a house priced at 15,000,000 KES with 20% down payment.",
            }
        ],
        tools=tools,
        tool_choice="auto",
        max_tokens=300,
    )

    choice = response.choices[0]
    assert choice.finish_reason in ("tool_calls", "stop")
    tool_calls = choice.message.tool_calls
    assert tool_calls is not None and len(tool_calls) > 0

    first_call = tool_calls[0]
    assert first_call.function.name == "calculate_mortgage"
    assert "15000000" in first_call.function.arguments or "15" in first_call.function.arguments
