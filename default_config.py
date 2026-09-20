DEFAULT_CONFIG = {
    "agent_llm_model":        "openai/gpt-oss-20b",   # text agent 
    "graph_llm_model":        "qwen/qwen3.8-27b",  # vision agent 
    "agent_llm_provider":     "groq",
    "graph_llm_provider":     "groq",
    "agent_llm_temperature":  0.0,
    "graph_llm_temperature":  0.0,
    "agent_llm_max_tokens":   2048,
    "graph_llm_max_tokens":   1024,   # đủ chỗ cho 6 trường sau khi bóc suy luận
    "groq_api_key":           "",
    "use_historical_sentiment": True,
    "allow_shorting":        False,
    "tx_cost":               0.0025,
    "slippage":              0.001,
    "initial_capital_vnd":    50_000_000.0,
    "price_multiplier":       1_000.0,
}
