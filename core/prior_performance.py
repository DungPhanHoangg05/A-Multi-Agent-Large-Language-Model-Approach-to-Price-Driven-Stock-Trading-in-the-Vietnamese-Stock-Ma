"""Nghiệm thu hiệu năng prior công khai trên nguồn đã khóa, không gọi Decision."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import gc
import hashlib
import os
from pathlib import Path
import platform
from time import perf_counter_ns
from typing import Any, Iterator
from unittest.mock import patch

from core.candidate_cohort import CODE_FILES, registry
from core.historical_signals import digest
from core.pit_price_features import extract_pit_price_features
from core.price_feature_index import build_price_feature_index
from core.prior_context import PriorContextAdapter
from core.prior_evidence_v2 import format_evidence_prefix, normalize_evidence_config
from core.prior_example_selection import PriceExampleSelector
from core.prior_prompt import CANDIDATE_PROFILES, build_prior_request
from core.research_cohort import read_envelope
from core.research_input_lock import _write_once, runtime_identity
from scripts.benchmark_bayesian_retriever import THRESHOLD_NS, benchmark as legacy_benchmark, measure, summarize, validate_counts

ROOT = Path(__file__).resolve().parents[1]
VERSION = "prior_performance_v1"
TRAIN_REPORT = "outputs/bayesian_benchmark/train_validation_v1.json"
TRAIN_SHA256 = "5fbabffcc8673144e24d72fb67e986bfd99e1b22e4449acc52e6a398c37e0df0"
INDEX = "outputs/bayesian_benchmark/price_features/train_validation_index_v1.json"
DEFAULT_REPORT = "outputs/bayesian_benchmark/prior_performance_v2.json"
STAGES = ("retrieval", "prefix", "retrieval_and_prefix", "feature_retrieval_and_prefix")


def code_identity() -> dict[str, str]:
    """Ghim text LF, gồm benchmark kế thừa và mọi API thực sự được đo."""
    return {name: hashlib.sha256((ROOT/name).read_text("utf-8").encode("utf-8")).hexdigest()
            for name in (*CODE_FILES, "core/prior_performance.py", "scripts/benchmark_bayesian_retriever.py",
                         "scripts/verify_bayesian_prior.py")}


def train_contexts(train: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Toàn bộ query đã đăng ký, không chọn subset theo latency hoặc readiness."""
    rows = sorted(train["points"], key=lambda row:(row["as_of_date"], row["symbol"]))
    by_id = {r["episode_id"]: r for r in records}
    expected = {key for fold in train["folds"].values() for item in fold["symbols"].values() for key in item["query_ids"]}
    if (train["report_version"] != "train_pit_diagnostics_v1" or train["status"] != "COMPLETE"
            or train["registry"] != registry() or train["query_count"] != 651 or len(rows) != 651
            or len({r["episode_id"] for r in rows}) != 651 or expected != {r["episode_id"] for r in rows}):
        raise ValueError("Roster benchmark khác 651 query/fold/registry đã đăng ký")
    for row in rows:
        record = by_id.get(row["episode_id"])
        if (record is None or any(row[key] != record[key] for key in ("symbol", "as_of_date", "regime"))
                or train["regime_fits"][row["as_of_date"]]["train_end_date"] != row["as_of_date"]):
            raise ValueError("Query benchmark khác bank hoặc prefix model PIT")
    return rows


@contextmanager
def hot_guard() -> Iterator[None]:
    """Chặn mọi I/O/LLM/refit trong API hot, giữ nguyên producer/validator/copy."""
    with ExitStack() as stack:
        for target in ("builtins.open", "pathlib.Path.open", "pathlib.Path.read_bytes", "pathlib.Path.read_text",
                       "socket.socket.connect", "socket.getaddrinfo", "dotenv.load_dotenv", "dotenv.dotenv_values",
                       "httpx.Client.send", "httpx.AsyncClient.send", "requests.sessions.Session.request",
                       "core.bayesian_memory.read_json", "core.bayesian_retriever.read_json",
                       "core.bayesian_memory.HistoricalMemory.load", "core.price_feature_index._fit",
                       "core.regime_detector.GaussianHMM.fit", "sklearn.preprocessing.StandardScaler.fit",
                       "core.historical_signals.HistoricalSignalExtractor.extract"):
            stack.enter_context(patch(target, side_effect=AssertionError("Hot query không được I/O/API/refit")))
        yield


class PerformanceInputs:
    """Nguồn cold đã kiểm; feature và evidence vẫn tính mới ở từng invocation."""

    def __init__(self) -> None:
        started = perf_counter_ns()
        total_started = started
        self.adapter = PriorContextAdapter({"enable_bayesian_prior": True})
        self.cold = {"adapter_load_ns": perf_counter_ns()-started}
        path = ROOT/TRAIN_REPORT
        if hashlib.sha256(path.read_bytes()).hexdigest() != TRAIN_SHA256:
            raise ValueError("Report train khác SHA-256 đã đăng ký; không tự thay roster")
        self.train = read_envelope(path)
        for name, sha in self.train["sources"].items():
            self.adapter._files.pin(name, sha)
        self.adapter._files.pin(TRAIN_REPORT, TRAIN_SHA256)
        self.rows = train_contexts(self.train, self.adapter._retriever._memory.records)
        started = perf_counter_ns()
        self.index = self.adapter.load_price_feature_index(INDEX)
        self.cold["index_load_semantic_rebuild_ns"] = perf_counter_ns()-started
        started = perf_counter_ns()
        inputs = self.adapter._price_feature_index_inputs()
        rebuilt = build_price_feature_index(**inputs)
        self.cold["index_feature_extraction_and_scaler_fit_ns"] = perf_counter_ns()-started
        if rebuilt.identity != self.index.identity:
            raise ValueError("Index tái fit khác index đã khóa")
        self.calendar = inputs["calendar"]
        self.selector = PriceExampleSelector(self.index, self.calendar)
        self.by_id = self.adapter._retriever._verified_by_id
        self.queries = [{"symbol": r["symbol"], "as_of_date": r["as_of_date"], "current_regime": r["regime"],
                         "current_signals": deepcopy(self.by_id[r["episode_id"]]["agent_signals"])} for r in self.rows]
        self.cold["source_preparation_total_ns"] = perf_counter_ns()-total_started

    def feature(self, slot: int) -> dict[str, Any]:
        """Extractor public trên RAM; giữ proof giống adapter, không gọi verifier file hot."""
        query, adapter = self.queries[slot], self.adapter
        symbol, cutoff = query["symbol"], query["as_of_date"]
        frame, events = adapter._prices[symbol]
        result = extract_pit_price_features(frame, events, self.calendar, cutoff, source=adapter._price_manifest)
        result.update(symbol=symbol, source_provenance={"prices": deepcopy(adapter._price_sources[symbol]),
                                                      "calendar": deepcopy(adapter._vnindex_source)})
        return result

    def retrieve(self, name: str, slot: int, feature: dict[str, Any]) -> dict[str, Any]:
        """Biên API công khai; mọi validation và bản sao đầu ra nằm trong timer."""
        retriever, query = self.adapter._retriever, self.queries[slot]
        if name == "v1_train_same_symbol":
            return retriever.retrieve(**query, mode="bayesian_regime", scope="same_symbol", k=3, seed=42)
        if name == "C0":
            return retriever.retrieve_evidence(**query, config=normalize_evidence_config())
        return retriever.quality_evidence(**query, selector=self.selector, query_features=feature,
                                          gate_version=CANDIDATE_PROFILES[name][0])

    def prefix(self, name: str, evidence: dict[str, Any], feature: dict[str, Any]) -> str:
        """Builder public có validator nguồn; không gọi renderer private để giảm số đo."""
        if name == "v1_train_same_symbol":
            from core.bayesian_retriever import format_compact_prior_prefix
            return format_compact_prior_prefix(evidence["tasks"], evidence["stats"])
        if name == "C0":
            return format_evidence_prefix(evidence)
        return build_prior_request(evidence, name, self.adapter._retriever,
                                   selector=self.selector, query_features=feature)["prefix"]

    def references(self) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        """Đối chiếu mọi evidence với W6-14 ngoài timer, không cache đáp án trong API."""
        features, references = [], {name:[] for name in ("v1_train_same_symbol", *registry()["order"])}
        for slot, row in enumerate(self.rows):
            feature = self.feature(slot)
            if feature["status"] != row["feature_status"] or feature["reasons"] != row["feature_reasons"]:
                raise ValueError("Feature query khác chẩn đoán train đã khóa")
            features.append(feature)
            for name in references:
                evidence = self.retrieve(name, slot, feature)
                if name != "v1_train_same_symbol":
                    checksum = evidence["evidence_sha256"] if name == "C0" else evidence["base_evidence_sha256"]
                    if checksum != row["candidates"][name]["evidence_sha256"]:
                        raise ValueError("Evidence mới khác semantic W6-14")
                references[name].append(evidence)
        return features, references


def benchmark(*, warmup: int = 100, samples: int = 1000) -> dict[str, Any]:
    """Đo tuần tự và giữ cả FAIL; không trừ overhead hoặc loại outlier."""
    validate_counts(warmup, samples)
    code = code_identity()
    legacy = legacy_benchmark(warmup=warmup, samples=samples)
    inputs = PerformanceInputs()
    started = perf_counter_ns()
    features, references = inputs.references()
    inputs.cold["semantic_parity_all_queries_ns"] = perf_counter_ns()-started
    modes = {}
    with hot_guard():
        feature_times = measure([lambda slot=slot:inputs.feature(slot) for slot in range(len(features))],
                                features, warmup=warmup, samples=samples)
        for name, expected in references.items():
            prefixes = [inputs.prefix(name, value, feature) for value, feature in zip(expected, features)]
            query_before, expected_before = digest(inputs.queries), digest(expected)
            def combined(slot: int, extract: bool) -> tuple[dict[str, Any], str]:
                feature = inputs.feature(slot) if extract and name not in ("C0", "v1_train_same_symbol") else features[slot]
                evidence = inputs.retrieve(name, slot, feature)
                return evidence, inputs.prefix(name, evidence, feature)
            operations = {
                "retrieval": [lambda slot=slot:inputs.retrieve(name, slot, features[slot]) for slot in range(len(features))],
                "prefix": [lambda slot=slot:inputs.prefix(name, expected[slot], features[slot]) for slot in range(len(features))],
                "retrieval_and_prefix": [lambda slot=slot:combined(slot, False) for slot in range(len(features))],
                "feature_retrieval_and_prefix": [lambda slot=slot:combined(slot, True) for slot in range(len(features))]}
            stages = {}
            for stage, operations_stage in operations.items():
                outputs = expected if stage == "retrieval" else prefixes if stage == "prefix" else list(zip(expected, prefixes))
                times = measure(operations_stage, outputs, warmup=warmup, samples=samples)
                stages[stage] = {"summary": summarize(times), "samples_ns": times}
                print(f"{name}/{stage}: p95={stages[stage]['summary']['p95_ms']:.3f} ms", flush=True)
            if digest(inputs.queries) != query_before or digest(expected) != expected_before:
                raise ValueError("API/formatter sửa query hoặc bằng chứng tham chiếu")
            passed = stages["retrieval"]["summary"]["p95_ns"] < THRESHOLD_NS
            modes[name] = {"gate_passed": passed, "stages": stages,
                "feature_required": name not in ("C0", "v1_train_same_symbol"),
                "evidence_sha256": [digest(value) for value in expected], "prefix_sha256": [digest(value) for value in prefixes]}
            print(f"{name}: p95 retrieval={stages['retrieval']['summary']['p95_ms']:.3f} ms; "
                  f"gate={'PASS' if passed else 'FAIL'}", flush=True)
    inputs.adapter.verify_sources()
    if code_identity() != code:
        raise ValueError("Code đổi trong lúc đo; không phát hành report")
    return {"report_version": VERSION, "status": "PASS" if legacy["status"] == "PASS" and all(m["gate_passed"] for m in modes.values()) else "FAIL",
        "measured_at_utc": datetime.now(timezone.utc).isoformat(), "code_sha256": code, "runtime": runtime_identity(),
        "environment": {"platform": platform.platform(), "processor": platform.processor(), "logical_cpu_count": os.cpu_count(),
            "gc_enabled": gc.isenabled(), "load_note": "Đo tuần tự, không chạy gate/unit đồng thời; không bỏ mẫu ngoại lai."},
        "method": {"warmup": warmup, "samples": samples, "percentile": "nearest_rank_ceil_0.95_n", "threshold_ns": THRESHOLD_NS,
            "query_rotation": "sample_index % 651; reset sau warm-up", "scope": "same_symbol", "k": 3, "seed": 42,
            "transform_cost": "Trong retrieval public, không transform trước timer.",
            "feature_cost": "Extractor public trên RAM có proof; verifier file/adapter/HMM là cold riêng.",
            "prefix_cost": "Builder public có semantic validation; không dùng renderer private hoặc cache đáp án."},
        "sources": inputs.adapter.source_hashes, "registry": registry(), "cold": inputs.cold,
        "contexts": inputs.queries, "episode_ids": [r["episode_id"] for r in inputs.rows],
        "feature_extraction": {"summary": summarize(feature_times), "samples_ns": feature_times},
        "legacy": legacy, "modes": modes, "checks": {"semantic_parity_651": True, "hot_io_refit_blocked": True,
            "inputs_unchanged": True, "every_sample_matches_reference": True, "decision_calls": 0},
        "limitations": ["Thời gian phụ thuộc máy/tải nền; report FAIL phải giữ lại trước khi đo lại.",
            "V1 W3 có 16 context/hai scope riêng; chỉ v1_train_same_symbol so trực tiếp cùng 651 query với C0–C3.",
            "Chi phí cold có semantic rebuild toàn index/scaler; không là thời gian gọi LLM hoặc hiệu quả đầu tư."]}


def verify_legacy(report: dict[str, Any], inputs: PerformanceInputs, method: dict[str, Any]) -> None:
    """Giữ đúng roster/scope v1 và kiểm lại ranking/counts/prefix bằng API public."""
    from core.bayesian_memory import read_json
    from core.bayesian_retriever import MODES, SCOPES, VERSIONS
    from scripts.benchmark_bayesian_retriever import SMOKE_PATH, assert_evidence, file_hash, select_contexts, stage_receipt
    from scripts.verify_bayesian_prior import check_result

    smoke = read_json(SMOKE_PATH)
    pins = {**smoke["protected_file_sha256"], str(SMOKE_PATH.relative_to(ROOT)): file_hash(SMOKE_PATH)}
    assert_evidence(pins)
    records = inputs.adapter._retriever._memory.records
    contexts = select_contexts(smoke, records)
    source_paths = ("scripts/benchmark_bayesian_retriever.py", "core/bayesian_retriever.py", "core/bayesian_memory.py",
                    "core/backtest_engine.py", "core/execution_prices.py", "scripts/verify_bayesian_prior.py")
    expected_method = {"clock": "perf_counter_ns", "percentile": "nearest_rank_ceil_0.95_n", "sequential": True,
        "warmup_per_mode_per_stage": method["warmup"], "samples_per_mode_per_stage": method["samples"],
        "context_count": 16, "queries_per_mode": 32, "query_rotation": "sample_index % 32; reset after warmup",
        "mode_order": sorted(MODES), "stage_order": ["retrieval", "formatter", "retrieval_and_format"],
        "k": 3, "seed": 42, "scopes": sorted(SCOPES), "retrieval_gate_p95_ns_strictly_below": THRESHOLD_NS}
    if (report["format_version"] != 1 or report["bank_sha256"] != smoke["bank_sha256"]
            or report["run_signature"] != smoke["run_signature"] or report["real_bank_records"] != 852
            or report["versions"] != VERSIONS or report["protected_file_sha256"] != pins
            or report["source_sha256"] != {name:file_hash(ROOT/name) for name in source_paths}
            or report["contexts"] != [{key:context[key] for key in ("query", "source")} for context in contexts]
            or any(digest(report["method"].get(key)) != digest(value) for key, value in expected_method.items())
            or set(report["modes"]) != set(MODES)):
        raise ValueError("Report v1 khác roster/context/scope/code/nguồn đã khóa")
    queries = []
    with hot_guard():
        for mode in sorted(MODES):
            mode_queries = []
            for context in contexts:
                for scope in sorted(SCOPES):
                    query = {**deepcopy(context["query"]), "mode": mode, "scope": scope, "k": 3}
                    result = inputs.adapter._retriever.retrieve(**query)
                    prefix = check_result(records, query, result)
                    case = next(c for c in context["cases"] if (c["mode"], c["scope"], c["k"]) == (mode, scope, 3))
                    if (prefix != case["prefix"] or result["stats"] != case["stats"]
                            or any(result["metadata"][key] != value for key, value in case["metadata"].items())):
                        raise ValueError("Semantic v1 khác smoke PIT")
                    mode_queries.append(query)
                    queries.append({"query": query, "selected_ids": result["metadata"]["selected_ids"],
                        "eligible_count": result["metadata"]["eligible_count"], "population_count": result["stats"]["population_count"]})
            for stage in ("retrieval", "formatter", "retrieval_and_format"):
                measured = report["modes"][mode][stage]
                if digest(measured) != digest(stage_receipt(measured["samples_ns"], mode_queries)):
                    raise ValueError("Percentile từng scope v1 khác mẫu thô")
    if report["queries"] != queries:
        raise ValueError("Query/IDs/counts v1 khác API đã tái tính")


def _verify_report(report: dict[str, Any]) -> None:
    """Tái tính percentile/gate và kiểm nguồn/code cùng semantic API ngoài timer."""
    if report["report_version"] != VERSION or report["code_sha256"] != code_identity() or report["runtime"] != runtime_identity():
        raise ValueError("Report hiệu năng khác version/code/runtime")
    method = report["method"]
    validate_counts(method["warmup"], method["samples"])
    expected_method = {"threshold_ns": THRESHOLD_NS, "percentile": "nearest_rank_ceil_0.95_n",
        "scope": "same_symbol", "k": 3, "seed": 42, "query_rotation": "sample_index % 651; reset sau warm-up"}
    if any(digest(method.get(key)) != digest(value) for key, value in expected_method.items()):
        raise ValueError("Report tự đổi ngưỡng/percentile/scope/K/seed/thứ tự query")
    if set(report["modes"]) != {"v1_train_same_symbol", *registry()["order"]}:
        raise ValueError("Report thiếu hoặc thêm mode chưa đăng ký")
    def stage_check(stage: dict[str, Any]) -> None:
        if (len(stage["samples_ns"]) != method["samples"]
                or digest(stage["summary"]) != digest(summarize(stage["samples_ns"]))):
            raise ValueError("Mẫu thô/percentile không khớp")
    stage_check(report["feature_extraction"])
    for value in report["modes"].values():
        if set(value["stages"]) != set(STAGES):
            raise ValueError("Thiếu stage đo đầy đủ")
        for stage in value["stages"].values():
            stage_check(stage)
        if (type(value["gate_passed"]) is not bool
                or value["gate_passed"] != (value["stages"]["retrieval"]["summary"]["p95_ns"] < THRESHOLD_NS)):
            raise ValueError("Gate hiệu năng khác mẫu thô")
    from core.bayesian_retriever import MODES
    if set(report["legacy"]["modes"]) != set(MODES):
        raise ValueError("Report v1 thiếu hoặc thêm mode")
    for value in report["legacy"]["modes"].values():
        for stage in ("retrieval", "formatter", "retrieval_and_format"):
            stage_check(value[stage])
        if (type(value["gate_passed"]) is not bool
                or value["gate_passed"] != (value["retrieval"]["summary"]["p95_ns"] < THRESHOLD_NS)):
            raise ValueError("Gate v1 khác mẫu thô")
    legacy_passed = all(v["gate_passed"] for v in report["legacy"]["modes"].values())
    if report["legacy"]["status"] != ("PASS" if legacy_passed else "FAIL"):
        raise ValueError("Status v1 khác các gate")
    inputs = PerformanceInputs()
    verify_legacy(report["legacy"], inputs, method)
    features, references = inputs.references()
    if (report["sources"] != inputs.adapter.source_hashes or report["contexts"] != inputs.queries
            or report["episode_ids"] != [r["episode_id"] for r in inputs.rows] or report["registry"] != registry()
            or set(report["modes"]) != set(references)):
        raise ValueError("Report khác nguồn/roster/registry đã khóa")
    with hot_guard():
        for name, expected in references.items():
            value = report["modes"][name]
            if (type(value["feature_required"]) is not bool
                    or value["feature_required"] != (name not in ("C0", "v1_train_same_symbol"))
                    or value["evidence_sha256"] != [digest(e) for e in expected]
                    or value["prefix_sha256"] != [digest(inputs.prefix(name, e, f)) for e, f in zip(expected, features)]):
                raise ValueError("Semantic API khác report")
    passed = all(v["gate_passed"] for v in report["modes"].values()) and report["legacy"]["status"] == "PASS"
    if report["status"] != ("PASS" if passed else "FAIL"):
        raise ValueError("Status tổng khác các gate")
    checks = {"semantic_parity_651": True, "hot_io_refit_blocked": True,
              "inputs_unchanged": True, "every_sample_matches_reference": True, "decision_calls": 0}
    cold_fields = {"adapter_load_ns", "index_load_semantic_rebuild_ns", "index_feature_extraction_and_scaler_fit_ns",
                   "source_preparation_total_ns", "semantic_parity_all_queries_ns"}
    if (digest(report["checks"]) != digest(checks) or set(report["cold"]) != cold_fields
            or any(type(value) is not int or value < 0 for value in report["cold"].values())):
        raise ValueError("Report thiếu kiểm tra/cost cold hoặc sai kiểu native")
    inputs.adapter.verify_sources()


def verify_report(report: dict[str, Any]) -> None:
    """Chuẩn hóa lỗi schema thành ValueError; không bỏ qua dữ liệu bị hỏng."""
    try:
        _verify_report(report)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("Schema report hiệu năng không hợp lệ") from exc


def run_performance(report_path: Path, *, verify_only: bool = False) -> dict[str, Any]:
    """CLI tạo envelope bất biến, giữ cả FAIL; verify không đo lại hay ghi file."""
    if (not report_path.resolve().is_relative_to((ROOT/"outputs/bayesian_benchmark").resolve())
            or report_path.suffix != ".json" or report_path.name.startswith(".env")):
        raise ValueError("Report hiệu năng cần JSON riêng trong outputs/bayesian_benchmark")
    if verify_only:
        report = read_envelope(report_path)
        verify_report(report)
        return report
    if report_path.exists():
        raise ValueError("Không ghi đè report hiệu năng; cần đường mới cho lượt đo mới")
    report = benchmark()
    _write_once(report_path, report)
    return report
