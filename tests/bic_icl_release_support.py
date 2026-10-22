"""Support release tổng hợp ngoài workspace; không là receipt khoa học thật."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

from bic_icl_cohort_support import CohortFixture
from core.bic_icl_protocol import code_identity
from core.bic_icl_release import request_manifest
from core.bic_icl_runtime import context_lock, hashlib_sha
from core.historical_signals import digest
from core.research_input_lock import _write_once, runtime_identity


class ReleaseFixture:
    """Dữ liệu/SDK thật của fixture 12 điểm; thay ranh giới source production có chủ ý."""

    def __init__(self) -> None:
        self.cohort = CohortFixture()
        self.base = self.cohort.sdk.root
        self.root = self.base/'development_release_fixture'
        self.path = self.base/'releases/development_fixture.json'
        self.ledger = self.cohort.sdk.pacer.path
        self.plan = self.cohort.plan
        self.plan.update(split='development_2023', confirmation_allowed=False,
            code_sha256=code_identity(), runtime=runtime_identity(),
            inputs={'signal_config': {'models': {'agent_llm_model': 'openai/gpt-oss-20b',
                'agent_llm_temperature': 0., 'agent_llm_max_tokens': 2048}}})
        self.cohort.signature = digest(self.plan)
        self.sources = self.cohort.sources
        self.packets = [self.sources.packet(row, *self.sources.cached(row)) for row in self.plan['schedule']]
        self.lock = context_lock(self.plan, self.packets)
        self.manifest = request_manifest(self.plan, self.packets, self.lock, self.cohort.sdk.llm)
        self.gates = self.base/'gates/receipt.json'
        checks = {}
        for name in ('compileall', 'unit', 'e2e', 'leakage'):
            text = ('\n'.join("Listing '"+p+"'..." for p in ('agents', 'core', 'data_manager', 'scripts', 'tests', 'utils'))
                if name == 'compileall' else 'ALL PIPELINE CHECKS SUCCESSFUL' if name == 'e2e'
                else 'Ran 1 test in 0.001s\n\nOK\n')
            log = self.gates.parent/(name+'.log')
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(text, encoding='utf8')
            checks[name] = {'status': 'PASS', 'exit_code': 0,
                'log': {'path': log.name, 'sha256': hashlib_sha(log)}}
        _write_once(self.gates, {'gate_version': 'research_technical_gates_v1',
            'code_sha256': self.plan['code_sha256'], 'runtime': self.plan['runtime'], 'checks': checks})

    def patches(self) -> list[Any]:
        """Cô lập đường ghi và nguồn production; serializer và verifier snapshot giữ thật."""
        return [patch('core.bic_icl_protocol.NAMESPACE', self.base),
            patch('core.bic_icl_release.RELEASE_ROOT', self.path.parent),
            patch('core.bic_icl_release.LEDGER', self.ledger),
            patch('core.bic_icl_release._population', return_value=(self.packets, self.lock, self.manifest)),
            patch('core.bic_icl_release.CohortSources', return_value=self.sources)]

    def close(self) -> None:
        """Đóng handle trước dọn thư mục tạm Windows."""
        self.cohort.close()
