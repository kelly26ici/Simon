# src/configs/constants.py
GROQ_MODEL = "groq/compound"
GROQ_FALLBACK_MODEL = "openai/gpt-oss-20b"
OPENROUTER_MODEL = "openai/gpt-4o-mini"
# NVIDIA's hosted OpenAI-compatible API expects the raw model ID without a
# provider prefix. The nvidia_nim/ prefix is for provider-routing clients.
DEFAULT_NVIDIA_MODEL = "moonshotai/kimi-k3"
NVIDIA_MODEL = DEFAULT_NVIDIA_MODEL

# Poolside AI — OpenAI-compatible inference API at https://inference.poolside.ai/v1
# Model ID format: poolside/<model-name>
# Ordered fastest → slowest (by active parameter count).
DEFAULT_POOLSIDE_MODEL = "poolside/laguna-xs-2.1"

# ---------------------------------------------------------------------------
# Poolside cascade — used when LLM_PROVIDER=poolside (or auto-detected via
# POOLSIDE_API_KEY).  Poolside models first (fastest→slowest), then the rest
# of the capable models (also fastest→slowest).  Minimax M3 has been removed.
# ---------------------------------------------------------------------------
# Poolside models (fastest → slowest by active params):
#   XS 2.1  — 33B total / 3B active MoE, 256K ctx  (lightest, fastest)
#   S 2.1   — 118B total / 8B active MoE, 1M ctx   (large, reasoning-focused)
#   M.1     — 225B total / 23B active MoE, 256K ctx (highest quality, slowest)
POOLSIDE_CASCADE_MODELS = [
    # --- Poolside (fastest → slowest) ---
    "poolside/laguna-xs-2.1",       # 33B-A3B MoE, 256K ctx
    "poolside/laguna-s-2.1",        # 118B-A8B MoE, 1M ctx
    "poolside/laguna-m.1",          # 225B-A23B MoE, 256K ctx
    # --- Rest (fastest → slowest, minimiami/m3 excluded) ---
    "openai/gpt-oss-20b",
    "meta/llama-3.2-11b-vision-instruct",
    "google/diffusiongemma-26b-a4b-it",
    "nvidia/nemotron-3-nano-30b-a3b",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "meta/muse-glimmer-30b",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "nvidia/nemotron-3-super-120b-a12b",
    "meta/llama-3.2-90b-vision-instruct",
    "moonshotai/kimi-k3",
]

# ---------------------------------------------------------------------------
# NVIDIA cascade (fastest → slowest, minimiami/m3 removed).
# Used when LLM_PROVIDER=nvidia (or auto-detected via NVIDIA_API_KEY).
# ---------------------------------------------------------------------------
NVIDIA_CASCADE_MODELS = [
    "openai/gpt-oss-20b",                       # 20B dense
    "meta/llama-3.2-11b-vision-instruct",       # 11B dense
    "google/diffusiongemma-26b-a4b-it",         # 26B-A4B MoE
    "poolside/laguna-xs-2.1",                   # 33B-A3B MoE — fastest poolside model (also on NVIDIA NIM)
    "nvidia/nemotron-3-nano-30b-a3b",           # 30B-A3B MoE
    "nvidia/nemotron-3.5-lightning-30b-a3b",    # 30B-A3B MoE
    "meta/muse-glimmer-30b",                    # 33B dense
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",  # 30B-A3B MoE with CoT
    "nvidia/nemotron-3-super-120b-a12b",        # 120B-A12B MoE
    "meta/llama-3.2-90b-vision-instruct",       # 90B dense
    "moonshotai/kimi-k3",                       # 2.8T MoE (strongest, slowest)
]

# Time in seconds before an active failover model automatically resets back to
# the primary model (1 hour).
MODEL_RESET_COOLDOWN_SECONDS = 3600

GEMINI_MODEL = "gemini-2.5-flash"
