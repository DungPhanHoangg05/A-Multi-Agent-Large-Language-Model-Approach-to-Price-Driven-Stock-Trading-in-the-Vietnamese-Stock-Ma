# Response to reviewers — working draft

## Reviewer 1, comment 1 — baselines and class imbalance

**Status: partially addressed; R1 remains open. This is not a submission-ready response.**

> 1. A trivial majority-class baseline outperforms the proposed system. The label is UP only if a 3-bar Open-to-Close LONG cycle is profitable after roughly 0.7% round-trip costs (Eq. 4). Under this definition DOWN is the majority class. In the committed results, the share of DOWN labels is 55% (BHN), 80% (CMG), 65% (FPT), 65% (HVN), 70% (MBB), 65% (MWG), 75% (VCB), 75% (VJC) and 70% (VNM), i.e., 68.9% on average.A constant SHORT/CASH rule therefore achieves 68.9% mean accuracy, higher than the Full System's 65.0%. It also achieves a 0% account return, higher than the Full System's mean of -1.69%. The Full System exceeds this rule only for HVN and MWG; it ties for BHN, FPT and MBB, and is below it for CMG, VCB, VJC and VNM.Pooled over the 180 points, the Full System has a balanced accuracy of 55.0% and an MCC of 0.11. The No-Alpha control has a balanced accuracy of 44.4% and an MCC of -0.11, i.e., it is anti-predictive. The Full System issued 39 LONG calls (precision 41.0%) against 62 for No-Alpha (precision 24.2%). Most of the reported "Alpha Lift" therefore reflects the Full branch predicting LONG less often in a period when LONG was usually wrong.Please report class balance, balanced accuracy, MCC and precision/recall for both classes. Please include majority-class, always-cash, buy-and-hold and simple non-LLM baselines (e.g., momentum and logistic regression on the same features) for every symbol. The abstract, highlights and conclusions should be revised in light of these comparisons.

### Assessment

We agree that 65.0% raw accuracy and improvement over the weaker Base reports control do not establish predictive superiority. The legacy control removes both factors and sentiment, so the Full–Base gap cannot isolate alpha information value. CASH also exceeds the mean Full account return.

### Actions and evidence

1. Recomputed original-label support, confusion matrices, BA, MCC, macro-F1 and both classes' precision/recall/F1, by symbol and pooled. Full TP/FN/TN/FP is 16/40/101/23; Base reports is 15/41/77/47. Full BA is 55.01%, MCC 0.113, and UP precision/recall is 41.03%/28.57%. CASH accuracy is 68.89%. All undefined metrics are NA/null.
2. Preserved every original result byte and the original 28-file manuscript in `revision/manuscript_original.zip`. Original results and source hashes are checked by `scripts/verify_revision_r1.py`; no prediction or label was rewritten.
3. Implemented and ran train-majority, fixed momentum, price-only logistic, factor/sentiment-missingness logistic, factor-only voting and a train-rate random exposure control for all nine symbols. Preprocessing and C/threshold selection use purged chronological train/validation splits. Five whole-series-normalised factors receive documented causal adapters only in the new numerical pipeline. The legacy registry is unchanged.
4. Added daily MTM, costs, turnover, held-session and close exposure, and a continuous-hold price comparator with exactly one buy/sell per symbol. Fractional shares, reusable cash and unknown adjustment/dividend handling are explicit research limits. This is not a certified executable or total-return ledger.
5. Audited all `outputs/`, including ignored directories and the recovery ZIP. The legacy checkpoints retain decisions and cycle endpoints, but an authenticated nine-symbol OHLCV/report/Full-training archive was not recovered. New prices differ at 74 of the 180 cycles; two individual labels change although pooled UP/DOWN totals remain 56/124. We therefore do not compare new numerical results head-to-head with legacy Full, and never tune the exposure control to Full's observed test LONG rate.
6. Revised both abstracts/highlights, the introduction, target and metric definitions, methods/results, limitations and conclusion to remove significant forecasting improvement and isolated alpha/sentiment-value claims. Legacy ablation numbers are retained solely as unverified diagnostics.

Machine-readable evidence: `outputs/revision/r1_legacy/`, `outputs/revision/r1_prices_v1/`, `outputs/revision/r1_numeric_v1/` (report, models, per-cutoff predictions, per-class metrics and 81 daily ledgers), and `outputs/revision/r1_source_inventory.json`. Numerical outputs are exploratory and remain separate from legacy results.

### Manuscript locations

Both checked PDFs contain 42 physical pages. Highlights are physical page 2; the abstract is page 3; the introduction is pages 3–4. The numerical protocol is Section 5.5, physical pages 20–21. Legacy metrics/class tables are Tables 7–8, physical page 23 (printed page 21); reconstruction/comparability are Tables 10–11, physical page 25 (printed page 23). The conclusion is Section 8, physical page 28 (printed page 26). Source locators: both main TeX front matters, sections 01/03/05/06/07/08, and paper/generated/r1_*.tex. Page numbering here is explicitly physical PDF numbering, not a locator borrowed from the unavailable submitted PDF.

### Residual requirements — why R1 is not closed

The requested Full comparison on authenticated identical inputs remains incomplete. The second logistic uses the same numerical information families, with a broader factor set and missing unverifiable sentiment; it cannot be called an exact matched-input Full comparator without archived reports/features and peer context. The random control matches a training momentum rate, not Full exposure; genuine Full-exposure matching needs Full training predictions or a newly frozen common-snapshot experiment. Multi-year LLM folds/repeats and execution/corporate-action validation remain dependencies of R2/R3/R6/R9/R15. No unit test, revised limitation, or reconstructed numerical result is presented as satisfying those missing experimental requirements.
