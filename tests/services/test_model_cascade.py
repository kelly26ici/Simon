"""Tests for ModelCascadeManager and in-flight model failover in src/services/llm.py."""

import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from openai import RateLimitError, APIStatusError
import httpx

from src.services.llm import (
    ModelCascadeManager,
    ask_llm,
    _clean_output_text,
    LLMRateLimitError,
    LLMError,
    resolve_llm_config,
)
from src.configs.constants import DEFAULT_NVIDIA_MODEL, NVIDIA_CASCADE_MODELS
from src.configs.constants import DEFAULT_POOLSIDE_MODEL, POOLSIDE_CASCADE_MODELS
from src.configs import settings as s


def test_cascade_manager_initialization():
    """Manager must start with primary model (Kimi K3) as default."""
    manager = ModelCascadeManager(
        primary_model="moonshotai/kimi-k3",
        cascade_models=["moonshotai/kimi-k3", "meta/llama-3.2-11b-vision-instruct", "openai/gpt-oss-20b"],
        reset_cooldown_seconds=3600.0,
    )
    assert manager.get_active_model() == "moonshotai/kimi-k3"
    assert manager.get_candidates() == ["moonshotai/kimi-k3", "meta/llama-3.2-11b-vision-instruct", "openai/gpt-oss-20b"]


def test_cascade_manager_record_failure_shifts_to_next():
    """Failing a model advances the active pointer to the next model in cascade."""
    manager = ModelCascadeManager(
        primary_model="moonshotai/kimi-k3",
        cascade_models=["moonshotai/kimi-k3", "meta/llama-3.2-11b-vision-instruct", "openai/gpt-oss-20b"],
        reset_cooldown_seconds=3600.0,
    )
    next_model = manager.record_failure("moonshotai/kimi-k3", Exception("Rate limited"))
    assert next_model == "meta/llama-3.2-11b-vision-instruct"
    assert manager.get_active_model() == "meta/llama-3.2-11b-vision-instruct"
    assert manager.get_candidates() == ["meta/llama-3.2-11b-vision-instruct", "openai/gpt-oss-20b", "moonshotai/kimi-k3"]


def test_cascade_manager_auto_reset_after_cooldown():
    """After 1-hour cooldown, active model automatically shifts back to primary."""
    manager = ModelCascadeManager(
        primary_model="moonshotai/kimi-k3",
        cascade_models=["moonshotai/kimi-k3", "meta/llama-3.2-11b-vision-instruct", "openai/gpt-oss-20b"],
        reset_cooldown_seconds=3600.0,
    )
    # Demote model
    manager.record_failure("moonshotai/kimi-k3", Exception("Temporary 429"))
    assert manager.get_active_model() == "meta/llama-3.2-11b-vision-instruct"

    # Simulate 3601 seconds elapsed since demote
    manager._last_demote_time = time.monotonic() - 3601.0

    # Next check should auto-reset to primary Kimi K3
    assert manager.get_active_model() == "moonshotai/kimi-k3"
    assert manager.get_candidates()[0] == "moonshotai/kimi-k3"


def test_cascade_manager_manual_reset():
    """Manual reset returns index to 0 immediately."""
    manager = ModelCascadeManager(
        primary_model="moonshotai/kimi-k3",
        cascade_models=["moonshotai/kimi-k3", "meta/llama-3.2-11b-vision-instruct"],
    )
    manager.record_failure("moonshotai/kimi-k3", Exception("429"))
    assert manager.get_active_model() == "meta/llama-3.2-11b-vision-instruct"

    manager.reset_to_primary()
    assert manager.get_active_model() == "moonshotai/kimi-k3"


def test_clean_output_text_strips_think_tags():
    """Reasoning chain-of-thought in <think> tags must be stripped."""
    raw = "<think>Let me calculate the square footage.</think>The apartment is 120 sqm."
    cleaned = _clean_output_text(raw)
    assert cleaned == "The apartment is 120 sqm."


def test_clean_output_text_fallback_to_reasoning_content():
    """If content is None, pull from reasoning_content."""
    msg = MagicMock()
    msg.reasoning_content = "Hello there!"
    cleaned = _clean_output_text(None, msg)
    assert cleaned == "Hello there!"


@pytest.mark.asyncio
async def test_ask_llm_in_flight_failover_success():
    """When the first model fails with 429, ask_llm must immediately try the next model and succeed."""
    mock_manager = ModelCascadeManager(
        primary_model="moonshotai/kimi-k3",
        cascade_models=["moonshotai/kimi-k3", "meta/llama-3.2-11b-vision-instruct"],
    )

    success_choice = MagicMock()
    success_choice.message.content = "Here is your answer from fallback model."
    success_choice.message.tool_calls = None
    success_choice.finish_reason = "stop"
    success_response = MagicMock()
    success_response.choices = [success_choice]

    mock_client = AsyncMock()

    # First call (kimi-k3) raises 429, second call (llama-3.2-11b) returns success
    req = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    resp_429 = httpx.Response(429, request=req, text='{"error":"Rate limited"}')
    rate_err = RateLimitError("Rate limited", response=resp_429, body={"error": "Rate limited"})

    mock_client.chat.completions.create = AsyncMock(side_effect=[
        rate_err,
        success_response,
    ])

    with patch("src.services.llm.client", mock_client), \
         patch("src.services.llm.cascade_manager", mock_manager):
        res = await ask_llm(history=[{"role": "user", "content": "Hello"}])
        assert res.output_text == "Here is your answer from fallback model."
        assert mock_client.chat.completions.create.call_count == 2
        # Verify active model shifted
        assert mock_manager.get_active_model() == "meta/llama-3.2-11b-vision-instruct"


@pytest.mark.asyncio
async def test_ask_llm_all_models_fail_raises():
    """When all models in cascade fail, classified exception is raised."""
    mock_manager = ModelCascadeManager(
        primary_model="model-a",
        cascade_models=["model-a", "model-b"],
    )

    req = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/chat/completions")
    resp_429 = httpx.Response(429, request=req, text='{"error":"Rate limited"}')
    rate_err = RateLimitError("Rate limited", response=resp_429, body={"error": "Rate limited"})

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=[rate_err, rate_err])

    with patch("src.services.llm.client", mock_client), \
         patch("src.services.llm.cascade_manager", mock_manager):
        with pytest.raises(LLMRateLimitError):
            await ask_llm(history=[{"role": "user", "content": "Hello"}])


# ---------------------------------------------------------------------------
# Poolside AI cascade and provider tests
# ---------------------------------------------------------------------------


def test_poolside_default_model_is_laguna_xs():
    """The primary poolside model should be the fastest (XS 2.1)."""
    assert DEFAULT_POOLSIDE_MODEL == "poolside/laguna-xs-2.1"


def test_poolside_cascade_starts_with_poolside_models():
    """First entries in the poolside cascade must be poolside models."""
    poolside_entries = [m for m in POOLSIDE_CASCADE_MODELS if m.startswith("poolside/")]
    assert len(poolside_entries) >= 3
    # The first entry must be a poolside model
    assert POOLSIDE_CASCADE_MODELS[0].startswith("poolside/")


def test_poolside_cascade_poolside_before_others():
    """All poolside models must appear before any non-poolside model in the cascade."""
    first_non_poolside = next(
        (i for i, m in enumerate(POOLSIDE_CASCADE_MODELS) if not m.startswith("poolside/")),
        len(POOLSIDE_CASCADE_MODELS),
    )
    poolside_indices = [i for i, m in enumerate(POOLSIDE_CASCADE_MODELS) if m.startswith("poolside/")]
    assert all(idx < first_non_poolside for idx in poolside_indices)


def test_poolside_cascade_fastest_first():
    """Poolide models in the cascade must be ordered fastest → slowest.

    XS 2.1 (33B/3B) → S 2.1 (118B/8B) → M.1 (225B/23B)
    """
    poolside_models = [m for m in POOLSIDE_CASCADE_MODELS if m.startswith("poolside/")]
    xs_idx = poolside_models.index("poolside/laguna-xs-2.1")
    s_idx = poolside_models.index("poolside/laguna-s-2.1")
    m_idx = poolside_models.index("poolside/laguna-m.1")
    assert xs_idx < s_idx < m_idx


def test_no_minimax_m3_in_poolside_cascade():
    """minimaxai/minimax-m3 must NOT appear in the poolside cascade."""
    assert "minimaxai/minimax-m3" not in POOLSIDE_CASCADE_MODELS


def test_no_minimax_m3_in_nvidia_cascade():
    """minimaxai/minimax-m3 must NOT appear in the NVIDIA cascade."""
    assert "minimaxai/minimax-m3" not in NVIDIA_CASCADE_MODELS


def test_poolside_cascade_manager_uses_poolside_models():
    """The poolside cascade manager's candidates start with poolside models."""
    from src.services.llm import poolside_cascade_manager
    candidates = poolside_cascade_manager.get_candidates()
    assert candidates[0] == DEFAULT_POOLSIDE_MODEL
    assert candidates[0].startswith("poolside/")


def test_poolside_cascade_manager_primary():
    """The poolside cascade manager's primary model is Laguna XS 2.1."""
    from src.services.llm import poolside_cascade_manager
    assert poolside_cascade_manager.primary_model == DEFAULT_POOLSIDE_MODEL


def test_resolve_llm_config_poolside_provider():
    """When POOLSIDE_API_KEY is set and no other key, poolside should be selected."""
    with patch("src.services.llm.POOLSIDE_API_KEY", "sky_test"), \
         patch("src.services.llm.NVIDIA_API_KEY", None), \
         patch("src.services.llm.OPENROUTER_API_KEY", None), \
         patch("src.services.llm.GROQ_API_KEY", None), \
         patch("src.services.llm.LLM_BASE_URL", ""), \
         patch("src.services.llm.LLM_API_KEY", ""), \
         patch("src.services.llm.LLM_PROVIDER", ""):
        provider, base_url, api_key, model = resolve_llm_config()
        assert provider == "poolside"
        assert base_url == s.POOLSIDE_BASE_URL
        assert api_key == "sky_test"


def test_resolve_llm_config_poolside_explicit_provider():
    """When LLM_PROVIDER=poolside and key is set, poolside is selected."""
    with patch("src.services.llm.POOLSIDE_API_KEY", "sky_test"), \
         patch("src.services.llm.LLM_PROVIDER", "poolside"), \
         patch("src.services.llm.LLM_BASE_URL", ""), \
         patch("src.services.llm.LLM_API_KEY", ""):
        provider, base_url, api_key, model = resolve_llm_config()
        assert provider == "poolside"
        assert base_url == s.POOLSIDE_BASE_URL
        assert api_key == "sky_test"
