"""Tests for CLI utility commands in src/cli.py."""

import pytest
from unittest.mock import patch, AsyncMock
from src.cli import cmd_status


@pytest.mark.asyncio
async def test_cmd_status_runs_without_crashing(capsys):
    with patch("src.cli.db.search_properties", new=AsyncMock(return_value=[])), \
         patch("src.cli.qdrant_client.get_collections", new=AsyncMock(side_effect=Exception("mocked"))), \
         patch("src.cli.get_embeddings", new=AsyncMock(return_value=[])), \
         patch("src.cli.ask_llm", new=AsyncMock(return_value="OK")):
        await cmd_status()
        captured = capsys.readouterr()
        assert "HEALTH CHECK" in captured.out
