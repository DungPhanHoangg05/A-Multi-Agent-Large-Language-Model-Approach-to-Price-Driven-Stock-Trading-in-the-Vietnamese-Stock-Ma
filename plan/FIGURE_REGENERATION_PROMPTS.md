# Prompts for Regenerating the ESWA System Figures

These prompts are grounded in the current implementation and manuscript as of 2026-09-20. Use each prompt with the corresponding existing PNG attached as **Image 1: layout/style reference only**. The old image is not a factual reference: redraw it from scratch and obey the prompt whenever the old labels conflict with it.

Recommended output for all four figures: high-quality 16:9 or wide-landscape PNG, 3840 × 2160 where supported, white background, crisp vector-like lines, readable at journal-page scale, and no watermark. Render every quoted label verbatim and do not invent extra modules, metrics, claims, or numbers.

## 1. `system_pipeline.png`

```text
Use case: scientific-educational infographic for an Expert Systems with Applications graphical abstract.
Input images: Image 1 is the old system_pipeline.png, used only as a layout and colour-family reference. Redraw the figure from scratch; do not copy its outdated facts.

Primary request: Create a precise wide workflow diagram of the implemented five-agent Vietnamese-equity system and its paired backtest path.

Style/medium: clean flat vector-like academic infographic; white background; dark charcoal text; thin orthogonal arrows; rounded rectangles; generous whitespace; consistent sans-serif typography. Use blue for text/quantitative agents, green for vision agents, purple dashed outlines for ablation/optional branches, and orange for decisions and account outputs.

Composition/framing: left-to-right landscape flow with four clearly separated stages.

Stage 1 — point-in-time inputs:
- Box: "Point-in-Time Inputs"
- Inside it, three lines: "OHLCV window [e-W, e)", "History snapshot ending at d = e-1 (up to 600 bars)", and "Historical sentiment: available_at <= cutoff"
- Feed these inputs into a long box labelled "Shared Typed State".

Stage 2 — shared upstream evidence, executed once per test point:
- Header: "Shared Upstream Graph (run once)"
- Sequential boxes with arrows:
  1. "Indicator Agent" / "deterministic TA signals + text report"
  2. "Pattern Agent" / "candlestick VLM + rule-based consistency gate"
  3. "Trend Agent" / "trendline VLM + rule-based consistency gate"
- Below Pattern and Trend, one shared support box: "Chart Renderers (candlestick + trendline PNG)".
- After Trend Agent, show a box labelled "Deep-copied shared reports".

Stage 3 — paired decision branches:
- Top branch, solid blue/orange: header "Full". Flow: "Alpha Agent" / "85 candidates -> Top 5" and "Point-in-time sentiment context" -> "Decision Agent".
- Bottom branch, purple dashed: header "Baseline (No Alpha, No Sentiment)". The same deep-copied Indicator, Pattern, and Trend reports go directly to a separate "Decision Agent" box.
- Add a small side note: "Four-way ablation also supports Alpha-only and Sentiment-only".
- Make it visually unambiguous that upstream reports are held fixed between the paired branches.

Stage 4 — outputs and evaluation:
- From each Decision Agent, output a compact JSON card with the exact field names: "decision", "forecast_horizon", "confidence", "risk_reward_ratio", "evidence_for", "evidence_against", "justification".
- The decision value must be shown as "LONG | SHORT", never BUY, SELL, or NEUTRAL.
- Both JSON cards feed two final boxes:
  1. "Directional Evaluation" / "LONG vs UP; SHORT vs DOWN"
  2. "Long-Only Account Ledger" / "LONG: BUY next Open -> SELL target Close" / "SHORT: CASH (no short sale)" / "0.25% fee + 0.10% slippage on each leg"

Legend text (verbatim): "text/quantitative", "vision-language", "ablation/optional", "decision/output".

Constraints:
- Show exactly five named agents: Indicator Agent, Alpha Agent, Pattern Agent, Trend Agent, Decision Agent.
- Sentiment is context loaded within the Alpha/Sentiment decision branch, not a sixth graph agent.
- Use "85 candidates" only: 5 proprietary + 80 WorldQuant adaptations.
- Preserve the exact cutoff notation [e-W, e) and d = e-1.
- Do not claim that rule-based gates prove visual evidence faithfulness.
- Do not show 87 candidates, 82 WQ candidates, BUY as the classifier output, an always-invested SHORT position, or a separate short-selling P&L.
- No logos, decorative stock photos, 3D effects, gradients that reduce legibility, or watermark.
```

## 2. `alpha_agent_pipeline.png`

```text
Use case: detailed scientific workflow figure for the Alpha Agent section of an academic paper.
Input images: Image 1 is the old alpha_agent_pipeline.png, used only for its two-column visual rhythm. Redraw all content from the specification below and discard outdated counts, weights, and coupling.

Primary request: Show two strictly separated evidence lanes—OHLCV alpha selection on the left and point-in-time sentiment context on the right—that produce separate reports for the Decision Agent.

Style/medium: clean vector-like academic infographic on white; blue alpha lane, green sentiment lane, orange output lane; rounded boxes, crisp arrows, compact mathematical notation, consistent sans-serif font.

Composition/framing: wide landscape with two major columns that never merge before the final report layer.

Left column header: "OHLCV Alpha Selection"
Flow from top to bottom:
1. Box: "Point-in-Time History" with the exact sublabels "up to 600 bars" and "ends at decision cutoff d = e-1".
2. Box: "Executable Registry: 85 Candidates" containing two child boxes: "5 Proprietary" and "80 WorldQuant Adaptations".
3. Box: "Feature Construction" with "returns, log-volume, VWAP proxy, ADV20" and a small note "range proxy if volume is sparse".
4. Box: "Matured Net Labels Only" with "entry Open O_e -> target Close C_(e-1+L)" and "exclude final L rows".
5. Box: "Eligibility Gate" with "at least 20 finite observations" and "finite IC, Accuracy, Sharpe".
6. Three metric boxes feeding one score box: "|Spearman IC| × 0.40", "Directional Accuracy × 0.35", and "Horizon Sharpe × 0.25".
7. Score box with the exact formula: "S = 0.40 N_V(|IC|) + 0.35 N_V(Acc) + 0.25 N_V(Sharpe)" and sublabel "min-max over eligible set V".
8. Box: "Rank and Select Top 5".
9. Box: "Orient by Historical IC Sign" with the caution icon and note "cutoff-safe, but selection bias remains".
10. Box: "Current Normalised Signals" with "default: zscore_tanh".
11. Output box: "Deterministic Alpha Table + Consensus" and small note "optional LLM interpretation in live mode; omitted in benchmark mode".

Right column header: "Point-in-Time Sentiment Context"
Split the input into two mutually exclusive modes:
- Solid live path: "Live mode: CafeF crawler".
- Purple dashed backtest path: "Backtest mode: historical sentiment store" with "keyed by symbol and cutoff".
Both paths feed a strict filter box labelled "available_at <= cutoff" with the notes "90-day window", "undated records rejected", and "date-only records available next day at 00:00 Asia/Ho_Chi_Minh".
Then flow through:
1. "Scoring with stored provenance" / "ViSoBERT endpoint or versioned lexicon fallback".
2. "Time-Decayed Target Sentiment S_decay" / "30-day half-life".
3. "Relative Sentiment Rel_sent" / "target minus eligible related-company mean".
4. Output box: "Separate Sentiment Report".

At the bottom, route "Deterministic Alpha Table + Consensus" and "Separate Sentiment Report" as two distinct arrows into a wide box labelled "Compressed Inputs to Decision Agent". Add the exact note: "Sentiment is not injected into any alpha formula or factor ranking."

Constraints:
- Use exactly 85 = 5 + 80, never 87 = 5 + 82.
- Long-only win rate may appear only as "diagnostic only" if shown at all; it must not be a scoring term.
- Do not use the outdated weights 0.35/0.30/0.20/0.15.
- Do not show sentiment entering alpha formulas, normalisation, IC, ranking, or Top-5 selection.
- Do not imply that negative-IC orientation removes overfitting risk.
- Do not claim all 101 WorldQuant expressions are implemented.
- No extra modules, logos, tiny unreadable footnotes, or watermark.
```

## 3. `decision_agent_pipeline.png`

```text
Use case: scientific workflow diagram of the implemented Decision Agent for an academic paper.
Input images: Image 1 is the old decision_agent_pipeline.png, used only as a broad composition reference. Replace "CHAIN OF THOUGHT" with observable evidence synthesis; do not depict hidden reasoning tokens.

Primary request: Create a precise left-to-right diagram showing report distillation, evidence synthesis, schema-constrained binary classification, and the separate long-only execution mapping.

Style/medium: clean vector-like academic infographic; white background; blue quantitative elements, green vision elements, purple sentiment, orange/red risk and output elements; crisp arrows; rounded boxes; readable sans-serif typography.

Composition/framing: four stages from left to right.

Stage 1 header: "Upstream Reports"
Show five report cards:
- "Indicator Report" / "consensus summary"
- "Pattern Report" / "patterns, candles, key levels"
- "Trend Report" / "direction, regime, support/resistance"
- "Alpha Report" / "Top-5 table + deterministic consensus"
- "Sentiment Report" / "time-decayed and relative context"
Use dashed outlines on Alpha and Sentiment cards and label them "enabled by variant". Add the note "Indicator, Pattern, and Trend are shared across paired variants".

Stage 2 header: "Deterministic Prompt Distillation"
Show one funnel with the exact per-report character caps:
- "Trend: 900"
- "Pattern: 900"
- "Indicator: 900"
- "Alpha: 1,200"
- "Sentiment: 600"
Below the funnel write "maximum report payload: 4,500 characters" and "benchmark prompt cap: 7,500 characters".

Stage 3 header: "Decision Agent — Evidence Synthesis"
Show four numbered evidence gates:
1. "Trend & Key Levels"
2. "Candles & Entry Risk"
3. "Momentum Confirmation"
4. "Alpha & Sentiment Alignment (when enabled)"
Below them add a prominent contract box with these exact lines:
"Binary forecast: LONG or SHORT"
"LONG only if the net Open-to-Close cycle is expected to remain profitable after costs"
"SHORT means bearish classification and maps to CASH; it is not a short sale"

Stage 4 header: "Structured Output and Downstream Action"
First show a JSON card with these field names exactly once:
{
  "decision": "LONG | SHORT",
  "forecast_horizon": "L = 3 daily bars",
  "confidence": "Very high | High | Medium | Low",
  "risk_reward_ratio": "1.0 to 5.0",
  "evidence_for": "...",
  "evidence_against": "...",
  "justification": "..."
}
Add a small validation box: "Structured schema; up to 2 format attempts; invalid output aborts the test point—no silent fallback decision".

From the JSON card split into two action boxes:
- Blue/orange box: "LONG -> invest all cash at next Open -> sell all shares at target Close -> charge 0.25% fee + 0.10% slippage on each leg"
- Grey/purple box: "SHORT -> hold CASH for the full horizon -> zero account return -> no short selling and no fee"

Constraints:
- Never call the middle stage "chain of thought" and do not show private hidden reasoning.
- The classifier output is only LONG or SHORT, never BUY, SELL, or NEUTRAL.
- Do not state that a SHORT forecast maintains a market position; it holds cash in the account simulation.
- Do not show T+1 or intraday as evaluated settings; the reported study uses daily L = 3.
- Alpha and sentiment must be visibly optional by ablation variant.
- No logos, model-generated prose outside the specified labels, 3D effects, or watermark.
```

## 4. `walkforward_protocol.png`

```text
Use case: mathematically precise timeline infographic for the walk-forward evaluation protocol in a finance/AI journal paper.
Input images: Image 1 is the old walkforward_protocol.png, used only as a loose style reference. Rebuild the indexing from scratch because the old t-based labels are inconsistent with the implementation.

Primary request: Draw a wide OHLCV candlestick timeline that explains the exclusive window boundary, decision cutoff, entry, target, step size, paired evaluation, and fixed-cycle account update.

Style/medium: clean vector-like scientific diagram; white background; black timeline; restrained blue, green, and purple analysis-window fills; amber target horizons; sharp sans-serif labels; exact mathematical notation; no decorative imagery.

Composition/framing:
- Horizontal axis labelled "Bar position (older -> newer)".
- Vertical label at the left: "OHLCV candles".
- Show three consecutive test points with exclusive boundaries e_i, e_(i+1) = e_i + S, and e_(i+2) = e_i + 2S.

For the first test point, render these labels verbatim and align them to the correct candles:
- Analysis window: "X_e = X_[e-W, e)"
- First visible index: "e-W"
- Final visible / decision bar: "d = e-1"
- Exclusive boundary and entry bar: "e"
- Target bar: "h = e-1+L"
- Execution arrow: "BUY at Open O_e -> SELL at Close C_h"
- Label arrow: "y_(e,L) = UP iff net return > 0; otherwise DOWN"

Repeat the same geometry for the next two windows, shifted exactly S bars to the right. Place a brace between successive exclusive boundaries labelled "Step size S = 3 bars".

Above or below the timeline, add a compact process strip for every test point:
1. "Cut point-in-time window [e-W, e)"
2. "Select Top-5 from 85 candidates using history ending at d = e-1"
3. "Run shared Indicator -> Pattern -> Trend once"
4. "Deep-copy reports to Full and Baseline"
5. "Obtain paired LONG/SHORT predictions"
6. "Score direction and update separate compounded ledgers"

Add a compact parameter table in the lower-right corner with these exact rows:
- "W = 45 — analysis-window bars"
- "S = 3 — bars between test points"
- "L = 3 — daily forecast/holding horizon"
- "N_test = 20 — points per symbol"
- "History <= 600 — alpha-selection bars through d"

Add a compact financial-contract box:
- "Net LONG return: Open O_e to Close C_(e-1+L)"
- "Fee 0.25% + slippage 0.10% on each BUY/SELL leg"
- "LONG compounds wealth; SHORT holds CASH"
- "No position carries across test points"

Constraints:
- The analysis window is [e-W, e), not [e-W+1, e] and not a window that includes e.
- The final visible candle is e-1; entry is e; target is e-1+L. For L = 3, target is e+2.
- Never compute the label from Close_(e-1) to Close_(e+L-1); it is a net Open_e-to-Close_(e-1+L) return.
- Do not use the old variable t as both a visible candle and an exclusive boundary.
- Do not state that L = 1 intraday is part of the reported experiment.
- Show paired shared reports and separate Full/Baseline ledgers; do not imply separately sampled upstream agents.
- No logos, extra statistics, tiny text, or watermark.
```

## Mandatory visual QA after generation

Check every generated figure at full resolution and at the final LaTeX scale. Reject and regenerate if any of the following appears:

- `87 candidates`, `82 WQ`, or scoring weights other than `0.40 / 0.35 / 0.25`.
- `BUY`/`SELL`/`NEUTRAL` used as the Decision Agent classifier output.
- SHORT depicted as an executed short sale or as an always-invested account position.
- Sentiment connected into alpha formula computation or factor ranking.
- A walk-forward window that includes entry bar `e`, or a target other than `e-1+L`.
- Separate stochastic upstream reports for Full and Baseline.
- Misspelled labels, extra arrows, invented metrics, illegible formulas, clipped content, watermark, or decorative elements that weaken scientific readability.

## Backtest image provenance used by `ESWA/figs/`

| Ticker | Source artifact copied without modification |
|---|---|
| BHN | `backtest_result/backtest_BHN_20260917_1227.png` |
| CMG | `backtest_result/backtest_CMG_20260916_1110.png` |
| FPT | `backtest_result/backtest_FPT_20260915_1458.png` |
| HVN | `backtest_result/backtest_HVN_20260916_1032.png` |
| MBB | `backtest_result/backtest_MBB_20260916_1129.png` |
| MWG | `backtest_result/backtest_MWG_20260916_1422.png` |
| VCB | `backtest_result/backtest_VCB_20260916_1337.png` |
| VJC | `backtest_result/backtest_VJC_20260915_1542.png` |
| VNM | `backtest_result/backtest_VNM_20260915_1514.png` |
