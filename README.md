# A Multi-Agent Large Language Model Approach to Price-Driven Stock Trading in the Vietnamese Stock Market

This project is a Multi-Agent Large Language Model (LLM) framework designed for automated technical analysis and trading decision support specifically tailored for the Vietnamese stock market. Built on top of LangGraph, it coordinates multiple specialized AI agents to analyze stock price data, technical indicators, chart patterns, and news sentiment, ultimately synthesizing a cohesive trading decision.

## Features

- **Multi-Agent Architecture**: Built with LangGraph, combining the strengths of multiple specialized agents:
  - **Indicator Agent**: Analyzes momentum oscillators and technical indicators.
  - **Alpha Agent**: Selects top-performing quantitative factors from an 85-candidate registry, augmented with Vietnamese sentiment signals (from CafeF and ViSoBERT).
  - **Pattern Agent**: Uses vision-language models to analyze candlestick patterns.
  - **Trend Agent**: Uses vision-language models to analyze trendlines and chart structures.
  - **Decision Agent**: Synthesizes all reports into a forced LONG/SHORT trading decision calibrated to Vietnam’s T+2.5 settlement structure.
- **Vietnamese Market Adaptation**: Explicitly adapted for the T+2.5 settlement rule, domestic news ecosystem (CafeF), and single-stock OHLCV data characteristics.
- **Web Interface**: A Flask-based web interface to interact with the system, visualize charts, and run analyses.

## Requirements

The project uses Python and requires several dependencies. Make sure you have Python installed, then install the packages listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

### Key Dependencies
- `flask`: For the web interface
- `langchain`, `langchain-groq`, `langgraph`: For the LLM agent orchestration
- `pandas`, `numpy`, `scipy`, `TA-Lib`: For technical analysis and data manipulation
- `matplotlib`, `mplfinance`: For chart generation
- `vnstock`: For fetching Vietnamese stock data
- `transformers`, `torch`: For local sentiment analysis models

## Configuration

The system uses Groq for LLM inference (both text and vision models). You need to provide a Groq API Key.

You can configure the system by either:
1. Setting the `GROQ_API_KEY` environment variable:
   ```bash
   export GROQ_API_KEY="your_api_key_here"
   ```
2. Or editing the `default_config.py` file to include your API key and adjust model selections:
   ```python
   DEFAULT_CONFIG = {
       "agent_llm_model":        "openai/gpt-oss-20b",   # text agent 
       "graph_llm_model":        "qwen/qwen3.6-27b",       # vision agent 
       "agent_llm_provider":     "groq",
       "graph_llm_provider":     "groq",
       "agent_llm_temperature":  0.1,
       "graph_llm_temperature":  0.1,
       "groq_api_key":           "your_api_key_here", 
       "use_historical_sentiment": True
   }
   ```

## Usage

To start the web interface, run the `web_interface.py` file:

```bash
python web_interface.py
```

By default, the Flask application will start a local server. Open your web browser and navigate to `http://127.0.0.1:5000` (or the address provided in your terminal) to interact with the system.

## Project Structure

- `web_interface.py`: The main Flask application providing the UI and coordinating the analysis.
- `agents/`: Contains the specialized LangGraph agents (`indicator_agent.py`, `alpha_agent.py`, `pattern_agent.py`, `trend_agent.py`, `decision_agent.py`).
- `core/`: Core engine logic, including the backtesting engine (`backtest_engine.py`) and data loaders.
- `utils/`: Utility functions for graph setup, chart generation (`static_util.py`), etc.
- `data_manager/`: Modules for managing historical and realtime data.
- `static/` & `templates/`: HTML, CSS, and JS assets for the web interface.
- `default_config.py`: Default configuration for models and API keys.

## Architecture & Research Context

This project extends the QuantAgent framework to emerging markets. While typical LLM trading frameworks are designed for mature, English-language markets, this framework addresses challenges specific to Vietnam, such as the T+2.5 minimum holding period and the necessity for Vietnamese-language sentiment analysis. The system evaluates the contribution of quantitative alpha integration and localized sentiment over a technical-only pipeline.
