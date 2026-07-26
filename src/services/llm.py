# src/services/llm.py

from openai import AsyncOpenAI

from src.configs.prompts import system_prompt
from src.configs.settings import OPENAI_API_KEY

client = AsyncOpenAI(
    api_key=OPENAI_API_KEY,
	base_url="https://api.groq.com/openai/v1"
)


async def ask_gpt(history: list[dict]):
    response = await client.responses.create(
        model="gpt-oss-120b",
        input=[
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
        ],
        store=False,
    )

    return responses