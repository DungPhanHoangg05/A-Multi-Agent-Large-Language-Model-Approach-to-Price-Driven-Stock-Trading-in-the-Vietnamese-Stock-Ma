DEFAULT_CONFIG = {
    "agent_llm_model":        "openai/gpt-oss-20b",   # text agent 
    "graph_llm_model":        "qwen/qwen3.8-27b",  # vision agent 
    "agent_llm_provider":     "groq",
    "graph_llm_provider":     "groq",
    "agent_llm_temperature":  0.0,
    "graph_llm_temperature":  0.0,
    "graph_llm_max_tokens":   1024,   # đủ chỗ cho 6 trường sau khi bóc suy luận
    "groq_api_key":           "",
    "use_historical_sentiment": True
}