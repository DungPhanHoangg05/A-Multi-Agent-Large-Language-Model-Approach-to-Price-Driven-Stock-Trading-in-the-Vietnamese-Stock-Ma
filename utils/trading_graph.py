import os

from langchain_groq import ChatGroq
from langchain_core.language_models import BaseChatModel

from default_config import DEFAULT_CONFIG
from utils.graph_setup import SetGraph
from utils.graph_util import TechnicalTools


class TradingGraph:
    """
    Điều phối hệ thống đa-agent trading sử dụng Groq API.
    """

    def __init__(self, config=None):
        self.config = config if config is not None else DEFAULT_CONFIG.copy()
        self._ensure_api_key()

        self.agent_llm = self._create_llm(
            model=self.config.get("agent_llm_model", "openai/gpt-oss-20b"),
            temperature=self.config.get("agent_llm_temperature", 0.1),
        )
        self.graph_llm = self._create_llm(
            model=self.config.get("graph_llm_model", "qwen/qwen3.6-27b"),
            temperature=self.config.get("graph_llm_temperature", 0.1),
        )

        self.toolkit = TechnicalTools()

        self.graph_setup = SetGraph(
            self.agent_llm,
            self.graph_llm,
            self.toolkit,
        )
        self.graph = self.graph_setup.set_graph()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _ensure_api_key(self) -> None:
        """Lấy Groq API key từ config hoặc biến môi trường."""
        key = self.config.get("groq_api_key") or os.environ.get("GROQ_API_KEY", "")
        if key:
            self.config["groq_api_key"] = key
            os.environ["GROQ_API_KEY"] = key

    def _create_llm(self, model: str, temperature: float) -> BaseChatModel:
        """Tạo instance ChatGroq cho model chỉ định."""
        api_key = self.config.get("groq_api_key") or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError(
                "Groq API key chưa được cấu hình. "
                "Nhập key tại giao diện web hoặc đặt biến môi trường GROQ_API_KEY."
            )
        return ChatGroq(
            model=model,
            temperature=temperature,
            api_key=api_key,
            max_retries=3,
        )

    # ── Public methods ────────────────────────────────────────────────────────

    def refresh_llms(self) -> None:
        """Tạo lại các LLM với cấu hình hiện tại (dùng khi config thay đổi)."""
        self._ensure_api_key()
        self.agent_llm = self._create_llm(
            model=self.config.get("agent_llm_model", "openai/gpt-oss-20b"),
            temperature=self.config.get("agent_llm_temperature", 0.1),
        )
        self.graph_llm = self._create_llm(
            model=self.config.get("graph_llm_model", "qwen/qwen3.6-27b"),
            temperature=self.config.get("graph_llm_temperature", 0.1),
        )
        self.graph_setup = SetGraph(self.agent_llm, self.graph_llm, self.toolkit)
        self.graph = self.graph_setup.set_graph()

    def update_api_key(self, api_key: str) -> None:
        """Cập nhật Groq API key và refresh LLM."""
        self.config["groq_api_key"] = api_key
        os.environ["GROQ_API_KEY"] = api_key
        self.refresh_llms()

    def update_model(self, agent_model: str = None, graph_model: str = None) -> None:
        """Cập nhật tên model và refresh LLM."""
        if agent_model:
            self.config["agent_llm_model"] = agent_model
        if graph_model:
            self.config["graph_llm_model"] = graph_model
        self.refresh_llms()