
FALLBACK_CHAIN = [
    "deepseek-coder-1.3b-instruct.Q4_K_M.gguf",
    "granite-4.0-1b-IQ4_NL.gguf",
    "Llama-3.2-1B-Instruct-Q6_K.gguf",
    "qwen2.5-coder-0.5b-instruct-q8_0.gguf",
    "gemma-3-270m-it-Q8_0.gguf"
]

MODEL_CAPS = {
    "deepseek-coder-1.3b-instruct.Q4_K_M.gguf": ["coding", "legal", "analysis", "math", "logic"],
    "granite-4.0-1b-IQ4_NL.gguf": ["reasoning", "long-context"],
    "granite-3.1-3b-a800m-base.Q2_K.gguf": ["reasoning", "analysis"],
    "Llama-3.2-1B-Instruct-Q6_K.gguf": ["general", "instruct"],
    "Llama-3.2-1B-Instruct.Q8_0.gguf": ["general", "instruct", "high-quality"],
    "qwen2.5-coder-0.5b-instruct-q8_0.gguf": ["coding", "fast"],
    "gemma-3-270m-it-Q8_0.gguf": ["fallback", "fast", "tiny"]
}

AVAILABLE_MODELS = list(MODEL_CAPS.keys())
