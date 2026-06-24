import json
import os
import threading
import time
import uuid
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List
from core.backtest_engine import BacktestEngine
from dataclasses import asdict

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file

from utils import static_util
from default_config import DEFAULT_CONFIG
from core.realtime_loader import (
    check_vnstock_available,
    fetch_realtime_ohlcv,
    get_all_symbols_realtime,
    get_stock_info_realtime,
    get_realtime_status,
    get_cache_info,
    clear_cache,
)

app = Flask(__name__)

# ── Background job store ──────────────────────────────────────────────────────
_jobs: dict = {}
_jobs_lock  = threading.Lock()

def _cleanup_jobs():
    now = time.time()
    with _jobs_lock:
        for k in [k for k, v in _jobs.items() if now - v.get("ts", 0) > 600]:
            del _jobs[k]


# ── Main Analyzer class ───────────────────────────────────────────────────────

class WebTradingAnalyzer:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        # Ưu tiên lấy API key từ biến môi trường
        env_key = os.environ.get("GROQ_API_KEY", "")
        if env_key:
            self.config["groq_api_key"] = env_key
        self.trading_graph = None  # lazy init sau khi có API key
        self._stock_list: List[dict] = []
        self._refresh_stock_list()

    def _init_graph(self):
        """Khởi tạo TradingGraph (lazy — chỉ khi đã có API key)."""
        from utils.trading_graph import TradingGraph
        self.trading_graph = TradingGraph(config=self.config)

    # ── Stock list ────────────────────────────────────────────────────────────

    def _refresh_stock_list(self) -> None:
        symbols = get_all_symbols_realtime()
        self._stock_list = symbols
        print(f"[Analyzer] Loaded {len(self._stock_list)} symbols from vnstock.")

    def get_available_assets(self) -> List[dict]:
        return self._stock_list

    # ── Data loading ──────────────────────────────────────────────────────────

    def load_data(self, stock_code: str, tail: int = None, interval: str = "1d") -> tuple:
        print(f"[Analyzer] Fetching {stock_code} ({interval}) via vnstock...")
        return fetch_realtime_ohlcv(
            symbol=stock_code,
            interval=interval,
            tail=tail,        # None → auto from TIMEFRAME_CONFIG
        )

    # ── Analysis ──────────────────────────────────────────────────────────────

    # Mapping: LangGraph node name → step number (1-based, matching loading UI)
    # Sentiment runs inside Alpha Agent, so pipeline is 5 agents + decision = 6 steps
    _NODE_STEP_MAP = {
        "Indicator Agent": 2,
        "Alpha Agent":     3,
        "Pattern Agent":   4,
        "Trend Agent":     5,
        "Decision Maker":  6,
    }

    def run_analysis(self, df: pd.DataFrame, asset_name: str, timeframe: str,
                     step_callback=None) -> Dict[str, Any]:
        if self.trading_graph is None:
            return {"success": False, "error": "❌ Groq API key chưa được cấu hình. Vui lòng nhập API key trong phần cài đặt."}

        try:
            print(f"DataFrame columns : {df.columns.tolist()}")
            print(f"DataFrame shape   : {df.shape}")

            from core.realtime_loader import get_timeframe_cfg
            tf_cfg   = get_timeframe_cfg(timeframe)
            n_candles = tf_cfg["candles"]

            df_slice = df.tail(n_candles).reset_index(drop=True)

            required_columns = ["Datetime", "Open", "High", "Low", "Close"]
            if not all(col in df_slice.columns for col in required_columns):
                return {
                    "success": False,
                    "error": f"Thiếu cột dữ liệu. Cột hiện có: {list(df_slice.columns)}",
                }

            df_slice_dict: Dict[str, Any] = {}
            for col in required_columns:
                if col == "Datetime":
                    df_slice_dict[col] = df_slice[col].dt.strftime("%Y-%m-%d %H:%M:%S").tolist()
                else:
                    df_slice_dict[col] = df_slice[col].tolist()

            display_timeframe = _format_timeframe(timeframe)

            p_image = static_util.generate_kline_image(df_slice_dict, timeframe=timeframe)
            t_image = static_util.generate_trend_image(df_slice_dict, timeframe=timeframe)

            initial_state = {
                "kline_data":       df_slice_dict,
                "analysis_results": None,
                "messages":         [],
                "time_frame":       display_timeframe,
                "stock_name":       asset_name,
                "pattern_image":    p_image["pattern_image"],
                "trend_image":      t_image["trend_image"],
            }

            # Use stream() to get per-node progress updates
            final_state = None
            if step_callback:
                for chunk in self.trading_graph.graph.stream(initial_state, stream_mode="updates"):
                    for node_name in chunk:
                        step_num = self._NODE_STEP_MAP.get(node_name)
                        if step_num:
                            print(f"[WebAnalyzer] Node done: {node_name} → step {step_num}")
                            next_step = step_num + 1 if step_num < 6 else 6
                            step_callback(next_step)
                    # Merge chunk into final_state
                    if final_state is None:
                        final_state = {}
                    for node_output in chunk.values():
                        if isinstance(node_output, dict):
                            final_state.update(node_output)
            else:
                final_state = self.trading_graph.graph.invoke(initial_state)

            return {
                "success":     True,
                "final_state": final_state,
                "asset_name":  asset_name,
                "timeframe":   display_timeframe,
                "data_length": len(df_slice),
            }

        except Exception as e:
            error_msg = str(e)
            print(f"[Analysis Error] {error_msg}")

            if "api key" in error_msg.lower() or "authentication" in error_msg.lower() or "401" in error_msg:
                return {"success": False, "error": "❌ Groq API key không hợp lệ. Vui lòng kiểm tra lại key tại console.groq.com"}
            elif "rate limit" in error_msg.lower() or "429" in error_msg:
                return {"success": False, "error": "⏳ Groq rate limit — vui lòng chờ vài giây rồi thử lại."}
            elif "model" in error_msg.lower() and "not found" in error_msg.lower():
                return {"success": False, "error": f"❌ Model không tồn tại. Kiểm tra tên model trong cài đặt."}
            elif "connection" in error_msg.lower() or "refused" in error_msg.lower():
                return {"success": False, "error": "🌐 Không kết nối được Groq API. Kiểm tra kết nối internet."}
            else:
                return {"success": False, "error": f"❌ Lỗi phân tích: {error_msg}"}

    def extract_analysis_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        if not results.get("success"):
            return {"error": results.get("error", "Unknown error")}

        final_state    = results["final_state"]
        final_decision = _parse_decision(final_state.get("final_trade_decision", ""))

        return {
            "success":              True,
            "asset_name":           results["asset_name"],
            "timeframe":            results["timeframe"],
            "data_length":          results["data_length"],
            "technical_indicators": final_state.get("indicator_report", ""),
            "alpha_analysis":       final_state.get("alpha_report", ""),
            "pattern_analysis":     final_state.get("pattern_report", ""),
            "trend_analysis":       final_state.get("trend_report", ""),
            "pattern_chart":        final_state.get("pattern_image", ""),
            "trend_chart":          final_state.get("trend_image", ""),
            "pattern_image_filename": "",
            "trend_image_filename":   "",
            "sentiment_analysis":   final_state.get("sentiment_report", ""),
            "sentiment_data":       final_state.get("sentiment_data", {}),
            "sentiment_norm":       final_state.get("sentiment_norm", final_state.get("sentiment_data", {}).get("sentiment_norm", {})),
            "final_decision":       final_decision,
        }

    def validate_groq_connection(self) -> Dict[str, Any]:
        """Không gọi mạng — chỉ check format key và trạng thái graph."""
        api_key = self.config.get("groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
        if not api_key or not api_key.startswith("gsk_"):
            return {"valid": False, "error": "API key chưa được cấu hình"}
        return {
            "valid":       True,
            "agent_model": self.config.get("agent_llm_model"),
            "graph_model": self.config.get("graph_llm_model"),
            "api_key_set": True,
            "graph_ready": self.trading_graph is not None,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_timeframe(tf: str) -> str:
    from core.realtime_loader import get_timeframe_cfg
    cfg = get_timeframe_cfg(tf)
    return cfg.get("display", tf)


def _parse_decision(raw: str) -> Any:
    if not raw:
        return {}
    try:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            data = json.loads(raw[start:end])
            return {
                "decision":          data.get("decision", "N/A"),
                "risk_reward_ratio": data.get("risk_reward_ratio", "N/A"),
                "forecast_horizon":  data.get("forecast_horizon", "N/A"),
                "justification":     data.get("justification", "N/A"),
                "alpha_consensus":   data.get("alpha_consensus", ""),
                "consensus_count":   data.get("consensus_count", ""),
                "confidence":        data.get("confidence", ""),
                "key_risk":          data.get("key_risk", ""),
                "raw":               raw[:300],
            }
    except Exception:
        pass
    return {"raw": raw}


# ── App init ──────────────────────────────────────────────────────────────────

analyzer = WebTradingAnalyzer()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("demo_new.html")


@app.route("/demo")
def demo():
    return render_template("demo_new.html")


@app.route("/output")
def output():
    results = request.args.get("results")
    job_id  = request.args.get("job_id")

    #Ưu tiên lấy từ job_id 
    if job_id:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job and job.get("result"):
                return render_template("output.html", results=job["result"])

    if results:
        try:
            results_data = json.loads(urllib.parse.unquote(results))
            return render_template("output.html", results=results_data)
        except Exception as e:
            print(f"Error parsing results: {e}")

    default_results = {
        "asset_name": "VNM", "timeframe": "1 day", "data_length": 45,
        "technical_indicators": "", "alpha_analysis": "",
        "pattern_analysis": "", "trend_analysis": "",
        "pattern_chart": "", "trend_chart": "",
        "pattern_image_filename": "", "trend_image_filename": "",
        "final_decision": {
            "decision": "N/A", "risk_reward_ratio": "N/A",
            "forecast_horizon": "N/A", "justification": "No results.",
        },
    }
    return render_template("output.html", results=default_results)


# ── API: assets ───────────────────────────────────────────────────────────────

@app.route("/api/assets")
def get_assets():
    try:
        if request.args.get("refresh", "false").lower() == "true":
            analyzer._refresh_stock_list()
        return jsonify({
            "assets":      analyzer.get_available_assets(),
            "total":       len(analyzer.get_available_assets()),
            "data_source": "realtime",
        })
    except Exception as e:
        return jsonify({"error": str(e)})


# ── API: stock info ───────────────────────────────────────────────────────────

@app.route("/api/stock-info/<code>")
def stock_info(code: str):
    try:
        return jsonify(get_stock_info_realtime(code.upper()))
    except Exception as e:
        return jsonify({"error": str(e)})


# ── API: analyze ──────────────────────────────────────────────────────────────

@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Khởi động phân tích trong background thread, trả job_id ngay."""
    try:
        data       = request.get_json()
        stock_code = (data.get("asset") or "").strip().upper()
        timeframe  = data.get("timeframe", "1d")

        if not stock_code:
            return jsonify({"error": "Vui lòng chọn mã cổ phiếu."})
        api_key = analyzer.config.get("groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return jsonify({"error": "❌ Groq API key chưa được cấu hình."})
        if not check_vnstock_available():
            return jsonify({"error": "vnstock chưa cài. Chạy: pip install vnstock"})

        job_id = str(uuid.uuid4())
        with _jobs_lock:
            _jobs[job_id] = {"status": "running", "step": 1, "result": None, "ts": time.time()}

        def _set_step(step: int):
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["step"] = step

        def _run():
            try:
                # Step 1: Init graph + fetch data
                _set_step(1)
                if analyzer.trading_graph is None:
                    analyzer._init_graph()
                df, load_err = analyzer.load_data(stock_code, interval=timeframe)
                if load_err:
                    raise RuntimeError(load_err)
                if df.empty:
                    raise RuntimeError(f"Không có dữ liệu cho {stock_code}.")

                # Step 2+: run analysis with per-node step tracking
                _set_step(2)
                results   = analyzer.run_analysis(df, stock_code, timeframe, step_callback=_set_step)
                formatted = analyzer.extract_analysis_results(results)
                formatted["data_source_used"] = "realtime"
                if formatted.get("success"):
                    # Gửi redirect qua job_id để tránh lỗi URI Too Long (414)
                    formatted["redirect"] = f"/output?job_id={job_id}"
                with _jobs_lock:
                    _jobs[job_id] = {"status": "done", "step": 6, "result": formatted, "ts": time.time()}
            except Exception as exc:
                with _jobs_lock:
                    _jobs[job_id] = {"status": "error", "step": 0, "result": {"error": str(exc)}, "ts": time.time()}

        threading.Thread(target=_run, daemon=True).start()
        _cleanup_jobs()
        return jsonify({"job_id": job_id})

    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/analyze/status/<job_id>")
def analyze_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job không tồn tại."}), 404
    return jsonify({"status": job["status"], "step": job.get("step", 1), "result": job["result"]})


# ── API: Groq status ──────────────────────────────────────────────────────────

@app.route("/api/groq-status")
def groq_status():
    try:
        status = analyzer.validate_groq_connection()
        return jsonify(status)
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})


@app.route("/api/update-api-key", methods=["POST"])
def update_api_key():
    """Chỉ lưu key — KHÔNG gọi mạng, KHÔNG init graph."""
    try:
        data    = request.get_json()
        api_key = (data.get("api_key") or "").strip()
        if not api_key:
            return jsonify({"error": "API key không được để trống."})
        if not api_key.startswith("gsk_"):
            return jsonify({"error": "Key sai định dạng (phải bắt đầu bằng gsk_)"})
        analyzer.config["groq_api_key"] = api_key
        os.environ["GROQ_API_KEY"]       = api_key
        analyzer.trading_graph           = None
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/update-models", methods=["POST"])
def update_models():
    try:
        data        = request.get_json()
        agent_model = data.get("agent_model")
        graph_model = data.get("graph_model")
        if analyzer.trading_graph is None:
            return jsonify({"error": "Vui lòng cấu hình API key trước."})
        analyzer.trading_graph.update_model(
            agent_model=agent_model, graph_model=graph_model,
        )
        if agent_model:
            analyzer.config["agent_llm_model"] = agent_model
        if graph_model:
            analyzer.config["graph_llm_model"] = graph_model
        return jsonify({
            "success":     True,
            "agent_model": analyzer.config["agent_llm_model"],
            "graph_model": analyzer.config["graph_llm_model"],
        })
    except Exception as e:
        return jsonify({"error": str(e)})


# ── API: realtime status ──────────────────────────────────────────────────────

@app.route("/api/realtime-status")
def realtime_status():
    try:
        return jsonify(get_realtime_status())
    except Exception as e:
        return jsonify({"available": False, "error": str(e)})


@app.route("/api/realtime-cache/clear", methods=["POST"])
def clear_realtime_cache():
    try:
        data = request.get_json() or {}
        clear_cache(symbol=data.get("symbol"), interval=data.get("interval"))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)})


# ── API: images ───────────────────────────────────────────────────────────────

@app.route("/api/images/<image_type>")
def get_image(image_type):
    try:
        path = {"pattern": "kline_chart.png", "trend": "trend_graph.png"}.get(image_type)
        if not path or not os.path.exists(path):
            return jsonify({"error": "Image not found."})
        return send_file(path, mimetype="image/png")
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    try:
        return send_file(f"assets/{filename}")
    except FileNotFoundError:
        return jsonify({"error": "Asset not found"}), 404


# ── Backtest globals ──────────────────────────────────────────────────────────
 
_bt_jobs: dict = {}
_bt_lock = threading.Lock()
 
def _cleanup_bt_jobs():
    now = time.time()
    with _bt_lock:
        for k in [k for k, v in _bt_jobs.items() if now - v.get("ts", 0) > 7200]:
            del _bt_jobs[k]
 
 
@app.route("/backtest")
def backtest_page():
    return render_template("backtest.html")
 
 
@app.route("/api/backtest/start", methods=["POST"])
def backtest_start():
    try:
        data      = request.get_json()
        symbol    = (data.get("symbol") or "").strip().upper()
        n_tests   = int(data.get("n_tests",   10))
        win_size  = int(data.get("window_size", 45))
        step      = int(data.get("step",  3))
 
        if not symbol:
            return jsonify({"error": "Vui lòng nhập mã cổ phiếu."})
 
        api_key = analyzer.config.get("groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return jsonify({"error": "Groq API key chưa được cấu hình."})
 
        if not check_vnstock_available():
            return jsonify({"error": "vnstock chưa cài. Chạy: pip install vnstock"})
 
        n_tests  = max(3, min(n_tests,  30))
        win_size = max(20, min(win_size, 90))
        step     = max(1, min(step,      15))
 
        bt_id = str(uuid.uuid4())
        engine = BacktestEngine(config=analyzer.config.copy())
 
        with _bt_lock:
            _bt_jobs[bt_id] = {
                "status": "starting", "step": "loading",
                "ts": time.time(), "engine": engine,
                "summary": None, "test_points": [], "partial": {},
                "error": "",
            }
 
        def _run_bt():
            try:
                # Bước 1: Tải dữ liệu
                with _bt_lock:
                    _bt_jobs[bt_id]["step"] = "loading"
                    _bt_jobs[bt_id]["status"] = "running"
 
                lookback = max(365, (n_tests * step + win_size) * 3)
                df, err = fetch_realtime_ohlcv(
                    symbol=symbol, interval="1d",
                    lookback_days=lookback,
                    tail=n_tests * step + win_size + 20,
                )
                if err or df.empty:
                    raise RuntimeError(err or f"Không có dữ liệu cho {symbol}.")
 
                def _cb(progress: dict):
                    tp_list = progress.get("test_points", [])
                    with _bt_lock:
                        j = _bt_jobs.get(bt_id, {})
                        # Append latest test point
                        if progress.get("latest"):
                            j["test_points"] = j.get("test_points", []) + [progress["latest"]]
                        j["partial"] = progress.get("partial", {})
                        j["step"] = progress.get("current_step", "running")
 
                # Bước 2: Chạy backtest
                def _step_cb(step_name: str):
                    with _bt_lock:
                        if bt_id in _bt_jobs:
                            _bt_jobs[bt_id]["step"] = step_name
 
                from datetime import datetime as _dt2
                _ts = _dt2.now().strftime("%Y%m%d_%H%M")
                os.makedirs("backtest_result", exist_ok=True)
                _json_path = os.path.join("backtest_result", f"backtest_{symbol}_{_ts}.json")

                summary = engine.run(
                    df=df,
                    symbol=symbol,
                    timeframe="1 day",
                    n_tests=n_tests,
                    window_size=win_size,
                    step=step,
                    callback=lambda p: _bt_update(bt_id, p),
                    result_path=_json_path,
                )
 
                # Test points are already tracked inside summary with their cumulative PnL

                with _bt_lock:
                    _bt_jobs[bt_id]["status"]      = "done"
                    _bt_jobs[bt_id]["summary"]     = asdict(summary)
                    _bt_jobs[bt_id]["test_points"] = summary.test_points
                    _bt_jobs[bt_id]["partial"]     = {
                        "n_completed":     summary.n_tests,
                        "acc_full":        summary.acc_full,
                        "acc_no_alpha":    summary.acc_no_alpha,
                        "alpha_lift":      summary.alpha_lift,
                        "n_valid_full":    summary.n_long_full + summary.n_short_full,
                        "n_valid_no":      summary.n_long_no_alpha + summary.n_short_no_alpha,
                        "n_correct_full":  round((summary.acc_full / 100) * (summary.n_long_full + summary.n_short_full)),
                        "n_correct_no":    round((summary.acc_no_alpha / 100) * (summary.n_long_no_alpha + summary.n_short_no_alpha)),
                        "pnl_full":        summary.pnl_full,
                        "pnl_no_alpha":    summary.pnl_no_alpha,
                    }

                # Lưu biểu đồ PNG vào backtest_result/
                try:
                    from utils.static_util import generate_backtest_summary_chart
                    png_path = os.path.join("backtest_result", f"backtest_{symbol}_{_ts}.png")
                    generate_backtest_summary_chart(asdict(summary), png_path)
                except Exception as chart_exc:
                    print(f"[BT] Cảnh báo — không lưu được biểu đồ: {chart_exc}")
 
            except Exception as exc:
                with _bt_lock:
                    if bt_id in _bt_jobs:
                        _bt_jobs[bt_id]["status"] = "error"
                        _bt_jobs[bt_id]["error"]  = str(exc)
                print(f"[BT] Lỗi backtest {bt_id}: {exc}")
 
        threading.Thread(target=_run_bt, daemon=True).start()
        _cleanup_bt_jobs()
        return jsonify({"job_id": bt_id})
 
    except Exception as e:
        return jsonify({"error": str(e)})
 

def _bt_update(bt_id: str, progress: dict):
    from dataclasses import asdict as _asdict, fields as _fields
    with _bt_lock:
        j = _bt_jobs.get(bt_id)
        if not j:
            return
        if progress.get("latest"):
            j["test_points"] = j.get("test_points", []) + [progress["latest"]]
        raw_partial = progress.get("partial", {})
        # PartialSummary là dataclass → dùng asdict(); nếu đã là dict thì giữ nguyên
        if hasattr(raw_partial, "__dataclass_fields__"):
            j["partial"] = _asdict(raw_partial)
        elif isinstance(raw_partial, dict):
            j["partial"] = raw_partial
        else:
            j["partial"] = {}
 
 
@app.route("/api/backtest/status/<bt_id>")
def backtest_status(bt_id: str):
    with _bt_lock:
        job = _bt_jobs.get(bt_id)
    if not job:
        return jsonify({"error": "Job không tồn tại."}), 404
    return jsonify({
        "status":      job["status"],
        "step":        job.get("step", ""),
        "partial":     job.get("partial", {}),
        "test_points": job.get("test_points", []),
        "summary":     job.get("summary"),
        "error":       job.get("error", ""),
        "latest":      job["test_points"][-1] if job.get("test_points") else None,
    })
 
 
@app.route("/api/backtest/stop/<bt_id>", methods=["POST"])
def backtest_stop(bt_id: str):
    with _bt_lock:
        job = _bt_jobs.get(bt_id)
    if job and job.get("engine"):
        job["engine"].stop()
        with _bt_lock:
            _bt_jobs[bt_id]["status"] = "stopped"
    return jsonify({"success": True})
 
 
@app.route("/api/backtest/result/<bt_id>")
def backtest_result(bt_id: str):
    with _bt_lock:
        job = _bt_jobs.get(bt_id)
    if not job:
        return jsonify({"error": "Job không tồn tại."}), 404
    return jsonify(job.get("summary") or {"error": "Chưa hoàn thành."})

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    Path("templates").mkdir(exist_ok=True)
    Path("static").mkdir(exist_ok=True)
    rt_avail = check_vnstock_available()
    api_key  = os.environ.get("GROQ_API_KEY", "")
    print("=" * 60)
    print("  QuantAgent VN — Vietnamese Stock Market Analysis")
    print("  Powered by Groq API — ultra-fast inference")
    print(f"  Agent model  : {DEFAULT_CONFIG['agent_llm_model']}")
    print(f"  Vision model : {DEFAULT_CONFIG['graph_llm_model']}")
    print(f"  Data source  : Real-time via vnstock (VCI / MSN)")
    print(f"  Groq API key : {'✓ configured' if api_key else '⚠  not set (enter in UI)'}")
    if not rt_avail:
        print("  ⚠️  vnstock chưa cài — chạy: pip install vnstock")
    print("=" * 60)
    app.run(debug=False, host="127.0.0.1", port=5000, threaded=True, use_reloader=False)