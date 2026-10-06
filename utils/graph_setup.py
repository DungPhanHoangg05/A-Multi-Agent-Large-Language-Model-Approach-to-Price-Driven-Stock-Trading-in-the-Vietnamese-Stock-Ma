from copy import deepcopy
from typing import Any, AsyncIterator, Callable, Dict, Iterator

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.runnables.graph import Graph
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.graph.state import CompiledStateGraph

from agents.agent_state import IndicatorAgentState
from agents.alpha_agent import create_alpha_agent
from agents.decision_agent import create_final_trade_decider
from utils.graph_util import TechnicalTools
from agents.indicator_agent import create_indicator_agent
from agents.pattern_agent import create_pattern_agent
from agents.trend_agent import create_trend_agent
from core.prior_config import (
    PRIOR_STATE_FIELDS, PriorConfig, copy_prior_json, normalize_prior_config,
    normalize_prior_query_context, normalize_prior_state, validate_prior_execution,
)
from core.decision_prior import PriorSourceValidator, prepare_decision_prior


PriorRetriever = Callable[[dict[str, Any]], dict[str, Any]]
_REPORT_FIELDS = tuple(f"{name}_report" for name in ("indicator", "pattern", "trend", "alpha", "sentiment"))


class ValidatedBacktestGraph(Runnable[dict[str, Any], dict[str, Any]]):
    """Biên input thô; chuyển nguyên config/kwargs tới graph cho cả async/stream.

    Không mở API update_state/checkpointer ở bước này; W4-12 cần kiểm identity
    và báo cáo durable trước khi thiết kế resume nghiên cứu.
    """

    def __init__(self, graph: CompiledStateGraph,
                 validator: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self._graph = graph
        self._validator = validator

    @property
    def channels(self) -> dict[str, Any]:
        """Cho phép kiểm schema mà không bỏ qua biên input."""
        return self._graph.channels

    def get_graph(self, config: RunnableConfig | None = None, *, xray: bool | int = False) -> Graph:
        """Trả topology LangGraph thật để kiểm thứ tự node."""
        return self._graph.get_graph(config, xray=xray)

    def invoke(self, input: dict[str, Any], config: RunnableConfig | None = None,
               **kwargs: Any) -> dict[str, Any]:
        """Kiểm input rồi chạy graph đồng bộ."""
        return self._graph.invoke(self._validator(input), config, **kwargs)

    async def ainvoke(self, input: dict[str, Any], config: RunnableConfig | None = None,
                      **kwargs: Any) -> dict[str, Any]:
        """Kiểm input rồi chạy graph bất đồng bộ."""
        return await self._graph.ainvoke(self._validator(input), config, **kwargs)

    def stream(self, input: dict[str, Any], config: RunnableConfig | None = None,
               **kwargs: Any) -> Iterator[dict[str, Any]]:
        """Kiểm input trước chunk đầu, giữ tham số stream của LangGraph."""
        yield from self._graph.stream(self._validator(input), config, **kwargs)

    async def astream(self, input: dict[str, Any], config: RunnableConfig | None = None,
                      **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        """Kiểm input trước chunk đầu của stream bất đồng bộ."""
        async for chunk in self._graph.astream(self._validator(input), config, **kwargs):
            yield chunk


def _require_reports(state: dict[str, Any], fields: tuple[str, ...]) -> None:
    """Chặn báo cáo thiếu trước khi truy xuất hoặc gọi agent tiếp theo."""
    for field in fields:
        value = state.get(field)
        if (type(value) is not str or not value.strip()
                or value.strip() in ("No data.", "Không có dữ liệu.")):
            raise ValueError(f"Graph yêu cầu báo cáo đầy đủ: {field}")


def _consume_graph_prior(state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Hook nội bộ: chỉ nhận output của node Prior Preparation ngay trước Decision.

    Không lưu cờ verified trong JSON và không retrieve/format lần hai. Entry point
    graph luôn chạy node chuẩn bị; hook này không dùng cho Decision độc lập.
    """
    prepared = {**state, **{field: copy_prior_json(state[field]) for field in PRIOR_STATE_FIELDS}}
    return prepared, prepared["bayesian_prior_context"]


def _guard_prior_state(
    node: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Kiểm prior trước node và giữ field chuẩn hóa qua các channel của graph."""
    def guarded(state: dict[str, Any]) -> dict[str, Any]:
        prepared = normalize_prior_state(state)
        result = node(prepared)
        checked = normalize_prior_state({**prepared, **result})
        return {**result, **{field: checked[field] for field in PRIOR_STATE_FIELDS if field in checked}}

    return guarded


ABLATION_CONFIGS: Dict[str, Dict[str, bool]] = {
    "full": {"enable_alpha_factors": True, "enable_sentiment": True},
    "alpha_only": {"enable_alpha_factors": True, "enable_sentiment": False},
    "sentiment_only": {"enable_alpha_factors": False, "enable_sentiment": True},
    "baseline": {"enable_alpha_factors": False, "enable_sentiment": False},
}


def resolve_ablation_config(
    ablation_config: Dict[str, bool] = None,
    include_alpha: bool = None,
) -> Dict[str, bool]:
    """Chuẩn hóa cấu hình hai module; giữ tương thích với cờ cũ."""

    if ablation_config is not None and include_alpha is not None:
        raise ValueError("Chỉ truyền ablation_config hoặc include_alpha, không truyền cả hai.")
    if ablation_config is None:
        variant = "full" if include_alpha is not False else "baseline"
        return dict(ABLATION_CONFIGS[variant])

    required = {"enable_alpha_factors", "enable_sentiment"}
    missing = required.difference(ablation_config)
    if missing:
        raise ValueError(f"ablation_config thiếu trường: {sorted(missing)}")
    return {
        "enable_alpha_factors": bool(ablation_config["enable_alpha_factors"]),
        "enable_sentiment": bool(ablation_config["enable_sentiment"]),
    }


def _ablation_mode(config: Dict[str, bool]) -> str:
    for name, standard_config in ABLATION_CONFIGS.items():
        if config == standard_config:
            return name
    return "custom"


class BacktestAgentState(IndicatorAgentState, total=False):
    """Các trường điều khiển chỉ dùng khi chạy graph backtest tách pha."""

    sentiment_store: Any
    window_end_date: str
    alpha_norm_method: str
    alpha_weights: Dict[str, float]
    ablation_config: Dict[str, bool]


class SetGraph:
    def __init__(
        self,
        agent_llm: BaseChatModel,  
        graph_llm: BaseChatModel,  
        toolkit: TechnicalTools,
    ):
        self.agent_llm = agent_llm
        self.graph_llm = graph_llm
        self.toolkit = toolkit

    def compile_full_preparation(self, *, strict_research_mode: bool = False) -> ValidatedBacktestGraph:
        """Chuẩn bị Alpha/Sentiment một lần từ upstream, chưa chạy Decision/prior.

        Caller kiểm nguồn PIT trước upstream, rồi lưu/deep-copy Full output cho
        từng nhánh. Prior chỉ được bật tại compile_report_decision().
        """
        def validate_input(state: dict[str, Any]) -> dict[str, Any]:
            if type(state) is not dict or state.get("is_backtest") is not True:
                raise ValueError("Chuẩn bị Full yêu cầu state backtest")
            prepared = normalize_prior_state(state)
            config = state.get("ablation_config", ABLATION_CONFIGS["full"])
            if (type(config) is not dict or set(config) != set(ABLATION_CONFIGS["full"])
                    or any(type(value) is not bool or value is not True for value in config.values())):
                raise ValueError("Chuẩn bị Full yêu cầu cả Alpha và Sentiment")
            _require_reports(prepared, _REPORT_FIELDS[:3])
            return {**prepared, "ablation_config": dict(ABLATION_CONFIGS["full"])}

        graph = StateGraph(BacktestAgentState)
        alpha = (create_alpha_agent(self.agent_llm, True, True, strict_research_mode=True)
                 if strict_research_mode else create_alpha_agent(self.agent_llm, True, True))
        graph.add_node("Full Preparation", _guard_prior_state(alpha))
        graph.add_edge(START, "Full Preparation")
        graph.add_edge("Full Preparation", END)
        # Kiểm input thô trước khi TypedDict của LangGraph lọc channel.
        return ValidatedBacktestGraph(graph.compile(), validate_input)

    def compile_report_decision(
        self, *, prior_config: PriorConfig | dict[str, Any] | None = None,
        prior_retriever: PriorRetriever | None = None,
        prior_source_validator: PriorSourceValidator | None = None,
    ) -> ValidatedBacktestGraph:
        """Chạy Decision từ Full reports có sẵn, không gọi lại Alpha/upstream.

        Enabled: context đã chuẩn bị, result còn rỗng; verifier kiểm nguồn trước
        retrieve và kiểm result sau retrieve. Callback trả đúng tasks/stats/metadata
        W3, không format. Graph sở hữu retrieve và formatter duy nhất mỗi invoke.
        Disabled: không hook/đọc kho; Decision dùng guard legacy.
        """
        config = normalize_prior_config(prior_config)
        enabled = config["enable_bayesian_prior"]
        if enabled and (not callable(prior_retriever) or not callable(prior_source_validator)):
            raise ValueError("Graph prior enabled cần retriever và verifier nguồn PIT")
        if not enabled and (prior_retriever is not None or prior_source_validator is not None):
            raise ValueError("Graph prior disabled không nhận hook prior")

        def validate_input(state: dict[str, Any]) -> dict[str, Any]:
            if type(state) is not dict:
                raise ValueError("Input graph phải là dict Python gốc")
            bound = normalize_prior_config(state.get("prior_config", config))
            if bound != config:
                raise ValueError("Config state khác config graph đã biên dịch")
            if state.get("is_backtest") is not True:
                raise ValueError("Graph từ Full reports chỉ hỗ trợ backtest")
            full = state.get("ablation_config", ABLATION_CONFIGS["full"])
            if (type(full) is not dict or set(full) != set(ABLATION_CONFIGS["full"])
                    or any(type(value) is not bool or value is not True for value in full.values())):
                raise ValueError("Graph từ Full reports yêu cầu ablation Full")
            if not enabled:
                prepared = normalize_prior_state(state)
                _require_reports(prepared, _REPORT_FIELDS)
                return {**prepared, "ablation_config": dict(ABLATION_CONFIGS["full"])}
            unknown = set(state).difference(BacktestAgentState.__annotations__)
            if unknown:
                raise ValueError(f"Input research chứa field ngoài schema: {sorted(unknown)}")
            _, ablation, timeframe = validate_prior_execution(
                bound, is_backtest=state.get("is_backtest"), time_frame=state.get("time_frame"),
                ablation_config=state.get("ablation_config"),
            )
            _require_reports(state, _REPORT_FIELDS)
            if any(field not in state for field in ("market_regime", "current_signals", "prior_provenance")):
                raise ValueError("Graph enabled thiếu context regime/signals/provenance")
            for field, empty in (("prior_tasks", []), ("prior_stats", None),
                                 ("prior_metadata", None), ("bayesian_prior_context", "")):
                value = state.get(field, empty)
                if type(value) is not type(empty) or value != empty:
                    raise ValueError(f"Graph không nhận result prior có sẵn: {field}")
            prior = {field: copy_prior_json(state[field]) for field in
                     ("market_regime", "current_signals", "prior_provenance")}
            query = normalize_prior_query_context({**state, **prior})
            return {**state, **prior, **query, "prior_config": deepcopy(config),
                    "prior_tasks": [], "prior_stats": None, "prior_metadata": None,
                    "bayesian_prior_context": "", "time_frame": timeframe, "ablation_config": ablation}

        def prepare_prior(state: dict[str, Any]) -> dict[str, Any]:
            projection = {**{field: copy_prior_json(state[field]) for field in PRIOR_STATE_FIELDS},
                          **normalize_prior_query_context(state), "time_frame": state["time_frame"],
                          "is_backtest": True, "ablation_config": dict(ABLATION_CONFIGS["full"]),
                          **{field: state[field] for field in _REPORT_FIELDS}}
            # Verifier nhận bản sao; lỗi nguồn dừng trước truy xuất, kể cả K=0.
            if prior_source_validator(deepcopy(projection)) is not None:
                raise ValueError("Hàm xác minh nguồn phải trả None hoặc ném ngoại lệ")
            result = prior_retriever(deepcopy(projection))
            if type(result) is not dict or set(result) != {"tasks", "stats", "metadata"}:
                raise ValueError("Retriever graph phải trả đúng tasks/stats/metadata, không prefix")
            retrieved = {**state, "prior_tasks": copy_prior_json(result["tasks"]),
                         "prior_stats": copy_prior_json(result["stats"]),
                         "prior_metadata": copy_prior_json(result["metadata"])}
            prepared, _ = prepare_decision_prior(
                retrieved, source_validator=prior_source_validator, build_prefix=True,
            )
            return {**{field: prepared[field] for field in PRIOR_STATE_FIELDS},
                    "time_frame": prepared["time_frame"], "ablation_config": prepared["ablation_config"]}

        graph = StateGraph(BacktestAgentState)
        if enabled:
            graph.add_node("Prior Preparation", prepare_prior)
            decision = create_final_trade_decider(self.agent_llm, _prior_preparer=_consume_graph_prior)
            graph.add_edge(START, "Prior Preparation")
            graph.add_edge("Prior Preparation", "Decision Maker")
        else:
            decision = _guard_prior_state(create_final_trade_decider(self.agent_llm))
            graph.add_edge(START, "Decision Maker")
        graph.add_node("Decision Maker", decision)
        graph.add_edge("Decision Maker", END)
        return ValidatedBacktestGraph(graph.compile(), validate_input)

    def compile_upstream(self):
        """Biên dịch pha Indicator → Pattern → Trend dùng chung cho backtest."""
        graph = StateGraph(BacktestAgentState)
        graph.add_node(
            "Indicator Agent",
            _guard_prior_state(create_indicator_agent(self.agent_llm, self.toolkit)),
        )
        graph.add_node(
            "Pattern Agent",
            _guard_prior_state(create_pattern_agent(self.agent_llm, self.graph_llm, self.toolkit)),
        )
        graph.add_node(
            "Trend Agent",
            _guard_prior_state(create_trend_agent(self.agent_llm, self.graph_llm, self.toolkit)),
        )
        graph.add_edge(START, "Indicator Agent")
        graph.add_edge("Indicator Agent", "Pattern Agent")
        graph.add_edge("Pattern Agent", "Trend Agent")
        graph.add_edge("Trend Agent", END)
        print("[SetGraph] Upstream graph compiled: Indicator -> Pattern -> Trend")
        return graph.compile()

    def compile_decision(
        self,
        include_alpha: bool = None,
        ablation_config: Dict[str, bool] = None,
    ):
        """Biên dịch pha quyết định theo hai công tắc Alpha/Sentiment độc lập."""
        config = resolve_ablation_config(ablation_config, include_alpha)
        enable_alpha = config["enable_alpha_factors"]
        enable_sentiment = config["enable_sentiment"]
        graph = StateGraph(BacktestAgentState)
        decision_node = create_final_trade_decider(self.agent_llm)
        graph.add_node("Decision Maker", _guard_prior_state(decision_node))

        if enable_alpha or enable_sentiment:
            graph.add_node(
                "Alpha Agent",
                _guard_prior_state(create_alpha_agent(
                    self.agent_llm,
                    enable_alpha,
                    enable_sentiment,
                )),
            )
            graph.add_edge(START, "Alpha Agent")
            graph.add_edge("Alpha Agent", "Decision Maker")
        else:
            graph.add_edge(START, "Decision Maker")

        graph.add_edge("Decision Maker", END)
        print(f"[SetGraph] Decision graph compiled: {_ablation_mode(config)}")
        return graph.compile()

    def set_graph(
        self,
        include_alpha: bool = None,
        ablation_config: Dict[str, bool] = None,
    ):
        """
        Xây dựng LangGraph pipeline.

        Args:
            ablation_config: Hai cờ độc lập ``enable_alpha_factors`` và
                ``enable_sentiment``. ``include_alpha`` chỉ còn để tương thích
                với lời gọi Full/Baseline cũ.
        """
        config = resolve_ablation_config(ablation_config, include_alpha)
        enable_alpha = config["enable_alpha_factors"]
        enable_sentiment = config["enable_sentiment"]
        all_agents = ["indicator"]
        if enable_alpha or enable_sentiment:
            all_agents.append("alpha")
        all_agents.extend(["pattern", "trend"])

        agent_nodes = {}

        # Indicator Agent — computes MACD/RSI/etc. via Python tools
        agent_nodes["indicator"] = create_indicator_agent(self.agent_llm, self.toolkit)

        # Node đặc trưng chạy riêng Alpha, Sentiment, hoặc cả hai theo cấu hình.
        if enable_alpha or enable_sentiment:
            agent_nodes["alpha"] = create_alpha_agent(
                self.agent_llm,
                enable_alpha,
                enable_sentiment,
            )

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
            graph.add_node(f"{agent_type.capitalize()} Agent", _guard_prior_state(node))

        graph.add_node("Decision Maker", _guard_prior_state(decision_agent_node))

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

        mode = _ablation_mode(config)
        print(f"[SetGraph] Graph compiled: {mode}  →  {' → '.join(a.capitalize() for a in all_agents)} → Decision")
        return graph.compile()
