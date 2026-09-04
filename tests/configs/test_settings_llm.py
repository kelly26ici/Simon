"""Tests for LLM-related settings (src/configs/settings.py)."""

import src.configs.settings as s


def test_groq_stt_model_default():
    assert s.GROQ_STT_MODEL in ("whisper-large-v3", "whisper-medium")


def test_llm_temperature_is_str():
    assert isinstance(s.LLM_TEMPERATURE, str)


def test_llm_provider_is_str():
    assert isinstance(s.LLM_PROVIDER, str)


def test_llm_model_is_str():
    assert isinstance(s.LLM_MODEL, str)


def test_poolside_api_key_is_str():
    assert isinstance(s.POOLSIDE_API_KEY, str)


def test_poolside_base_url_is_str():
    assert isinstance(s.POOLSIDE_BASE_URL, str)


def test_poolside_base_url_is_inference_endpoint():
    assert s.POOLSIDE_BASE_URL.startswith("https://inference.poolside.ai")
