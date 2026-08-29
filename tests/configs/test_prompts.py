"""Tests for src/configs/prompts.py."""

from src.configs.prompts import system_prompt


def test_system_prompt_is_non_empty_string():
    assert isinstance(system_prompt, str) and len(system_prompt.strip()) > 0


def test_system_prompt_mentions_simon():
    assert "Simon" in system_prompt


def test_system_prompt_mentions_realtors_round_tables():
    assert "Realtors Round Tables" in system_prompt


def test_system_prompt_lists_search_properties_tool():
    assert "search_properties" in system_prompt


def test_system_prompt_lists_calculate_mortgage_tool():
    assert "calculate_mortgage" in system_prompt


def test_system_prompt_lists_notify_owner_tool():
    assert "notify_owner" in system_prompt


def test_system_prompt_contains_kenya():
    assert "Kenya" in system_prompt


def test_system_prompt_has_whatsapp_formatting_guidance():
    assert "WhatsApp" in system_prompt


def test_system_prompt_has_tone_section():
    assert "Tone" in system_prompt or "tone" in system_prompt
