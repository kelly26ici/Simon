# src/configs/constants.py
GROQ_MODEL = "groq/compound"
GROQ_FALLBACK_MODEL = "openai/gpt-oss-20b"
OPENROUTER_MODEL = "openai/gpt-4o-mini"
# NVIDIA's hosted OpenAI-compatible API expects the raw model ID without a
# provider prefix. The nvidia_nim/ prefix is for provider-routing clients.
NVIDIA_MODEL = "deepseek-ai/deepseek-v4-flash-0731"
GEMINI_MODEL = "gemini-2.5-flash"