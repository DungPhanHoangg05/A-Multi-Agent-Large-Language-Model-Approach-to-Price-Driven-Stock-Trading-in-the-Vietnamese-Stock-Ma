"""T28: kiểm hồi quy có chọn lọc và receipt cuối, tuyệt đối không gọi API."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
from importlib.metadata import version
from pathlib import Path
import platform
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from core.revision_minimal_bank import collect, runtime, verify_manifest
from core.revision_minimal_audit import audit_pairing
from core.revision_reproducibility import check_release as check_package, check_self_digest, digest, encoded, file_hash, offline_guard, read, require

OUTPUT = Path('outputs/revision/final_regression_v1')
ATTR_COMMIT = 'b3e0561366ad573c11148c2e1b4cadbee40765b7'
ATTR_APPEND = (b'core/revision_execution_final.py text eol=lf\n'
               b'scripts/analyze_revision_execution_final.py text eol=lf\n'
               b'tests/test_revision_execution_final.py text eol=lf\n')
PARENTS = ('sentiment_inventory_v1', 'sentiment_coverage_v1', 'sentiment_contract_v1',
           'alpha_registry_v1', 'alpha_contract_v1', 'alpha_selection_v1',
           'numeric_controls_design_v1', 'numeric_controls_v1', 'quantagent_attribution_v1',
           'fusion_prompt_audit_v1', 'execution_evidence_v1', 'execution_final_v1',
           'execution_sensitivity_v1', 'final_contracts_v1', 'reference_audit_v1',
           'clean_replay_v1', 'final_baselines_v1', 'final_temporal_v1', 'final_repeats_v1',
           'final_cost_integrity_v1', 'revision_minimal_final_v1')

# Chọn từng ca theo hợp đồng; không discover toàn suite hoặc chạy lại bootstrap/chart/model.
CASES = {
    'pairing_isolation': (
        'test_paired_protocol.PairedProtocolTests.test_one_decision_variant_failure_aborts_paired_point',
        'test_paired_protocol.PairedProtocolTests.test_split_graphs_execute_expected_nodes_and_preserve_control_fields',
        'test_paired_protocol.PairedProtocolTests.test_no_alpha_predictions_are_invariant_across_three_alpha_configs',
        'test_revision_r4_factorial.PromptLeakageTests.test_all_variant_sections_and_actual_content_are_isolated',
        'test_revision_r4_factorial.PromptLeakageTests.test_future_or_label_overlapping_donor_is_rejected',
        'test_revision_minimal_analysis.MinimalAnalysisTests.test_repeat_copy_prompt_change_missing_or_parent_change_are_rejected'),
    'pit_purge': (
        'test_revision_baseline_leakage.RevisionBaselineLeakageTests.test_future_price_and_volume_poison_does_not_change_cutoff_features',
        'test_revision_baseline_leakage.RevisionBaselineLeakageTests.test_date_only_next_day_explicit_availability_and_90_day_window',
        'test_revision_baseline_leakage.RevisionBaselineLeakageTests.test_time_split_purges_all_label_spans_touching_next_split',
        'test_revision_baseline_leakage.RevisionBaselineLeakageTests.test_imputer_scaler_and_selection_ignore_test_distribution',
        'test_revision_r2_leakage.RegimeLeakageTests.test_future_prices_and_volumes_do_not_change_context',
        'test_revision_r2_leakage.RegimeLeakageTests.test_validation_distribution_cannot_fit_thresholds',
        'test_revision_numeric_design_leakage.NumericDesignLeakageTests.test_eligibility_imputation_scaling_orientation_and_ranking_ignore_validation_test',
        'test_revision_numeric_design_leakage.NumericDesignLeakageTests.test_prediction_of_one_row_does_not_fit_other_prediction_rows',
        'test_revision_alpha_contract_leakage.AlphaContractLeakageTests.test_native_rowwise_counterexamples_are_detected_and_fail_causal_guard'),
    'prompt_budget': (
        'test_backtest_token_budget.BacktestTokenBudgetTests.test_backtest_decision_prompt_has_hard_character_budget',
        'test_revision_common_study.CallArchiveTests.test_6500_char_prompt_and_missing_context_are_stopped_before_network',
        'test_revision_r4_factorial.PromptLeakageTests.test_all_five_values_reach_actual_human_message_and_budget_guard',
        'test_revision_minimal.MinimalQueueTests.test_callback_rejects_changed_model_parameters_and_message'),
    'resume_raw_tamper': (
        'test_revision_minimal.MinimalQueueTests.test_whitelist_execution_and_resume_skip_successes',
        'test_revision_minimal.MinimalQueueTests.test_interruption_after_raw_replays_without_new_request',
        'test_revision_minimal.MinimalQueueTests.test_temporary_checkpoint_recovers_without_calls',
        'test_revision_minimal.MinimalQueueTests.test_tampered_raw_and_parent_fail_closed',
        'test_revision_minimal.MinimalQueueTests.test_resigned_parent_mismatch_and_duplicate_repeat_ids_rejected',
        'test_revision_minimal.MinimalQueueTests.test_resigned_wrong_context_does_not_replay',
        'test_revision_r4_factorial.ArchiveResumeTests.test_raw_response_resume_and_tamper_guard',
        'test_chart_rerun.ChartRerunTests.test_exact_archived_pattern_request_replays_without_sdk',
        'test_chart_rerun.ChartRerunTests.test_pattern_cache_miss_stops_before_client_creation'),
    'quota_retry': (
        'test_revision_minimal.MinimalQueueTests.test_one_key_shared_across_workers_and_origin_runs',
        'test_revision_minimal.MinimalQueueTests.test_provider_quota_state_prevents_early_reset',
        'test_revision_minimal.MinimalQueueTests.test_missing_ledger_never_silently_resets',
        'test_revision_minimal.MinimalQueueTests.test_format_retry_is_counted_and_keeps_repeat_identity',
        'test_revision_72h.QuotaTests.test_provider_pool_uses_another_key_after_one_exhausts_quota',
        'test_revision_72h.QuotaTests.test_pool_stops_only_after_all_allowed_keys_report_long_quota',
        'test_revision_72h.QuotaTests.test_short_rate_wait_is_retried_without_global_pause',
        'test_revision_common_study.CallArchiveTests.test_compound_retry_after_and_daily_quota_stop_before_fallback'),
    'metrics_ledger': (
        'test_revision_minimal_analysis.MinimalAnalysisTests.test_missing_duplicate_target_and_information_support_fail',
        'test_revision_minimal_analysis.MinimalAnalysisTests.test_macro_support_and_undefined_class_are_explicit',
        'test_revision_minimal_analysis.MinimalAnalysisTests.test_cash_and_two_leg_fee_ledger_match_independent_formula',
        'test_revision_final_baselines.FinalBaselineTests.test_hold_or_missing_pair_is_not_classifier_support',
        'test_revision_final_baselines.FinalBaselineTests.test_cohorts_do_not_backfill_bhn_or_pick_outcomes',
        'test_revision_baseline_leakage.RevisionDailyLedgerTests.test_continuous_hold_is_one_purchase_and_sale_across_gaps',
        'test_revision_execution_final.FinalExecutionTests.test_oracle_catches_pending_double_count_and_stock_sale_before_maturity'),
    'audit_guards': (
        'test_revision_regression.RegressionAuditTests.test_case_plan_rejects_duplicates_and_missing_names',
        'test_revision_regression.RegressionAuditTests.test_parent_source_and_output_tamper_fail_closed',
        'test_revision_regression.RegressionAuditTests.test_failed_skipped_or_expected_failure_cannot_pass',
        'test_revision_regression.RegressionAuditTests.test_output_path_never_overwrites_or_targets_paper',
        'test_revision_regression.RegressionAuditTests.test_historical_attributes_cannot_mask_runtime_changes'),
}


def output_folder(root: Path, output: Path) -> Path:
    """Chỉ tạo release con trực tiếp mới; không nhận paper, queue hay overwrite."""
    folder = (root / output).resolve()
    require(folder.parent == (root / 'outputs/revision').resolve() and not folder.exists(), 'Cần release mới trong outputs/revision')
    return folder


def load_cases(plan: dict[str, tuple[str, ...]]) -> unittest.TestSuite:
    """Khóa case IDs; sai tên hoặc trùng ca không được biến thành coverage PASS."""
    names = [name for group in plan.values() for name in group]
    require(bool(names) and len(names) == len(set(names)), 'Case plan rỗng hoặc trùng')
    suite = unittest.TestSuite()
    for name in names:
        loaded = unittest.defaultTestLoader.loadTestsFromName(name)
        tests = list(loaded)
        require(len(tests) == 1 and isinstance(tests[0], unittest.TestCase) and tests[0].id() == name, 'Không tìm đúng case: ' + name)
        suite.addTests(loaded)
    return suite


def historical_attributes(root: Path, expected: str, original: bytes) -> None:
    """Chỉ chấp nhận nguyên blob T16 cộng đúng ba eol rules T18 đã biết."""
    require(digest(original) == expected, 'Git blob không khớp hash T16')
    require((root / '.gitattributes').read_bytes() == original + ATTR_APPEND, 'Attributes đổi ngoài ba rules T18')


def verify_parent(root: Path, name: str, original: bytes | None = None) -> tuple[dict, set[str]]:
    """Đối soát từng byte; ngoại lệ duy nhất là non-runtime attributes T16 có blob gốc."""
    folder = root / 'outputs/revision' / name
    manifest = read(folder / 'manifest.json')
    self_digest = check_self_digest(manifest)
    observed = {**runtime(), 'jsonschema': version('jsonschema')}
    require(all(observed.get(k) == v for k, v in manifest.get('runtime', {}).items()), 'Runtime khác receipt: ' + name)
    paths = {(folder / 'manifest.json').relative_to(root).as_posix()}
    count = 0; historical = []
    for group, base in (('sources', root), ('outputs', folder)):
        for row in manifest[group]:
            path = (base / row['path']).resolve()
            require(path.is_relative_to(base.resolve()), 'Parent path vượt root')
            if file_hash(path) != row['sha256']:
                require(group == 'sources' and name == 'quantagent_attribution_v1' and row['path'] == '.gitattributes' and original is not None,
                        'Parent hash khác: ' + name + '/' + row['path'])
                historical_attributes(root, row['sha256'], original)
                historical.append({'path': row['path'], 'historical_sha256': row['sha256'], 'current_sha256': file_hash(path),
                                   'git_commit': ATTR_COMMIT, 'scope': 'Non-runtime: thêm đúng ba eol rules T18, không coi source cũ bằng source hiện tại.'})
            paths.add(path.relative_to(root.resolve()).as_posix()); count += 1
    return {'release': name, 'source_output_hashes': count, 'self_digest': self_digest,
            'status': 'PASS_WITH_HISTORICAL_NONRUNTIME_SOURCE' if historical else 'PASS', 'historical_sources': historical}, paths


class RecordedResult(unittest.TextTestResult):
    """Giữ kết quả từng ID; không chấp nhận skips/expected failures như PASS."""
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.passed_ids: list[str] = []

    def addSuccess(self, test: unittest.TestCase) -> None:
        """Ghi ID sau khi toàn bộ setup/test/cleanup đã thành công."""
        super().addSuccess(test); self.passed_ids.append(test.id())


def require_success(result: unittest.TestResult, expected: int) -> None:
    """Không đạt nếu lỗi, thiếu ca, skip hoặc expected/unexpected failure."""
    require(result.testsRun == expected and result.wasSuccessful() and not result.skipped and
            not result.expectedFailures and not result.unexpectedSuccesses, 'Hồi quy chưa PASS đủ các ca đã khóa')


def check(root: Path, output: Path) -> int:
    """Hash-only: không chạy lại tests/inference hoặc mở operational SQLite."""
    folder = root / output; manifest = read(folder / 'manifest.json')
    require(check_self_digest(manifest) == 'pretty_sorted_utf8_lf', 'T28 self-digest sai')
    count = 0
    for group, base in (('sources', root), ('outputs', folder)):
        for row in manifest[group]:
            require(file_hash(base / row['path']) == row['sha256'], 'T28 hash khác: ' + row['path']); count += 1
    require({p.name for p in folder.iterdir()} == {'manifest.json', *[r['path'] for r in manifest['outputs']]}, 'T28 file thừa/thiếu')
    return count


def build(root: Path, output: Path) -> dict:
    """Khóa nguồn trước/sau, kiểm receipts và chạy đúng các test offline đã chọn."""
    folder = output_folder(root, output)
    with offline_guard(), patch('dotenv.load_dotenv', side_effect=AssertionError('T28 không đọc .env')):
        suite = load_cases(CASES)
        before_runtime = {**runtime(), 'jsonschema': version('jsonschema')}
        original = subprocess.check_output(['git', 'show', ATTR_COMMIT + ':.gitattributes'], cwd=root)
        parents = []; names = set()
        for name in PARENTS:
            result, paths = verify_parent(root, name, original); parents.append(result); names.update(paths)
        package_folder = root / 'outputs/revision/reproducibility_v1'
        package = check_package(package_folder)
        package_manifest = read(package_folder / 'manifest.json')
        names.update((package_folder / n).relative_to(root).as_posix() for n in
                     ('manifest.json', *[r['path'] for r in package_manifest['metadata_files']], 'bundle.zip'))
        names.update({'scripts/check_revision_regression.py', 'tests/test_revision_regression.py'})
        # Các modules fixture được import thêm cũng nằm trong khóa nguồn trước khi test.
        for module in list(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_absolute() and Path(path).is_file() and Path(path).suffix == '.py' and Path(path).resolve().is_relative_to(root.resolve()):
                names.add(Path(path).resolve().relative_to(root.resolve()).as_posix())
        sources = [{'path': n, 'sha256': file_hash(root / n)} for n in sorted(names)]
        queue = root / 'outputs/revision/revision_minimal_v1'
        manifest = verify_manifest(root, queue); records = collect(root, queue, manifest)
        require(records == read(root / 'outputs/revision/revision_minimal_final_v1/records.json'), 'Final records khác')
        lineage, pairing = audit_pairing(root, manifest, records)
        final = root / 'outputs/revision/revision_minimal_final_v1'
        require(lineage == read(final / 'lineage.json') and pairing == read(final / 'pairing.json'), 'Actual raw/pairing khác T04')
        stream = io.StringIO()
        print(f'T28: kiểm receipt xong; chạy {suite.countTestCases()} ca offline đã chọn', flush=True)
        with redirect_stdout(stream), redirect_stderr(stream):
            result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordedResult).run(suite)
        expected = sum(map(len, CASES.values()))
        after_runtime = {**runtime(), 'jsonschema': version('jsonschema')}; require(after_runtime == before_runtime, 'Runtime đổi giữa chừng')
        for source in sources:
            require(file_hash(root / source['path']) == source['sha256'], 'Source/output cũ bị đổi khi kiểm T28: ' + source['path'])
        complete = (len(records) == len(manifest['jobs']) == 375)
        require(complete and all(r['prompt_chars'] < 6500 for r in lineage), 'Final jobs/prompt chưa đủ')
        passed = result.testsRun == expected and result.wasSuccessful() and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses
        report = {'status': 'PASS_SCOPED_REGRESSION' if passed else 'FAIL_SCOPED_REGRESSION',
                  'selected_tests': expected, 'tests_run': result.testsRun, 'passed_case_ids': result.passed_ids,
                  'failures': len(result.failures), 'errors': len(result.errors), 'skips': len(result.skipped),
                  'expected_failures': len(result.expectedFailures), 'parents': parents, 'package': package,
                  'runtime_before': before_runtime, 'runtime_after': after_runtime, 'platform': platform.platform(),
                  'final_jobs': len(records), 'missing_jobs': 0, 'paired_groups': len(pairing),
                  'max_actual_prompt_chars': max(r['prompt_chars'] for r in lineage),
                  'order_mismatches': sum(not p['order_matches'] for p in pairing),
                  'cross_epoch_groups': sum(p['n_execution_epochs'] > 1 for p in pairing),
                  'api_calls': 0, 'real_model_forwards': 0, 'native_rowwise_causal_gate': 'FAIL',
                  'full_compile_unit_e2e_or_global_zero_leakage_gate': 'NOT_RERUN_OR_CERTIFIED',
                  'limits': ['Mock tests kiểm hành vi code; bằng chứng LLM thật là raw T04, không phải mocks.',
                             'Tests guard phát hiện native row-wise causal FAIL không chứng nhận zero-leakage. News PIT/domain validation vẫn thiếu theo T08.',
                             'Không chạy lại toàn unit suite/E2E/compileall, bootstrap, render chart, scorer hoặc baseline trên market data; chỉ kiểm receipts và ca hợp đồng được chọn.',
                             'T16 receipt .gitattributes là source lịch sử, CLI verify T16 hiện tại sẽ từ chối hash này. T28 kiểm nguyên blob Git và đúng ba eol rules bổ sung T18; các source/runtime/license còn lại khớp.',
                             'T22 kiểm bundle/metadata; không kiểm lại weights sidecar hoặc chạy lại clean replay T23. Alias/fingerprint không là immutable hosted revision.',
                             'T28 không đóng R1–R18 hoặc đạt T30; T29 còn đối soát nhận xét, các giới hạn causal/PIT/order/epoch/quyền public/PID phải chuyển sang bài/response.']}
        lines = ['# Hồi quy theo phạm vi cuối (T28)', '',
                 f"Kết quả: **{report['status']}**, {result.testsRun}/{expected} tests, {len(result.failures)} failures, {len(result.errors)} errors, {len(result.skipped)} skips.", '',
                 'Case IDs và lý do phạm vi nằm trong cases.json; log chạy mới là tests.log. Không chạy toàn suite hoặc dùng số tests cũ làm kết quả chạy mới.', '',
                 f"Đối soát {len(parents)} receipts nguồn/đầu ra T05–T27 và bundle T22. Tái kiểm actual raw: 375 jobs/147 paired groups, prompt max={report['max_actual_prompt_chars']} <6500; 40 order mismatches/chín cross-epoch groups giữ nguyên.", '',
                 'T16: một source non-runtime .gitattributes đã thêm đúng ba eol rules T18; snapshot gốc giữ nguyên trong historical_gitattributes.bin, hash khớp receipt và Git blob. Không ghi hash gốc thành hash current; không sửa manifest cũ hoặc bypass hash cho code/runtime.', '',
                 *report['limits'], '',
                 'Kiểm hash-only: `py -3.13 -X utf8 scripts/check_revision_regression.py check`.',
                 'Muốn chạy lại dùng `build --output outputs/revision/final_regression_recheck_v1` chưa tồn tại. Không gọi API hoặc đọc .env.', '']
        outputs = {'report.json': encoded(report), 'report.md': '\n'.join(lines).encode(), 'cases.json': encoded(CASES),
                   'tests.log': stream.getvalue().replace('\r\n', '\n').encode(), 'historical_gitattributes.bin': original}
        folder.mkdir()
        for name, data in outputs.items(): (folder / name).write_bytes(data)
        receipt = {'schema_version': 'final_scoped_regression_v1', 'sources': sources,
                   'outputs': [{'path': n, 'sha256': digest(data)} for n, data in sorted(outputs.items())]}
        receipt['sha256'] = digest(encoded(receipt)); (folder / 'manifest.json').write_bytes(encoded(receipt))
        check(root, output); require_success(result, expected)
        return report


def main() -> None:
    """Build mới chạy ca offline chọn lọc; check chỉ đọc hashes đã khóa."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('build', 'check'))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.command == 'check': print(f'T28 hashes PASS: {check(ROOT, args.output)}')
    else:
        result = build(ROOT, args.output)
        print(f"T28 PASS: {result['tests_run']} tests; {result['final_jobs']} jobs; không API")


if __name__ == '__main__': main()
