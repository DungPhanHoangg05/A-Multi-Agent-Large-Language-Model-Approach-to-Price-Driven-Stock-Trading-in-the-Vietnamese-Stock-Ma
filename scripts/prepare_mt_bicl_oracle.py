"""Khóa corpus synthetic/oracle và chuẩn bị batch preflight, chỉ chạy offline."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.bayesian_memory import atomic_write_json, read_json
from core.mt_bicl_bank import content_hash, read_protocol
from core.mt_bicl_batches import CONTEXT_SHA256, TrainingBatchSource, load_context
from core.mt_bicl_oracle import FiniteBayesOracle
from core.mt_bicl_oracle_reference import EnumerationOracle
from core.mt_bicl_simulator import FiniteSimulator, pair_inputs
from scripts.verify_mt_bicl_protocol import validate_bundle, verify_sources

NAMESPACE = ROOT/"outputs/bayesian_benchmark/mt_bicl_v1"
DEFAULT_OUTPUT = NAMESPACE/"inputs/synthetic_oracle_v1.json"
CODE = ("core/mt_bicl_simulator.py", "core/mt_bicl_oracle.py", "core/mt_bicl_oracle_reference.py",
        "core/mt_bicl_batches.py", "scripts/prepare_mt_bicl_oracle.py")


def pooling_control(fixture: dict[str, Any]) -> dict[str, Any]:
    """Tái dựng control đã khóa, giữ ID riêng cho observations có giá trị bằng nhau."""
    def task(name: str, count: int, y: int) -> dict[str, Any]:
        """Dùng đúng x/count/nhãn từ fixture đặc tả, không chọn bằng kết quả oracle."""
        return {"task_id": name, "observations": [
            {"observation_id": f"{name}:{i}", "x": list(fixture["x"]), "y": y} for i in range(count)]}
    return {"prior": [task(row["task_id"], row["distinct_observations"], row["y"])
                      for row in fixture["prior_tasks"]],
            "target": task("control-T", fixture["target_context"]["distinct_observations"],
                           fixture["target_context"]["y"]),
            "query": {"observation_id": "control-Q", "x": list(fixture["query_x"])}}


def prepare(root: Path = ROOT) -> dict[str, Any]:
    """Sinh đúng 5.000 test/5.000 cặp và so mọi dự báo bằng enumeration scalar riêng."""
    protocol = read_protocol(root)
    directory = root/"docs/plan/week10"
    validate_bundle((directory/"protocol_v1.json").read_bytes(),
                    {name: (directory/name).read_bytes() for name in protocol["artifacts"]})
    verify_sources(root, protocol)
    simulator = FiniteSimulator.from_locked(root)
    oracle, reference = FiniteBayesOracle(simulator), EnumerationOracle(simulator.config)
    maxima = {"probability": 0., "log_probability_one": 0., "log_probability_zero": 0.}
    comparisons = 0

    def checked(data: dict[str, Any], *, pooled: bool = False) -> dict[str, Any]:
        """So cả hai log probability, không chỉ p đã làm tròn hoặc một vài fixture."""
        nonlocal comparisons
        actual = oracle.predict(data, pooled=pooled)
        expected = reference.predict(data, pooled=pooled)
        for key in maxima:
            difference = abs(actual[key]-expected[key])
            maxima[key] = max(maxima[key], difference)
            if difference > 1e-12:
                raise ValueError("Oracle khác enumeration độc lập: "+key)
        if actual["normalization_error"] > 1e-12:
            raise ValueError("Joint oracle không chuẩn hóa")
        comparisons += 1
        return actual

    fixture = read_json(directory/"protocol_fixtures_v1.json")["pooling_control"]
    control_input = pooling_control(fixture)
    control = {"input": control_input, "hierarchical": checked(control_input),
               "pooled": checked(control_input, pooled=True)}
    for key, expected_key in (("hierarchical", "expected_hierarchical_p"), ("pooled", "expected_pooled_p")):
        if abs(control[key]["probability"]-fixture[expected_key]) > fixture["absolute_tolerance"]:
            raise ValueError("Control không khớp giá trị đã khóa")
    tests, pairs = [], []
    for index in range(protocol["mechanism_gate"]["synthetic_episodes"]):
        episode = simulator.episode("synthetic_test", index)
        episode["oracle"] = checked(episode["input"])
        episode["pooled"] = checked(episode["input"], pooled=True)
        tests.append(episode)
        if (index+1) % 1000 == 0:
            print(f"Đã đối chiếu {index+1}/5000 episode test.", flush=True)
    swap_spec = protocol["mechanism_gate"]["prior_swap"]
    for index in range(swap_spec["attempt_pairs"]):
        pair = simulator.prior_swap_pair(index)
        a, b = pair_inputs(pair)
        pair["oracle_a"], pair["oracle_b"] = checked(a), checked(b)
        pair["oracle_delta_b_minus_a"] = pair["oracle_b"]["probability"]-pair["oracle_a"]["probability"]
        pair["eligible"] = abs(pair["oracle_delta_b_minus_a"]) >= swap_spec["minimum_oracle_delta"]
        pairs.append(pair)
        if (index+1) % 1000 == 0:
            print(f"Đã đối chiếu {index+1}/5000 cặp thay prior.", flush=True)
    source = TrainingBatchSource(simulator, load_context(root))
    preflight = []
    for step in range(protocol["training"]["real_pipeline_preflight_steps"]):
        batch = source.batch(step, model_seed=0, preflight=True)
        preflight.append(content_hash(batch))
    eligible = sum(pair["eligible"] for pair in pairs)
    return {"version": "mt_bicl_synthetic_oracle_v1", "protocol_sha256": hashlib.sha256(
                (directory/"protocol_v1.json").read_bytes()).hexdigest(),
            "simulator_sha256": protocol["artifacts"]["simulator_v1.json"],
            "context_sha256": CONTEXT_SHA256,
            "identity": {"code_sha256": {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in CODE},
                         "runtime": protocol["runtime"]},
            "verification": {"oracle_status": "PASS", "independent_predictions": comparisons,
                             "maximum_absolute_differences": maxima,
                             "synthetic_K_histogram": dict(sorted(Counter(str(e["oracle"]["K"]) for e in tests).items())),
                             "synthetic_m_histogram": dict(sorted(Counter(str(e["oracle"]["m"]) for e in tests).items())),
                             "eligible_prior_swap_pairs": eligible,
                             "prior_swap_support": "SUFFICIENT" if eligible >= swap_spec["minimum_eligible_pairs"]
                                                   else "INCONCLUSIVE_BLOCK_DEVELOPMENT"},
            "pooling_control": control, "synthetic_test": tests, "prior_swap_pairs": pairs,
            "preflight": {"status": "DATA_PREPARED_OPTIMIZER_NOT_RUN", "steps": len(preflight),
                          "step_batch_sha256": preflight, "first_batch": source.batch(0, model_seed=0, preflight=True),
                          "train_query_counts": {s: len(rows) for s, rows in source.groups.items()},
                          "weights_retained": False},
            "learner_mechanism_status": "NOT_RUN_NO_MODEL", "training_allowed": False,
            "decision_calls_allowed": False}


def main() -> None:
    """Ghi mới hoặc cold-rebuild kiểm artifact, không reseal bằng cờ cập nhật checksum."""
    parser = argparse.ArgumentParser(description="Chuẩn bị oracle/corpus MT-BICL offline")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(NAMESPACE.resolve()) or output.suffix != ".json" or output.name.startswith("."):
        parser.error("Output phải trong namespace MT-BICL")
    if not args.check and output.exists():
        parser.error("Không ghi đè artifact đã lưu")
    payload = prepare()
    envelope = {"payload": payload, "sha256": content_hash(payload)}
    if args.check:
        if read_json(output) != envelope:
            raise ValueError("Corpus/oracle khác cold-rebuild")
    else:
        atomic_write_json(output, envelope)
    print(f"Oracle độc lập PASS; {payload['verification']['eligible_prior_swap_pairs']}/5000 cặp đủ delta; "
          "100 batch preflight đã chuẩn bị, chưa chạy optimizer/learner/LLM.")


if __name__ == "__main__":
    main()
