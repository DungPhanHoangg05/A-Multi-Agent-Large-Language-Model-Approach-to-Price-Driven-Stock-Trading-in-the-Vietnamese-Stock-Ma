from typing import Dict

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agents.agent_state import IndicatorAgentState
from agents.alpha_agent import create_alpha_agent
from agents.decision_agent import create_final_trade_decider
from utils.graph_util import TechnicalTools
from agents.indicator_agent import create_indicator_agent
from agents.pattern_agent import create_pattern_agent
from agents.trend_agent import create_trend_agent


class SetGraph:
    def __init__(
        self,
        agent_llm: BaseChatModel,  # llama-3.1-8b-instant — text + tool calling
        graph_llm: BaseChatModel,  # llama-4-scout  — vision only, NO tool calling
        toolkit: TechnicalTools,
    ):
        self.agent_llm = agent_llm
        self.graph_llm = graph_llm
        self.toolkit = toolkit

    def set_graph(self, include_alpha: bool = True):
        """
        Xây dựng LangGraph pipeline.

        Args:
            include_alpha: Nếu True → pipeline đầy đủ (Indicator → Alpha → Pattern → Trend → Decision).
                           Nếu False → bỏ Alpha Agent (Indicator → Pattern → Trend → Decision).
                           Dùng include_alpha=False cho Backtest No-Alpha variant.
        """
        if include_alpha:
            all_agents = ["indicator", "alpha", "pattern", "trend"]
        else:
            all_agents = ["indicator", "pattern", "trend"]

        agent_nodes = {}

        # Indicator Agent — computes MACD/RSI/etc. via Python tools
        agent_nodes["indicator"] = create_indicator_agent(self.agent_llm, self.toolkit)

        # Alpha Agent — collects sentiment internally, then has LLM create
        # 5 original alpha formulas combining sentiment + technical data.
        # Only added when include_alpha=True.
        if include_alpha:
            agent_nodes["alpha"] = create_alpha_agent(self.agent_llm)

        # Pattern Agent — vision analysis of candlestick chart
        agent_nodes["pattern"] = create_pattern_agent(
            self.agent_llm, self.graph_llm, self.toolkit
        )

        # Trend Agent — vision analysis of trendline chart
        agent_nodes["trend"] = create_trend_agent(
            self.agent_llm, self.graph_llm, self.toolkit
        )

        # Decision Agent — synthesises all reports → LONG/SHORT
        decision_agent_node = create_final_trade_decider(self.agent_llm)

        # ── Build graph ───────────────────────────────────────────────────────
        graph = StateGraph(IndicatorAgentState)

        for agent_type, node in agent_nodes.items():
            graph.add_node(f"{agent_type.capitalize()} Agent", node)

        graph.add_node("Decision Maker", decision_agent_node)

        # Entry point
        graph.add_edge(START, "Indicator Agent")

        # Sequential edges
        for i, agent_type in enumerate(all_agents):
            current = f"{agent_type.capitalize()} Agent"
            if i == len(all_agents) - 1:
                graph.add_edge(current, "Decision Maker")
            else:
                next_agent = f"{all_agents[i + 1].capitalize()} Agent"
                graph.add_edge(current, next_agent)

        graph.add_edge("Decision Maker", END)

        mode = "Full (w/ Alpha)" if include_alpha else "No-Alpha"
        print(f"[SetGraph] Graph compiled: {mode}  →  {' → '.join(a.capitalize() for a in all_agents)} → Decision")
        return graph.compile()