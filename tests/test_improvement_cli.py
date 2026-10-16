"""CLI revision kiểm offline và chặn fixture/malformed trước đọc key hoặc mạng."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from core.improvement_protocol import prepare_plan
from core.research_cohort import save_envelope
from test_candidate_cohort import CandidateSetup
from scripts.run_improvement import main


class ImprovementCliTests(CandidateSetup, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_path = self.fx.root/'improvement.json'
        self.new_plan = prepare_plan(self.plan_path, self.new_path, self.adapter)

    def test_dry_run_validates_sources_without_key_http_or_new_run(self) -> None:
        with (patch('sys.argv', ['run_improvement.py', '--dry-run', '--plan', str(self.new_path)]),
              patch('scripts.run_improvement.build_adapter', return_value=self.adapter),
              patch('scripts.run_improvement.dotenv_values', side_effect=AssertionError('Cấm đọc key')),
              patch('httpx.HTTPTransport', side_effect=AssertionError('Cấm mạng'))):
            main()
        self.assertFalse(self.output.exists())

    def test_fixture_run_and_rehashed_registry_block_before_key(self) -> None:
        with (patch('scripts.run_improvement.build_adapter', return_value=self.adapter),
              patch('scripts.run_improvement.dotenv_values', side_effect=AssertionError('Cấm đọc key')),
              patch('httpx.HTTPTransport', side_effect=AssertionError('Cấm mạng'))):
            with patch('sys.argv', ['run_improvement.py', '--run', '--plan', str(self.new_path), '--output-dir', str(self.output)]):
                with self.assertRaises(ValueError):
                    main()
            wrong = deepcopy(self.new_plan)
            wrong['registry']['profiles']['A_tp_pool']['statistics'] = 'conditional_disjoint_beta_v1'
            save_envelope(self.new_path, wrong)
            with patch('sys.argv', ['run_improvement.py', '--dry-run', '--plan', str(self.new_path)]):
                with self.assertRaises(ValueError):
                    main()

    def test_rehashed_development_parent_cannot_replace_locked_source_plan(self) -> None:
        forged = deepcopy(self.plan)
        forged['split'] = 'development_2023'
        forged['inputs']['signal_config']['models']['agent_llm_temperature'] = .5
        target = self.fx.root/'forged_parent.json'
        save_envelope(target, forged)
        with self.assertRaisesRegex(ValueError, 'Parent development W7'):
            prepare_plan(target, self.fx.root/'forged_improvement.json', self.adapter)
