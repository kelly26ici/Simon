import pytest
from unittest.mock import AsyncMock, patch
from src.services.llm import ask_gpt

@pytest.mark.asyncio
async def test_ask_gpt_basic():
    mock_response = AsyncMock()
    mock_response.output = []
    mock_response.output_text = "Hello there!"

    with patch("src.services.llm.client.responses.create", return_value=mock_response):
        res = await ask_gpt([{"role": "user", "content": [{"type": "input_text", "text": "Hi"}]}])
        assert res.output_text == "Hello there!"