# src/services/llm.py

import os
from openai import AsyncOpenAI
from loguru import logger

from src.configs.prompts import system_prompt
from src.configs.settings import OPENROUTER_API_KEY
from src.tools.registry import registry

client = AsyncOpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

MODEL_NAME = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")


async def ask_gpt(history: list[dict], max_tool_iterations: int = 5):
    """Sends conversation history to OpenRouter Responses API with automatic tool execution."""
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

    for iteration in range(max_tool_iterations):
        kwargs = {
            "model": MODEL_NAME,
            "input": input_items,
            "store": False,
        }
        if tools:
            kwargs["tools"] = tools

        response = await client.responses.create(**kwargs)

        function_calls = [
            item for item in getattr(response, "output", [])
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
                "arguments": args if isinstance(args, str) else str(args)
            })

            tool_output_item = await registry.execute(call_id, name, args)
            input_items.append(tool_output_item)

    return response
