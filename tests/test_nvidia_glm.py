"""Test the NVIDIA NIM API connection with the DeepSeek V4 Flash model.

Run with:
    uv run pytest tests/test_nvidia_glm.py
"""

import os
import pytest
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)

MODEL = "deepseek-ai/deepseek-v4-flash-0731"
BASE_URL = "https://integrate.api.nvidia.com/v1"


def test_nvidia_deepseek_connection() -> None:
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        pytest.skip("NVIDIA_API_KEY is not set")

    client = OpenAI(base_url=BASE_URL, api_key=api_key, timeout=30.0)

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": "Reply with exactly: NVIDIA test successful",
            }
        ],
        temperature=0.1,
        max_tokens=100,
    )

    message = completion.choices[0].message.content
    assert message is not None
    assert "successful" in message.lower() or "nvidia" in message.lower()


if __name__ == "__main__":
    test_nvidia_deepseek_connection()
    print("NVIDIA test passed successfully.")

