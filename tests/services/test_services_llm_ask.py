"""Tests for ask_llm function in src/services/llm.py."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.llm import ask_llm


@pytest.mark.asyncio
async def test_ask_llm_returns_text_response():
    fake_choice = MagicMock()
    fake_choice.message.content = "I found 3 great houses in Karen."
    fake_choice.message.tool_calls = None
    fake_choice.finish_reason = "stop"
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=fake_response)

    with patch("src.services.llm.client", mock_client):
        result = await ask_llm(
            history=[{"role": "user", "content": "Find houses in Karen"}],
            customer_context="Customer: Alice",
        )
        assert result.output_text == "I found 3 great houses in Karen."
