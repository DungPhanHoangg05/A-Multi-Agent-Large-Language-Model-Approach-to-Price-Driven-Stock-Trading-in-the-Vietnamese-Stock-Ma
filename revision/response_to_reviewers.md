# Response to reviewer comments

Working response aligned to the final historical evaluation and the author-confirmed metadata update of 5 November 2026. Thank you for the detailed assessment. We agree that the earlier manuscript overstated performance, component attribution and several aspects of provenance. We have rewritten the scientific text and report the completed 375-job corrected-chart whitelist separately from legacy/superseded studies. The primary evidence is the 102-unit main panel; auxiliary panels and numeric controls have their own support. This is a historical exploratory evaluation after a scope amendment, not a preregistered confirmatory or prospective trial.

This response covers all eighteen comments and all 87 indexed requests. The short request descriptions below are paraphrases, not quotations. A written answer or disclosed shortfall is not acceptance or closure. Native row-wise causal construction still fails; financial-news domain/PIT validation, fixed/random factors through the hosted LLM, public rights/PID and some historical version identities remain missing. Stronger claims have been withdrawn rather than certified by implementation tests.

Locations refer to the **verified T35 PDFs** and current source anchors, with scientific companions S1-S4 identified separately. Main has 22 physical pages and submit 21, including the separate unnumbered highlights sheet. Physical page 2 is the title/abstract page; subsequent visible page numbers are one lower than physical pages. The PDFs do not print line numbers, so locators use physical pages, visible page numbers where present, sections and tables; JSON bounding boxes identify the exact rendered text rather than inventing printed line numbers. Earlier response/PDF locators and closure statements apply only to their named historical versions. The previous response is preserved byte-for-byte in [previous_response.zip](../outputs/revision/reviewer_response_v1/previous_response.zip), not silently overwritten as evidence.

The [request-level mapping](../outputs/revision/final_pdf_v1/response_map.json) records each request, actual answer, evidence hashes, source anchors and outstanding limits. [Archive instructions](archive_runbook.md) describe a private final-evidence package; it has no PID and is not authorized for public release. No API/provider/upload calls are made by this revision task.


## R1 — Baselines, class imbalance and economic interpretation


### R1.1

We replaced the 180-point legacy headline with the completed common-support historical study: 102 eligible symbol-cutoff units, 25 UP and 77 DOWN, over twelve dates and six blocks. Full and Base use identical truths and eligibility. Table 2 and companion S1 report pooled, symbol and block support; six unavailable early BHN cells remain excluded rather than becoming CASH predictions.


### R1.2

Table 2 reports BA, MCC, accuracy, LONG rate and precision/recall for both classes. Full BA is 52.96%, MCC 0.060 and accuracy 65.69%; Base BA is 49.71%, MCC -0.005 and accuracy 60.78%. Both identify seven of 25 UP outcomes; Full has 17 false LONG forecasts versus 22 for Base. Undefined metrics are NA/null, and unweighted symbol macro summaries retain their planned and defined denominators in S1.


### R1.3

Always-CASH and a majority rule fitted on purged historical training data are both included on every eligible test unit and by symbol in S1. They coincide on this test set, with 75.49% pooled accuracy, BA 50% and undefined MCC; the training rule was not fitted to the observed test majority. A correct DOWN forecast is a CASH decision and earns no short-sale return.


### R1.4

Table 3 compares the mean over 51 separately funded symbol-block accounts: Full -0.797%, Base -0.750%, CASH zero and continuous price-only hold -2.128%. Always-LONG three-bar cycles (-3.000%) are reported separately from continuous hold, which retains exposure through calendar gaps. These are account means under explicit fill/cost assumptions, not a pooled executable portfolio or total-return index.


### R1.5

Momentum-20, train-fitted logistic-price, logistic with matched numerical market inputs, and deterministic factor vote are retained alongside the constants and LLM branches. Logistic-price BA is 55.61%, above Full. Fits and preprocessing use purged chronological training data, with validation/test kept separate. Numerical inputs do not match chart/report representations or pretrained knowledge, so these comparisons do not identify a controlled information-only effect.


### R1.6

Full makes 24/102 LONG decisions and Base 29/102, while both recover the same seven UP cases. Their BA difference therefore accompanies higher DOWN recall and is compatible with a shift toward CASH. We report scheduled LONG propensity and calendar held-session fractions separately; Full-Base is not exposure matched and cannot establish why the propensity changed.


### R1.7

We withdrew profitability, broad superiority and information-specific alpha conclusions from the title, abstract, highlights, introduction and conclusion. Full loses more than Base on the main account mean and underperforms CASH economically and logistic-price on BA. The remaining contribution is an auditable historical decision-support implementation and bounded empirical comparison; favourable small-panel results do not override these main outcomes.


Evidence: [outputs/revision/final_baselines_v1/baseline_contracts.json](../outputs/revision/final_baselines_v1/baseline_contracts.json); [outputs/revision/final_baselines_v1/classification.csv](../outputs/revision/final_baselines_v1/classification.csv); [outputs/revision/final_baselines_v1/financial.csv](../outputs/revision/final_baselines_v1/financial.csv); [outputs/revision/final_baselines_v1/per_class.csv](../outputs/revision/final_baselines_v1/per_class.csv); [outputs/revision/final_baselines_v1/report.md](../outputs/revision/final_baselines_v1/report.md); [outputs/revision/final_repeats_v1/contrasts.csv](../outputs/revision/final_repeats_v1/contrasts.csv).


Current source locations (PDF positions are listed separately): [paper/sections/06_backtest_results.tex:5](../paper/sections/06_backtest_results.tex) (`Table~\ref{tab:classification}`); [paper/generated/t02_classification.tex:6](../paper/generated/t02_classification.tex) (`\label{tab:classification}`); [paper/generated/t03_accounts.tex:6](../paper/generated/t03_accounts.tex) (`\label{tab:accounts}`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R1.1**: main physical pp. 9,12,13; submit physical pp. 9,12,13.
- **R1.2**: main physical pp. 12,13; submit physical pp. 12,13.
- **R1.3**: main physical pp. 12,13; submit physical pp. 12,13.
- **R1.4**: main physical pp. 12,13; submit physical pp. 12,13.
- **R1.5**: main physical pp. 12,13; submit physical pp. 12,13.
- **R1.6**: main physical pp. 12,13; submit physical pp. 12,13.
- **R1.7**: main physical pp. 1,2,12,13,17; submit physical pp. 1,2,12,13,17.

## R2 — Historical coverage and cross-sectional dependence


### R2.1

The final study contains real archived hosted decisions at twelve selected dates across six historical blocks rather than extending the sample with synthetic predictions. Nine securities contribute 102 eligible units, with 96 units on the common-eight universe and 54 on the recent-nine universe. The calendar and all outcomes are in S4. This is sparse historical coverage, not a continuous multi-year strategy or an untouched prospective evaluation.


### R2.2

We report all observed bull/bear/sideways, volatility and turnover-proxy strata with class support, defined counts, scores and exposure. Trend is each security's Close/SMA60 context; other thresholds use purged training medians. These post-inference descriptions are not validated index regimes, an ex ante regime-aware policy or evidence of robust performance across market conditions. An all-DOWN block has undefined within-block BA.


### R2.3

Whole-block resampling retains dates, the complete eligible cross-section, variants and paired outcomes together. The two fixed-universe cohorts also have six calendar-aligned Bartlett HAC accuracy rows at lags 0/1/2; these are accuracy differences, not BA estimates. Twelve or six selected dates and irregular gaps do not support calibrated significance, coverage or an independence claim.


### R2.4

The effective number of independent market replications is not 102, nor the count after multiplying by classifiers, repeats or bootstrap draws. The primary support has twelve dates/six blocks; overlapping cohorts and correlated securities share outcomes. Purposive/surviving-universe selection, unverified listing/suspension membership and possible training contamination remain explicit limitations.


Evidence: [outputs/revision/final_temporal_v1/calendar_panel.csv](../outputs/revision/final_temporal_v1/calendar_panel.csv); [outputs/revision/final_temporal_v1/folds.csv](../outputs/revision/final_temporal_v1/folds.csv); [outputs/revision/final_temporal_v1/panel_hac.csv](../outputs/revision/final_temporal_v1/panel_hac.csv); [outputs/revision/final_temporal_v1/report.md](../outputs/revision/final_temporal_v1/report.md); [outputs/revision/final_temporal_v1/stratified_metrics.json](../outputs/revision/final_temporal_v1/stratified_metrics.json).


Current source locations (PDF positions are listed separately): [paper/sections/05_experimental_setup.tex:7](../paper/sections/05_experimental_setup.tex) (`Six blocks cover`); [paper/generated/t05_temporal.tex:6](../paper/generated/t05_temporal.tex) (`\label{tab:temporal}`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R2.1**: main physical pp. 9,15; submit physical pp. 8,9,15.
- **R2.2**: main physical pp. 9,15; submit physical pp. 8,15.
- **R2.3**: main physical pp. 9,15; submit physical pp. 8,15.
- **R2.4**: main physical pp. 9,15; submit physical pp. 8,9,15.

## R3 — Repeated executions and variability


### R3.1

The legacy default labels and matching prediction sequences cannot authenticate equal actual prompts, served weights, executed code or independent runs. We retain those artifacts for lineage audit and no longer interpret their table-to-table differences as treatment effects or stable defaults. The final response uses the completed corrected-chart release, not the superseded 474/270-job grids or earlier 18-unit repeat panel.


### R3.2

We report two separate nine-unit panels, each with two UP/seven DOWN and three real executions. One regenerates upstream inputs for B/AS; the other fixes upstream reports and repeats Decision over B/A/S/AS/P. They have different dates/symbols and prompt representations. We did not repeat every main-grid configuration or cross upstream and Decision in a full factorial variance design; that part of the request remains unfulfilled.


### R3.3

Table 4 and S2 retain all 21 variant-execution metric rows, all 48 contrast-metric rows, sample SD (ddof=1), median/range and 63 cutoff-level disagreement rows. Aggregate score equality is not equated with identical predictions. Return summaries use nine upstream or eight factorial accounts per variant/execution, not the main 51-account support; favourable executions are not selected.


### R3.4

Repeated-panel contrasts use joint block/paired-execution resampling, with undefined draws retained in the denominator report. Only 6,986/10,000 BA draws are defined; 3,014 lack class support. Three executions do not certify stable variance or calibrated inference. Across the complete pairing audit, 40/147 groups differ from listed successful-call order and nine cross epochs; quota/routing/resume did not implement complete counterbalancing, and immutable served weights remain unknown.


Evidence: [outputs/revision/final_repeats_v1/contrasts.csv](../outputs/revision/final_repeats_v1/contrasts.csv); [outputs/revision/final_repeats_v1/disagreement.csv](../outputs/revision/final_repeats_v1/disagreement.csv); [outputs/revision/final_repeats_v1/pairing.csv](../outputs/revision/final_repeats_v1/pairing.csv); [outputs/revision/final_repeats_v1/repeat_summary.csv](../outputs/revision/final_repeats_v1/repeat_summary.csv); [outputs/revision/final_repeats_v1/report.md](../outputs/revision/final_repeats_v1/report.md).


Current source locations (PDF positions are listed separately): [paper/sections/06_backtest_results.tex:19](../paper/sections/06_backtest_results.tex) (`Table~\ref{tab:repeats}`); [paper/generated/t04_repeats.tex:6](../paper/generated/t04_repeats.tex) (`\label{tab:repeats}`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R3.1**: main physical pp. 10,14; submit physical pp. 10,14.
- **R3.2**: main physical pp. 10,14; submit physical pp. 10,14.
- **R3.3**: main physical pp. 10,14; submit physical pp. 10,14.
- **R3.4**: main physical pp. 10,14; submit physical pp. 10,14.

## R4 — Bundle ablation, factorial contrasts and placebo


### R4.1

We agree that Base removes both alpha and sentiment, not alpha alone. The manuscript now defines Full as AS and Base as B and describes Full-Base as a bundle difference including report/prompt content and possible CASH propensity. The general instructions can still mention concepts whose sections have been removed; the actual prompts, not branch names alone, define delivered content.


### R4.2

The explicit factorial panel includes B, A, S, AS and P on the same nine units and three paired Decision executions. Frozen reports, five numeric factor rows, signals, skills and parent identities are checked against actual requests. This representation differs from compact main/upstream prompts, so the factorial is not pooled into the 102-unit main comparison or treated as its identical mechanism.


### R4.3

P preserves current names, headings, schema/missingness and sentiment while replacing scalar/signal/skill fields with one predetermined earlier train-only rank-vector donor; donor label exits precede validation/test. This supplies a reproducible structured replacement control, but not name-matched covariance, exposure matching or a distribution of placebo interventions. We report that limitation rather than describing it as a perfect information-only placebo.


### R4.4

Actual-content integrity establishes delivery, not that the LLM used a factor semantically or that sentiment/alpha caused the decision. In the factorial panel mean AS-B BA is -9.52 pp and AS-P -11.90 pp; all seven descriptive BA family envelopes include zero, and all factorial account means are negative. We withdrew independent-alpha, sentiment-information and semantic-reasoning benefit claims.


### R4.5

We distinguish interaction AS-A-S+B (mean +14.29 pp) from the post-hoc gap between AS mean BA and the observed best single component (zero here). A positive interaction in this small dependent panel is not validated synergy; every family envelope spans zero. The upstream AS-B mean of +4.76 pp on different support is retained separately and cannot replace the negative factorial or bounded main result.


Evidence: [outputs/revision/final_baselines_v1/baseline_contracts.json](../outputs/revision/final_baselines_v1/baseline_contracts.json); [outputs/revision/final_repeats_v1/contrasts.csv](../outputs/revision/final_repeats_v1/contrasts.csv); [outputs/revision/final_repeats_v1/donors.csv](../outputs/revision/final_repeats_v1/donors.csv); [outputs/revision/final_repeats_v1/pairing.csv](../outputs/revision/final_repeats_v1/pairing.csv); [outputs/revision/final_repeats_v1/report.md](../outputs/revision/final_repeats_v1/report.md); [outputs/revision/fusion_prompt_audit_v1/audit.json](../outputs/revision/fusion_prompt_audit_v1/audit.json).


Current source locations (PDF positions are listed separately): [paper/sections/05_experimental_setup.tex:24](../paper/sections/05_experimental_setup.tex) (`P retains`); [paper/generated/t01_scope.tex:6](../paper/generated/t01_scope.tex) (`\label{tab:scope}`); [paper/generated/t04_repeats.tex:6](../paper/generated/t04_repeats.tex) (`\label{tab:repeats}`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R4.1**: main physical pp. 10,14; submit physical pp. 9,10,14.
- **R4.2**: main physical pp. 10,14; submit physical pp. 9,10,14.
- **R4.3**: main physical pp. 10,14; submit physical pp. 9,10,14.
- **R4.4**: main physical pp. 10,14; submit physical pp. 9,10,14.
- **R4.5**: main physical pp. 10,14; submit physical pp. 9,10,14.

## R5 — Uncertainty, HAC and risk conventions


### R5.1

Primary main BA inference is a descriptive 10,000-draw paired whole-block interval: Full-Base +3.25 pp, interval [-1.18,8.13] pp. Exact discordance is a separate accuracy diagnostic (9 Full-only versus 4 Base-only correct; nominal p=0.266846), whose independence assumption is not certified. Neither procedure is presented as proof of significance or a zero effect; block/null diagnostics show that nominal coverage is not calibrated.


### R5.2

S4 includes all six actual HAC rows. Common-eight mean accuracy difference is +3.125 pp, with lag-0/1/2 SEs 0.026042/0.023146/0.020172 and p=0.255346/0.204107/0.149610. Recent-nine is +9.259 pp, SEs 0.040713/0.047112/0.045710 and p=0.072051/0.106554/0.098654. Lags count selected dates, not consecutive sessions; Bartlett estimates with a t(dates-1) reference remain small-sample sensitivity diagnostics.


### R5.3

We separate pooled confusion-cell metrics from unweighted means over symbols and from 51-account economic means. Every export retains planned/defined counts and class support; undefined BA/MCC/risk ratios remain NA/null. BHN has six eligible units rather than twelve, and overlapping 102/96/54 cohorts are not added. A table Mean is never represented as an extra pooled independent observation.


### R5.4

We removed annualized cycle Sharpe/Sortino claims for irregular, gapped schedules. Where daily-ledger ratios are supplied, Sharpe uses population daily SD, a 252-session convention and zero risk-free rate; retained Sortino uses SD of negative daily observations rather than downside RMS. Daily-close drawdown includes an initial-capital anchor. These explicit conventions do not make sparse risk estimates reliable investment-quality evidence.


### R5.5

We disclose few trades, long CASH gaps and separate account funding. Main cutoffs within blocks are 57 observed sessions apart, so comparable pending-cash/advance results are weak evidence about rapid capital reuse. Negative account means and poorly identified risk ratios cannot demonstrate deployable profitability; raw account/ledger rows and twelve sensitivities remain available privately.


Evidence: [outputs/revision/final_baselines_v1/financial.csv](../outputs/revision/final_baselines_v1/financial.csv); [outputs/revision/final_baselines_v1/report.md](../outputs/revision/final_baselines_v1/report.md); [outputs/revision/final_contracts_v1/report.md](../outputs/revision/final_contracts_v1/report.md); [outputs/revision/final_contracts_v1/risk_cycles.csv](../outputs/revision/final_contracts_v1/risk_cycles.csv); [outputs/revision/final_temporal_v1/calendar_panel.csv](../outputs/revision/final_temporal_v1/calendar_panel.csv); [outputs/revision/final_temporal_v1/panel_hac.csv](../outputs/revision/final_temporal_v1/panel_hac.csv); [outputs/revision/final_temporal_v1/report.md](../outputs/revision/final_temporal_v1/report.md).


Current source locations (PDF positions are listed separately): [paper/sections/05_experimental_setup.tex:27](../paper/sections/05_experimental_setup.tex) (`BA averages`); [paper/generated/t05_temporal.tex:6](../paper/generated/t05_temporal.tex) (`\label{tab:temporal}`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R5.1**: main physical pp. 11,15; submit physical pp. 10,15.
- **R5.2**: main physical pp. 11,15; submit physical pp. 10,13,15.
- **R5.3**: main physical pp. 11,15; submit physical pp. 10,15.
- **R5.4**: main physical pp. 11,15; submit physical pp. 10,15.
- **R5.5**: main physical pp. 11,15; submit physical pp. 10,15.

## R6 — Legacy lineage and duplicated results


### R6.1

The legacy audit compares 47 artifacts, 66 streams and 573 pairs; twenty pairs have complete duplicated sequences, including eight execution-unverified cases and twelve intended-shared-control cases with unverified parents. Byte/prediction matching and early Git matches are traceability evidence only. No authenticated original request set establishes the executed root cause, which remains unknown.


### R6.2

We cannot retrospectively certify the old Full/No-Alpha/ablation branch labels or independent execution. We have not relabelled, edited or regenerated old outcomes to match a narrative. Those legacy tables no longer support causal component attribution or robustness claims. Final comparisons instead have distinct stored request/response identities and checked parents, while retaining their own order/epoch limitations.


### R6.3

Repeated legacy return values such as -7.85/-7.38 are not treated as proof of matched controls, independent repeats or a specific caching bug. The audit records exact duplicated streams without inferring an unobserved execution. New paired/factorial results use their own frozen support and requests; neither their completion nor unit tests authenticate the historical duplicates.


Evidence: [outputs/revision/final_repeats_v1/pairing.csv](../outputs/revision/final_repeats_v1/pairing.csv); [outputs/revision/legacy_lineage_v1/comparisons.json](../outputs/revision/legacy_lineage_v1/comparisons.json); [outputs/revision/legacy_lineage_v1/report.json](../outputs/revision/legacy_lineage_v1/report.json).


Current source locations (PDF positions are listed separately): [paper/sections/07_limitations.tex:5](../paper/sections/07_limitations.tex) (`Byte-level duplication`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R6.1**: main physical pp. 16; submit physical pp. 16.
- **R6.2**: main physical pp. 16; submit physical pp. 16.
- **R6.3**: main physical pp. 16; submit physical pp. 16.

## R7 — Sentiment counts, provenance and domain validation


### R7.1

We withdraw the claim of 8,180 authenticated news articles. The retained legacy files contain 180 article records but 177 unique identities, with three excess duplicate identities; these are article records, not 180 independent prediction cutoffs or validated sentiment labels. All 180 historical scorer identities are unknown. The separate 102-unit evaluation and 154 rescored excerpts have distinct provenance scopes.


### R7.2

The inventory provides article identities/counts by symbol; the cutoff coverage export separately records eligible, missing and available-neutral states and unique article memberships. Under corrected strict scorer-provenance/availability rules none of the 180 legacy cutoffs has an accepted three-article set. This is a rule/provenance outcome, not evidence that no historical news existed; main frozen-report delivery is audited separately.


### R7.3

We separate raw records, unique identities, dated records, accepted provenance and cutoff memberships instead of reusing one percentage for incompatible denominators. Of 180 legacy date records, 155 agree with the frozen date audit and 25 do not; date parsing alone does not verify original publication. Unknown legacy scorer provenance is not reclassified as ViSoBERT or lexicon output. Repaired scoring does not overwrite the historical cache.


### R7.4

Availability requires at least three distinct accepted-provenance finite-score articles in a 90-day window; missing is not an observed neutral value. The frozen weighted score has a 30-day half-life. The normalizer receives empty article-detail/peer lists on this path, so its z-score/relative fields are zero; its >=8 reliability flag differs from >=3 report availability. We do not equate a false reliability flag with an unavailable weighted report.


### R7.5

The legacy FPT Sentiment-only result cannot authenticate a sentiment-information benefit: counts are sparse, strict provenance/availability is unresolved and branch execution is unverified. It is removed as evidence of component value. The actual S/AS factorial report presence and outcomes are described separately; delivering a sentiment section does not establish that its content is correct or causal.


### R7.6

The text cites the ViSoBERT backbone and separately identifies 5CD-AI/Vietnamese-Sentiment-visobert at revision d7738b85200272f10ba8b048d80236c8c582b581. It reports NEG/POS/NEU, P(POS)-P(NEG), a 256-token limit and the saved scoring recipe. The XLM-R-derived social-media backbone is not conflated with the downstream classifier or a model trained/validated on Vietnamese financial news.


### R7.7

No independently labelled financial-news set, agreement/adjudication study or domain test performance is available. We therefore withdraw financial-domain accuracy/reliability claims and explicitly disclose social-media domain mismatch. Offline probability/tokenizer checks on 154 saved rescores are implementation checks, not domain validation. This requested validation remains unfulfilled; it has not been replaced by labels invented by an LLM.


### R7.8

Date-only content is made available the following day by an explicit conservative rule, but neither that rule nor URL/content hashes authenticate original content or publication availability. The corpus is not claimed to be PIT certified. Independent news provenance/domain validation remains missing, so sentiment delivery, coverage and Full-Base differences cannot certify historical information effects.


Evidence: [outputs/revision/legacy_lineage_v1/report.json](../outputs/revision/legacy_lineage_v1/report.json); [outputs/revision/reference_audit_v1/reference_audit.json](../outputs/revision/reference_audit_v1/reference_audit.json); [outputs/revision/sentiment_contract_v1/scorer_tokenizer.json](../outputs/revision/sentiment_contract_v1/scorer_tokenizer.json); [outputs/revision/sentiment_contract_v1/summary.json](../outputs/revision/sentiment_contract_v1/summary.json); [outputs/revision/sentiment_coverage_v1/coverage.json](../outputs/revision/sentiment_coverage_v1/coverage.json); [outputs/revision/sentiment_coverage_v1/summary.json](../outputs/revision/sentiment_coverage_v1/summary.json); [outputs/revision/sentiment_inventory_v1/inventory.json](../outputs/revision/sentiment_inventory_v1/inventory.json); [outputs/revision/sentiment_inventory_v1/summary.json](../outputs/revision/sentiment_inventory_v1/summary.json).


Current source locations (PDF positions are listed separately): [paper/sections/03_problem_formulation.tex:37](../paper/sections/03_problem_formulation.tex) (`Legacy inventory`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R7.1**: main physical pp. 5; submit physical pp. 5.
- **R7.2**: main physical pp. 5; submit physical pp. 5.
- **R7.3**: main physical pp. 5; submit physical pp. 5.
- **R7.4**: main physical pp. 5; submit physical pp. 5.
- **R7.5**: main physical pp. 5; submit physical pp. 5.
- **R7.6**: main physical pp. 5; submit physical pp. 5.
- **R7.7**: main physical pp. 5,16; submit physical pp. 5,16.
- **R7.8**: main physical pp. 5; submit physical pp. 5.

## R8 — Attribution and the meaning of aggregation


### R8.1

The architecture and related work now attribute Indicator, Pattern, Trend and Decision roles, shared state, chart tools and trendline procedures to reused/modified QuantAgent components. The repository attribution inventory distinguishes reuse, modifications and additions. The figure follows implemented roles; it does not add a learned fusion module to make a novelty claim.


### R8.2

We restrict contributions to daily Vietnamese-equity adaptation, the implemented factor/sentiment path, protocol and auditable historical comparisons. Neither an added component nor a registered factor catalogue by itself establishes scientific novelty, improved reasoning or profitable trading. Native causal defects, domain uncertainty and negative/bounded comparisons qualify the contribution explicitly.


### R8.3

The repository includes LICENSES/QuantAgent-MIT.txt and THIRD_PARTY_NOTICES.md with upstream attribution and the scoped MIT notice. This does not license all author additions, data, news, models or hosted outputs for public redistribution. The archive rights register keeps those permissions pending rather than applying the upstream MIT licence to the whole package.


### R8.4

We acknowledge inherited high-frequency/K-line wording in actual frozen prompts despite using daily bars. The manuscript states this mismatch and retains exact original prompts in the private evidence package rather than silently editing them and attributing the old predictions to a new prompt. Application frequency is not represented as identical to the upstream HFT setting.


### R8.5

We replaced the stronger knowledge-fusion framing with prompt-level report aggregation. Distilled/capped reports and heuristic precedence instructions prefer price/chart evidence, allow factors to challenge it and give sentiment lower priority. There is no separately validated explicit knowledge representation, learned/calibrated evidence weighting or guaranteed conflict-resolution algorithm. The observed Decision prompt maximum is 4,187 characters under the 6,500 guard.


Evidence: [LICENSES/QuantAgent-MIT.txt](../LICENSES/QuantAgent-MIT.txt); [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md); [outputs/revision/fusion_prompt_audit_v1/audit.json](../outputs/revision/fusion_prompt_audit_v1/audit.json); [outputs/revision/quantagent_attribution_v1/attribution.json](../outputs/revision/quantagent_attribution_v1/attribution.json); [outputs/revision/quantagent_attribution_v1/prompt_inventory.json](../outputs/revision/quantagent_attribution_v1/prompt_inventory.json); [outputs/revision/quantagent_attribution_v1/provenance.json](../outputs/revision/quantagent_attribution_v1/provenance.json).


Current source locations (PDF positions are listed separately): [paper/sections/02_related_work.tex:5](../paper/sections/02_related_work.tex) (`QuantAgent`); [paper/sections/04_system_architecture.tex:7](../paper/sections/04_system_architecture.tex) (`QuantAgent`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R8.1**: main physical pp. 3,6; submit physical pp. 3,6.
- **R8.2**: main physical pp. 3,6; submit physical pp. 3,6.
- **R8.3**: main physical pp. 3,6; submit physical pp. 3,6.
- **R8.4**: main physical pp. 3,6; submit physical pp. 3,6.
- **R8.5**: main physical pp. 3,6; submit physical pp. 3,6.

## R9 — Reproducibility, model provenance and public archive


### R9.1

A byte-indexed private package retains reconstructed OHLCV/news inputs, saved sentiment artifacts and model/tokenizer metadata; the T34 package adds final analyses, source snapshots and S1-S4. These are reconstructed research inputs, not an authenticated submission-time snapshot. Publication/content provenance remains bounded, and missing rights prevent claiming that the exact private package is publicly available.


### R9.2

Pinned runtime/dependency manifests replace latest-based reproducibility claims. The T23 replay used Python 3.13.5 and NumPy 2.1.2 from a hashed runtime image in a fresh isolated venv without pip/network/user-site access. Installed interpreter/stdlib are shared, and the Windows pins/runtime clone are not original wheels or a portability proof for other OS/CUDA environments.


### R9.3

The private evidence preserves prompts/images, upstream reports, requests, responses/errors, parse/checkpoints and call identities. Final closure accounting has 649 attempts, 615 successes, 34 errors, 1,063,328 observed prompt tokens and 340,736 completion tokens. The 120 original Pattern calls are replayed shared dependencies, not 120 new calls; successful latency sums are not wall-clock time, and error usage/latency and monetary billing remain unknown.


### R9.4

We state exactly the archived SDK aliases openai/gpt-oss-20b (text) and qwen/qwen3.8-27b (vision), not an independently attested catalogue entry or immutable served revision. Forty response fingerprints and near-zero SDK temperature do not certify fixed weights; no hosted seed is recorded. Ninety-one original Pattern requests lack epoch/org fields. Historical provider-catalogue/weight attestation is unavailable; no new provider probe was run to fill it.


### R9.5

The final archive remains a local private draft: PID is null and public release is not authorized. Author-addition licensing, OHLCV redistribution, CafeF excerpts, model assets and hosted-output sharing terms require decisions; the QuantAgent notice alone is insufficient. We prepared offline verification/assembly instructions and an itemized rights register. We cannot provide a genuine DOI until the author has permission and publishes a suitable version; this request remains incomplete.


### R9.6

The existing no-network package-only replay reproduced 375 saved predictions, 684 T04 accounts and 37 tensors from the archived inputs, with zero unexpected external reads/network/process attempts in its isolation report. T34 verifies bytes and round-trip archive contents; it does not rerun that replay, inference, scoring or model fitting. The archive distinguishes original base evidence, the NumPy runtime image and the final response/source overlay so versions are not silently substituted.


Evidence: [outputs/revision/clean_replay_v1/metrics_qa.json](../outputs/revision/clean_replay_v1/metrics_qa.json); [outputs/revision/final_cost_integrity_v1/report.json](../outputs/revision/final_cost_integrity_v1/report.json); [outputs/revision/final_regression_v1/report.json](../outputs/revision/final_regression_v1/report.json); [outputs/revision/fusion_prompt_audit_v1/audit.json](../outputs/revision/fusion_prompt_audit_v1/audit.json); [outputs/revision/reproducibility_v1/manifest.json](../outputs/revision/reproducibility_v1/manifest.json); [outputs/revision/reproducibility_v1/rights.json](../outputs/revision/reproducibility_v1/rights.json); [outputs/revision/sentiment_inventory_v1/summary.json](../outputs/revision/sentiment_inventory_v1/summary.json).


Current source locations (PDF positions are listed separately): [paper/sections/05_experimental_setup.tex:34](../paper/sections/05_experimental_setup.tex) (`Archived SDK aliases`); [paper/sections/availability.tex:1](../paper/sections/availability.tex) (`\section`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R9.1**: main physical pp. 11,18; submit physical pp. 11,17.
- **R9.2**: main physical pp. 11,18; submit physical pp. 11,17.
- **R9.3**: main physical pp. 11,18; submit physical pp. 11,17.
- **R9.4**: main physical pp. 11,18; submit physical pp. 11,17.
- **R9.5**: main physical pp. 11,18; submit physical pp. 11,17.
- **R9.6**: main physical pp. 11,18; submit physical pp. 11,17.

## R10 — Selection diagnostics and auxiliary numeric controls


### R10.1

Native frequency diagnostics cover all 85 candidates at all 102 cutoffs: 8,670 opportunities and 510 selected slots. WQ42 appears at 52/102 cutoffs (52/510 slots). Full per-factor eligible/opportunity denominators and zero selections remain in the registry diagnostics. These dependent in-sample counts are not out-of-sample discoveries or evidence that selecting five eliminated multiplicity.


### R10.2

We report 1,282 adjacent nonzero-IC sign flips over 7,894 eligible transition pairs, alongside per-factor sign/support and basket turnover. Native orientation/ranking is fitted on the trailing diagnostic sample. Row-wise causal probes fail for delay-bfill, whole-Series normalization and the full-frame volume branch; an outer-cutoff fixture passing does not cure that failure or make sign stability causal.


### R10.3

We provide a separate train-fitted numeric fixed-custom-five control, with eligibility, imputation, scaling and orientation fitted only on purged training data. Dynamic-minus-fixed BA is +15.84 pp, nominal six-block sign-flip p=0.0625. This is not the requested fixed-factor hosted-LLM experiment and does not retrospectively repair native LLM inputs; that stronger experiment remains unperformed and the corresponding claims are withdrawn.


### R10.4

All twenty predeclared random eligible-five trials are retained, giving 23 numeric strategies and 2,346 predictions on 102 units. Dynamic-minus-random-family and dynamic-minus-no-flip BA differences are +7.33/+6.44 pp with exact six-block p=0.125/0.53125. Holm over all 23 declared hypotheses gives adjusted p=1 throughout. No seed is chosen by test outcome, and these controls do not constitute a completed Reality Check, Deflated Sharpe analysis or fixed/random LLM test.


### R10.5

The complete registry lists all 101 source WorldQuant expressions, 80 retained adaptations, five custom handlers and 21 omissions. Seventeen omissions involve industry neutralization, one market capitalization and three price/volume omissions lack an authenticated selection rationale. We retain those unknown reasons rather than presenting all omissions as necessary or mathematically justified.


### R10.6

Each retained expression is linked to the actual handler, operator calls, windows, tie/fill conventions and divergences, with separate fixtures and causal probes. The implemented time-series/proxy adaptations are not claimed equivalent to every source cross-sectional expression. Native leakage/normalization defects and custom registry-versus-prototype differences remain explicit; causal numeric adapters are a separate path, not a retroactive certificate for frozen native inputs.


Evidence: [outputs/revision/alpha_contract_v1/leakage.json](../outputs/revision/alpha_contract_v1/leakage.json); [outputs/revision/alpha_contract_v1/summary.json](../outputs/revision/alpha_contract_v1/summary.json); [outputs/revision/alpha_registry_v1/registry.json](../outputs/revision/alpha_registry_v1/registry.json); [outputs/revision/alpha_registry_v1/summary.json](../outputs/revision/alpha_registry_v1/summary.json); [outputs/revision/alpha_selection_v1/aggregate.json](../outputs/revision/alpha_selection_v1/aggregate.json); [outputs/revision/alpha_selection_v1/transitions.json](../outputs/revision/alpha_selection_v1/transitions.json); [outputs/revision/numeric_controls_v1/inference.json](../outputs/revision/numeric_controls_v1/inference.json); [outputs/revision/numeric_controls_v1/summary.json](../outputs/revision/numeric_controls_v1/summary.json); [revision/numeric_controls_protocol.json](../revision/numeric_controls_protocol.json).


Current source locations (PDF positions are listed separately): [paper/sections/03_problem_formulation.tex:23](../paper/sections/03_problem_formulation.tex) (`The native row-wise causal gate fails.`); [paper/generated/t06_numeric.tex:6](../paper/generated/t06_numeric.tex) (`\label{tab:numeric}`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R10.1**: main physical pp. 5,15,16; submit physical pp. 5,15.
- **R10.2**: main physical pp. 5,16; submit physical pp. 5,15.
- **R10.3**: main physical pp. 5,16; submit physical pp. 5,15.
- **R10.4**: main physical pp. 5,16; submit physical pp. 5,15.
- **R10.5**: main physical pp. 5,16; submit physical pp. 5,15.
- **R10.6**: main physical pp. 5,16; submit physical pp. 5,15.

## R11 — Target definition and the legacy price alias


### R11.1

The text and exported contract now use the net Open[d+1]-to-Close[d+3] candidate-LONG target with fee 0.0025 and slippage 0.001 on each leg, UP iff net return >0. The old close-to-close state-schema description is not used as the truth definition. Seven gross/net label disagreements are disclosed; saved net-elicited decisions and labels are not altered to fit the correction.


### R11.2

Canonical exports distinguish decision Close, entry Open and exit Close. The legacy actual_prev_close field has unresolved semantics and is not authenticated as decision Close because it matches entry Open. The two prices differ at 65/102 final units. We document the alias and preserve raw legacy records instead of silently renaming a historical number or recomputing its labels.


Evidence: [outputs/revision/final_contracts_v1/report.md](../outputs/revision/final_contracts_v1/report.md); [outputs/revision/final_contracts_v1/targets.json](../outputs/revision/final_contracts_v1/targets.json); [revision/target_schema.json](../revision/target_schema.json).


Current source locations (PDF positions are listed separately): [paper/sections/03_problem_formulation.tex:14](../paper/sections/03_problem_formulation.tex) (`actual\_prev\_close`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R11.1**: main physical pp. 4; submit physical pp. 4.
- **R11.2**: main physical pp. 4; submit physical pp. 4.

## R12 — Indicator identities and priority rules


### R12.1

Table A.1 gives ordered RSI rules: RSI>=70 is bearish first; RSI<=30 bullish; 55<=RSI<70 bullish; 30<RSI<=45 bearish. The interior 45<RSI<55 uses change against the third retained sample rather than being automatically neutral. Order and boundaries prevent RSI>=70 satisfying both directions. We describe the implemented rule rather than claiming RSI independently predicts profitable returns.


### R12.2

The five actual Indicator votes are MACD, RSI, Stochastic, Williams %R and ROC, described as momentum/trend indicators rather than five volatility oscillators. Their exact ordered thresholds and missing/error convention are in Table A.1 and the frozen indicator contract. The backtest node is deterministic, not an extra Indicator LLM call.


### R12.3

We distinguish declared BB/ADX state slots from numeric arrays/reports actually delivered by the Indicator node. Their presence in an old schema does not imply two additional Indicator votes or an observed volatility signal. Bollinger-derived values on the alpha path are a separate computation; missing numeric state is not invented to match a table.


### R12.4

The architecture, shared methods and Table A.1 now use one five-vote contract with the same priority boundaries. Missing/error votes remain in the denominator of five rather than renormalizing only available indicators. Consensus/report text is not represented as a full numeric state-array payload, and the old contradictory indicator table is replaced.


Evidence: [outputs/revision/final_contracts_v1/indicators.json](../outputs/revision/final_contracts_v1/indicators.json); [outputs/revision/final_contracts_v1/report.md](../outputs/revision/final_contracts_v1/report.md).


Current source locations (PDF positions are listed separately): [paper/generated/a01_rules.tex:6](../paper/generated/a01_rules.tex) (`\label{tab:indicator_rules}`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R12.1**: main physical pp. 19; submit physical pp. 18.
- **R12.2**: main physical pp. 19; submit physical pp. 18.
- **R12.3**: main physical pp. 6,19; submit physical pp. 6,18.
- **R12.4**: main physical pp. 19; submit physical pp. 18.

## R13 — Signed-volume custom factor descriptions


### R13.1

We now describe native BFE/SignedVolZAlpha4 as tanh(1.5*(%B-0.5)*VolZ5). Negative VolZ5 reverses sign and zero cancels the signal, so it cannot be described as merely confirming volume expansion. The frozen handler/output is not edited to make the previous prose correct.


### R13.2

We withdrew unsupported volume-expansion and squeeze gating descriptions and disclose signed multiplication, proxy inputs and registry/prototype preprocessing differences. The custom appendix separates handler IDs from display rank: selected slot four is not necessarily BFE. Six selected metadata slots disagree with handler descriptions; their actual prompts omit the literal wrong formula, but a semantic effect is not ruled out.


### R13.3

The scientific text now calls the five formulas custom, not proprietary, and distinguishes source adaptations from new-to-this-comparison implementation choices. No order-flow measurement, protected formula, mathematical source equivalence or investment alpha is inferred from the custom labels. Full definitions remain in Table A.2 and the registry.


Evidence: [outputs/revision/alpha_contract_v1/summary.json](../outputs/revision/alpha_contract_v1/summary.json); [outputs/revision/alpha_registry_v1/registry.json](../outputs/revision/alpha_registry_v1/registry.json); [outputs/revision/final_contracts_v1/report.md](../outputs/revision/final_contracts_v1/report.md).


Current source locations (PDF positions are listed separately): [paper/generated/a02_custom.tex:6](../paper/generated/a02_custom.tex) (`\label{tab:custom_definitions}`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R13.1**: main physical pp. 19; submit physical pp. 18.
- **R13.2**: main physical pp. 19; submit physical pp. 18.
- **R13.3**: main physical pp. 19; submit physical pp. 18.

## R14 — Chart conventions, corrected inputs and visual limits


### R14.1

We withdrew the green-bearish/red-bullish claim. Actual candle bodies are green when Close>Open and red otherwise, including doji; the price-board reference-price convention is a different comparison. Corrected Trend maps support to blue and resistance to red. The manuscript now states actual render rules rather than invoking an inaccurate national convention.


### R14.2

The final integrity audit rerendered 204 PNGs for 102 frozen windows byte/pixel exactly and checked 240 actual vision requests against cached images/templates. Geometry, body colour, support/resistance handles and legend agree. Figure 2 (source label fig:charts) uses exact PNG bytes for the earliest eligible unit (CMG, 3 July 2023), selected chronologically rather than by outcome; its caption and inputs have been checked in both rendered PDFs. Legacy wrong-legend images remain historical evidence and are not overwritten.


### R14.3

The final whitelist has real corrected-Trend and Decision calls with original Pattern raw-response replay; only its 375 complete jobs enter final results, not incomplete superseded grids. This is not a randomized old/new-image-only effect experiment. Pixel/template agreement does not validate visual comprehension, and Vietnamese xanh remains ambiguous. Counterfactual charts or human local-evidence annotations were not performed; stronger semantic claims are withdrawn.


Evidence: [outputs/revision/final_cost_integrity_v1/actual_images.csv](../outputs/revision/final_cost_integrity_v1/actual_images.csv); [outputs/revision/final_cost_integrity_v1/chart_replay.json](../outputs/revision/final_cost_integrity_v1/chart_replay.json); [outputs/revision/final_cost_integrity_v1/report.json](../outputs/revision/final_cost_integrity_v1/report.json); [outputs/revision/final_cost_integrity_v1/report.md](../outputs/revision/final_cost_integrity_v1/report.md).


Current source locations (PDF positions are listed separately): [paper/sections/04_system_architecture.tex:17](../paper/sections/04_system_architecture.tex) (`Candle bodies are green`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R14.1**: main physical pp. 7,8; submit physical pp. 6,7.
- **R14.2**: main physical pp. 7,8; submit physical pp. 6,7.
- **R14.3**: main physical pp. 7,8; submit physical pp. 6,7.

## R15 — Execution, settlement and horizon assumptions


### R15.1

The reference ledger assumes shares become sellable in the afternoon of T+2 conditional on allocation/fill, and sale proceeds remain pending until the specified settlement phase. We distinguish marked wealth, liquidated cash, pending receivables and advances/fees. The historical settlement source is cited, but an assumed phase convention is not proof that an actual opening/closing order would fill.


### R15.2

The paper reports all twelve cost, pending-cash, advance, tax/charge, no-fill/delay and lot/capacity scenarios on unchanged predictions. Daily OHLC/vendor-volume proxies do not authenticate opening auction queues, price-limit availability, partial fills or units. Ten HVN venue/calendar unit flags remain flagged; they are not silently excluded or converted to certified trades. The all-missed zero result is not a mathematical worst-return bound.


### R15.3

L=3 is a fixed observed-bar protocol choice: buy on d+1 and exit on d+3, two observed sessions after entry, with three bars including entry. We do not infer horizon optimality from settlement or claim it dominates alternatives. Costs and executable-price assumptions are stated separately from the classification target and its unchanged saved decisions.


Evidence: [outputs/revision/execution_evidence_v1/report.md](../outputs/revision/execution_evidence_v1/report.md); [outputs/revision/execution_evidence_v1/sample_audit.json](../outputs/revision/execution_evidence_v1/sample_audit.json); [outputs/revision/execution_evidence_v1/sources.json](../outputs/revision/execution_evidence_v1/sources.json); [outputs/revision/execution_final_v1/report.md](../outputs/revision/execution_final_v1/report.md); [outputs/revision/final_contracts_v1/targets.json](../outputs/revision/final_contracts_v1/targets.json).


Current source locations (PDF positions are listed separately): [paper/sections/05_experimental_setup.tex:31](../paper/sections/05_experimental_setup.tex) (`Shares are assumed`); [paper/generated/a04_execution.tex:6](../paper/generated/a04_execution.tex) (`\label{tab:execution}`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R15.1**: main physical pp. 11,21; submit physical pp. 10,20.
- **R15.2**: main physical pp. 11,21; submit physical pp. 10,20.
- **R15.3**: main physical pp. 11,21; submit physical pp. 10,20.

## R16 — Bibliographic corrections and unresolved historical numbering


### R16.1

We added an explicit Kakushadze 101 Formulaic Alphas citation at the catalogue/adaptation description. Metadata follows the audited primary publication/version; the registry documents deviations instead of implying all 101 expressions are implemented exactly. The source citation is not evidence of profitable alphas in this study.


### R16.2

We added the audited ViSoBERT paper citation and retained a separate model-card reference for the 5CD-AI classifier. The text distinguishes backbone architecture/pretraining domain from downstream labels and the unvalidated financial-news use. The classifier version/revision is not assigned retrospectively to legacy records with unknown scorer identity.


### R16.3

White (2000) is cited for data-snooping methodology, alongside a clearly prospective discussion of additional selection-aware evidence. We do not claim a completed White Reality Check or Deflated Sharpe analysis: the completed numeric family uses the explicitly described block/sign-flip/Holm diagnostics.


### R16.4

TradingAgents is attributed to the four audited authors Xiao, Sun, Luo and Wang, with the reviewed arXiv version/year distinguished from first posting. The organizational placeholder is removed. The related-work claim is limited to that system rather than establishing novelty for multi-agent trading architectures.


### R16.5

The Tsantekidis citation is described as limit-order-book forecasting rather than candlestick image recognition. The paragraph no longer treats that task as a chart-image benchmark or evidence that our Pattern Agent improves candlestick understanding.


### R16.6

Deng metadata uses the 2017 issue publication while distinguishing 2016 online-first timing. Keys, year and claim scope follow the audited version rather than silently assigning one date to both events. The current bibliography has forty entries and eighteen cited keys; current numbering is recorded from the built PDFs, while historical reviewed-version numbering remains unresolved. The corrected Deng entry is uncited in the rewritten article and therefore has no rendered reference number; its source entry is retained for audit.


### R16.7

For reviewer reference [14], its identity in the reviewed PDF has not been authenticated from the available version records. We audited all 41 original entries, removed three wrong-identity DOI entries and replaced an unverified herding entry with a separately identified source. We cannot assert which revised key equals historical [14] or invent its DOI; reviewed-version mapping remains unresolved, and current numbering is verified separately and does not authenticate the historical reference identity.


### R16.8

The historical identity of reviewer reference [21] likewise remains unresolved; current BibTeX order is not evidence of the reviewer's numbering. The complete entry-by-entry audit and applied replacement/removal actions are supplied. No unverified DOI is retained as authenticated, but we cannot claim that a specific revised entry answers historical [21] without the correct reviewed reference list.


### R16.9

The same limitation applies separately to reviewer reference [22]. We provide the audited titles, version-specific metadata and applied bibliography actions, rather than mapping [22] by current key position. The identity/DOI requested for that historical number has not been independently established and remains an explicit shortfall.


### R16.10

For reviewer reference [23], historical numbering/title identity is also unverified. All current citations have defined keys in source QA, but the separately verified current rendered numbering does not authenticate the reviewer's historical [23]. We retain this unresolved version-mapping requirement for final reference/PDF checks instead of declaring the whole comment closed.


Evidence: [outputs/revision/reference_audit_v1/changes.csv](../outputs/revision/reference_audit_v1/changes.csv); [outputs/revision/reference_audit_v1/inventory.json](../outputs/revision/reference_audit_v1/inventory.json); [outputs/revision/reference_audit_v1/reference_audit.json](../outputs/revision/reference_audit_v1/reference_audit.json); [outputs/revision/sentiment_contract_v1/scorer_tokenizer.json](../outputs/revision/sentiment_contract_v1/scorer_tokenizer.json).


Current source locations (PDF positions are listed separately): [paper/sections/02_related_work.tex:5](../paper/sections/02_related_work.tex) (`Tsantekidis`); [paper/references.bib:1](../paper/references.bib) (`@`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R16.1**: main physical pp. 3,21,22; submit physical pp. 3,20,21.
- **R16.2**: main physical pp. 3,21,22; submit physical pp. 3,20,21.
- **R16.3**: main physical pp. 3,21,22; submit physical pp. 3,20,21.
- **R16.4**: main physical pp. 3,21,22; submit physical pp. 3,20,21.
- **R16.5**: main physical pp. 3,21,22; submit physical pp. 3,20,21.
- **R16.6**: main physical pp. 3,21,22; submit physical pp. 3,20,21.
- **R16.7**: main physical pp. 3,21,22; submit physical pp. 3,20,21.
- **R16.8**: main physical pp. 3,21,22; submit physical pp. 3,20,21.
- **R16.9**: main physical pp. 3,21,22; submit physical pp. 3,20,21.
- **R16.10**: main physical pp. 3,21,22; submit physical pp. 3,20,21.

## R17 — Presentation and scope


### R17.1

Flask serialization, tokenizer/Hugging Face endpoint routing, API/retry/checkpoint instructions, full prompts and state/code listings are moved out of the scientific appendix into repository implementation notes/runbooks and the rights-qualified private package. The appendix retains four methodological/results tables; S1-S4 retain the complete scientific row sets, not an implementation-log dump.


### R17.2

We rewrote eight shared sections around one methods/results structure and a consolidated limitations discussion. Six main tables, three main figures and four appendix tables replace the old repeated float blocks; complete registry/audits remain outside the article. Both final layouts have now passed visual QA (22 physical pages main, 21 submit, including the separate highlights sheet). This does not certify journal page-limit or anonymity requirements.


### R17.3

The rewritten paragraph headings are checked for the double-period pattern, and the old heading is not retained as current prose. The current typeset headings and captions have also been checked in both final PDFs; this does not authenticate the exact historical sentence that the reviewer read.


### R17.4

The quoted sub-tasks-market wording was already absent from the recovered sources and is not attributed to a new isolated fix. The replacement prose avoids that construction and uses explicit LaTeX dash conventions where needed. We do not claim to have located/repaired the exact historical rendered sentence without the reviewed version.


### R17.5

Section structure and chart-agent prose have been rewritten, with standard LaTeX quotation pairs in current source. The exact historical Section 4.3 quotation defect is not authenticated as a current occurrence. Current opening/closing quotations and section numbering have been checked visually in both PDFs. The exact historical occurrence remains unverified; no reviewer-acceptance conclusion follows.


### R17.6

Both entrypoints now use Multi-Agent LLM Decision Support for Vietnamese Equities: A Historical Evaluation. Abstract, highlights and conclusion match that decision-support scope and the negative/bounded results; they no longer promise profitable stock trading or a novel validated fusion algorithm. This title change does not certify journal fit or a submission route.


Evidence: [outputs/revision/final_baselines_v1/financial.csv](../outputs/revision/final_baselines_v1/financial.csv); [outputs/revision/final_baselines_v1/report.md](../outputs/revision/final_baselines_v1/report.md); [outputs/revision/final_regression_v1/report.json](../outputs/revision/final_regression_v1/report.json); [outputs/revision/fusion_prompt_audit_v1/audit.json](../outputs/revision/fusion_prompt_audit_v1/audit.json); [outputs/revision/reference_audit_v1/inventory.json](../outputs/revision/reference_audit_v1/inventory.json); [outputs/revision/reproducibility_v1/manifest.json](../outputs/revision/reproducibility_v1/manifest.json).


Current source locations (PDF positions are listed separately): [paper/sections/appendices.tex:2](../paper/sections/appendices.tex) (`\appendix`); [paper/main.tex:61](../paper/main.tex) (`\title{`); [revision/implementation_notes.md:1](../revision/implementation_notes.md) (`#`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R17.1**: main physical pp. 2,5,18; submit physical pp. 2,5,17.
- **R17.2**: main physical pp. 2,5,18; submit physical pp. 2,5,17.
- **R17.3**: main physical pp. 2,5,18; submit physical pp. 2,5,17.
- **R17.4**: main physical pp. 2,5,18; submit physical pp. 2,5,17.
- **R17.5**: main physical pp. 2,5,18; submit physical pp. 2,5,17.
- **R17.6**: main physical pp. 1,2,5,17,18; submit physical pp. 1,2,5,17.

## R18 — Author metadata


### R18.1

The author confirmed the displayed order and instructed that the remaining metadata be kept. We retain Thanh-Tam Do Thi consistently in the main author line, the commented submit line and CRediT, with the current affiliation mapping. We do not invent a given/family split for a submission portal; that separate field is not supplied.


### R18.2

Under the same confirmation, Van-Tang Nguyen is retained consistently in the author line, commented submit line and CRediT, with the existing corresponding-author marker. We do not change it to the historical Tang-Van variant or infer a new identity. The corresponding email has not been supplied.


### R18.3

The author explicitly confirmed Phuong-Thai Nguyen's ORCID as 0009-0006-2033-7788. We changed exactly one commented submit ORCID to match main, preserving other names/order, affiliations, CRediT, funding and declarations. The 46-file metadata snapshot remains separate from T32; T35 adds the later layout/source and PDF version without changing those historical archives. Manuscript ID, editor decision letter and blind/nonblind route remain unavailable; no submission permission, independent ORCID ownership audit or individual signed approval record is asserted.


Evidence: [outputs/revision/author_metadata_v1/manifest.json](../outputs/revision/author_metadata_v1/manifest.json); [revision/author_metadata.md](../revision/author_metadata.md); [revision/reviewer_matrix.csv](../revision/reviewer_matrix.csv).


Current source locations (PDF positions are listed separately): [paper/main.tex:65](../paper/main.tex) (`\author[`); [paper/main_submit.tex:65](../paper/main_submit.tex) (`\author[`).


Verified PDF locations (physical pages; exact anchors/bounding boxes in the mapping):

- **R18.1**: main physical pp. 2,18; submit: author block not rendered.
- **R18.2**: main physical pp. 2,17; submit: author block not rendered.
- **R18.3**: main physical pp. 2,18; submit: author block not rendered.

## Remaining release requirements

The public-archive/PID request remains incomplete; no placeholder is presented as a DOI. Author contact and editorial route remain missing. Financial-domain labels, independently authenticated news availability, a repaired native causal LLM study, full-grid controlled repeats and the hosted fixed/random factor experiment were not supplied by this revision. Historical references [14]/[21]/[22]/[23] cannot be mapped by current BibTeX order. Claim withdrawal/disclosure limits what the revised study asserts; it does not fulfill experiments that were not done.

Both PDFs have been built and visually checked, and current reference numbering and physical-page locators are recorded. Historical reviewed-reference identities, public rights/PID and the missing scientific/editorial evidence above remain unresolved. Accordingly **zero of eighteen comments is certified closed by this response**. Scientific and editorial adequacy remain for the reviewers/editor to assess. No upload, submission or publication has been performed.
