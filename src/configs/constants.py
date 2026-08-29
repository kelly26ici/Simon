# src/configs/constants.py
GROQ_MODEL = "groq/compound"
GROQ_FALLBACK_MODEL = "openai/gpt-oss-20b"
OPENROUTER_MODEL = "openai/gpt-4o-mini"
# NVIDIA's hosted OpenAI-compatible API expects the raw model ID without a
# provider prefix. The nvidia_nim/ prefix is for provider-routing clients.
DEFAULT_NVIDIA_MODEL = "moonshotai/kimi-k3"
NVIDIA_MODEL = DEFAULT_NVIDIA_MODEL

# Ordered cascade of capable models for auto-shifting and failover,
# strictly ranked from strongest/highest-reasoning to next (Quality & Benchmark first):
# 1. Kimi K3 (2.8T MoE, ~1500 Elo, 88% MMLU-Pro, 93.5% GPQA Diamond)
# 2. MiniMax M3 (428B MoE, 84-87% MMLU-Pro, 92% GPQA Diamond, 1M context)
# 3. Nemotron 3 Super (120B MoE, 83.7% MMLU-Pro, 79.2% GPQA)
# 4. Llama 3.2 90B Vision (90B dense, 88.5% MMLU)
# 5. Nemotron 3 Nano Omni Reasoning (30B with chain-of-thought & tool calling)
# 6. Muse Glimmer (30B agentic instruct)
# 7. Nemotron 3.5 Lightning (30B)
# 8. Diffusion Gemma (26B)
# 9. GPT-OSS 20B (20B)
# 10. Llama 3.2 11B Vision (11B)
# 11. Laguna XS 2.1
# 12. Nemotron 3 Nano (30B)
NVIDIA_CASCADE_MODELS = [
    "moonshotai/kimi-k3",
    "minimaxai/minimax-m3",
    "nvidia/nemotron-3-super-120b-a12b",
    "meta/llama-3.2-90b-vision-instruct",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "meta/muse-glimmer-30b",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "google/diffusiongemma-26b-a4b-it",
    "openai/gpt-oss-20b",
    "meta/llama-3.2-11b-vision-instruct",
    "poolside/laguna-xs-2.1",
    "nvidia/nemotron-3-nano-30b-a3b",
]

# Time in seconds before an active failover model automatically resets back to moonshotai/kimi-k3 (1 hour).
MODEL_RESET_COOLDOWN_SECONDS = 3600

GEMINI_MODEL = "gemini-2.5-flash"