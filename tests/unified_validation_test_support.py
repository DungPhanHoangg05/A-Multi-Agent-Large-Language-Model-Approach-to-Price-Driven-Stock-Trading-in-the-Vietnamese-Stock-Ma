"""Fixture hồi quy U-BICL; log giả chỉ kiểm producer/consumer, không là nghiệm thu."""

from pathlib import Path
import json
import tempfile

from core.unified_bayes_cohort import CohortRun
from core.unified_bayes_validation import diagnostics
from unified_context_test_support import dense_inputs, make_context
from unified_execution_test_support import ExecutionFixture
from unified_cohort_test_support import make_cohort

MATRIX = json.loads((Path(__file__).resolve().parents[1] /
    "docs/plan/week10/fixtures/unified_bic_failure_matrix_v1.json").read_text("utf-8"))


class ValidationFixture:
    """Dùng production cohort/kernel và SDK với HTTP mock, ledger tạm riêng."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.inputs = dense_inputs()
        cls.context = make_context(cls.inputs)

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.fx = ExecutionFixture(Path(temp.name), self.context, self.inputs)
        self.addCleanup(self.fx.close)
        self.cohort = make_cohort(self.fx)
        self.plan = self.cohort.plan(self.fx.llm)

    def handle(self, *, create: bool = True) -> CohortRun:
        """Mở lại handle từ cùng nguồn, plan, ledger và journal durable."""
        return CohortRun(self.cohort, self.plan, self.fx.llm, self.fx.root / "cohort", self.fx.pacer.path, create=create)

    def diagnostic(self) -> dict:
        """Không đánh giá query hoặc dùng kết quả HTTP làm đầu vào diagnostics."""
        return diagnostics(self.cohort, self.plan, self.fx.llm, self.context.memory.payload)
