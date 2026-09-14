import json
import time


# ── Retry wrapper ──────────────────────────────────────────────────────────────

def _invoke_with_retry(call_fn, *args, retries=3, wait_sec=5):
    last_err = None
    for attempt in range(retries):
        try:
            return call_fn(*args)
        except Exception as e:
            last_err = e
            print(f"[DecisionAgent] Lỗi lần {attempt + 1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(wait_sec)
    raise RuntimeError(f"[DecisionAgent] Thất bại sau {retries} lần thử. Lỗi: {last_err}")


# ── Parse JSON + fallback ──────────────────────────────────────────────────────

def _safe_parse_and_enrich(raw: str, stock_name: str, lang: str = "vi") -> str:
    """
    Chuẩn hoá output thô của Decision Agent về một khối JSON hợp lệ.

    Trước đây hàm này cắt JSON bằng `raw.find("{")` → `raw.rfind("}")`. Prompt
    lại yêu cầu model viết đoạn phân tích TRƯỚC rồi mới tới khối JSON, nên chỉ
    cần một dấu ngoặc nhọn lọt vào phần văn xuôi là lát cắt hỏng và cả quyết
    định rơi về "UNKNOWN"/"N/A". Nay dùng bộ trích xuất nhiều tầng ở
    `utils.decision_parser`, có bước khôi phục bằng regex nên phán quyết đã nêu
    trong văn bản không bao giờ bị mất.
    """
    from utils.decision_parser import parse_decision

    data = parse_decision(raw, lang=lang)

    if data.get("decision_source") == "fallback_conservative":
        print(
            "[DecisionAgent] Model không trả phán quyết nhị phân → "
            f"fallback SHORT ({data.get('fallback_reason', 'UNKNOWN_REASON')})."
        )
        data["_raw_llm_response"] = (raw or "")[:500]
    else:
        print(f"[DecisionAgent] Phán quyết: {data['decision']} "
              f"(R:R={data['risk_reward_ratio']}).")

    # Bỏ các trường rỗng để UI không hiển thị ô trống, nhưng LUÔN giữ bộ khoá
    # cốt lõi mà template và backtest engine đọc tới.
    core = {"decision", "confidence", "risk_reward_ratio", "justification"}
    data = {k: v for k, v in data.items() if v or k in core}

    return json.dumps(data, ensure_ascii=False, indent=2)


# ── Distill reports to save tokens ─────────────────────────────────────────────

# Tiêu đề phần tổng hợp của Indicator Agent theo từng ngôn ngữ — dùng để cắt bớt
# báo cáo. Luôn dò CẢ hai để một hàm xử lý được output của cả hai ngôn ngữ.
_CONVERGENCE_HEADINGS = [
    "Tổng hợp hội tụ tín hiệu",
    "Signal convergence summary",
]

# Tiêu đề danh sách bài báo trong Sentiment report (phần bị loại bỏ khi rút gọn).
_ARTICLES_HEADINGS = [
    "### 15 BÀI GẦN NHẤT",
    "### 15 MOST RECENT ARTICLES",
]


def _distill_report(report_type: str, text: str, lang: str = "vi") -> str:
    """
    Rút gọn báo cáo để tiết kiệm token khi gửi cho Decision Agent.
    Giữ lại các bảng tóm tắt và kết luận, loại bỏ các chi tiết tính toán dài dòng.
    """
    if not text or text in ("Không có dữ liệu.", "No data."):
        return text

    is_en = lang == "en"

    if report_type == "alpha":
        # Giữ bảng số và consensus xác định; loại lời văn LLM trung
        # gian để Decision Agent không bị neo bởi cách diễn đạt tự tin.
        parts = text.split("---")
        if len(parts) >= 2:
            summary = next(
                (
                    line.strip()
                    for line in reversed(text.splitlines())
                    if "TỔNG HỢP:" in line or "SUMMARY:" in line
                ),
                "",
            )
            return f"{parts[0].strip()}\n\n{summary}".strip()

    if report_type == "sentiment":
        # Sentiment report có Kết quả tổng hợp -> 15 bài gần nhất -> --- -> LLM Text
        # Loại bỏ phần 15 bài gần nhất
        for heading in _ARTICLES_HEADINGS:
            if heading in text:
                header = text.split(heading)[0]
                parts = text.split("---")
                reasoning = parts[-1] if len(parts) > 1 else ""
                return f"{header.strip()}\n\n---\n\n{reasoning.strip()}"

    if report_type == "indicator":
        # Indicator report có chi tiết 5 chỉ báo -> --- -> Tổng hợp
        for heading in _CONVERGENCE_HEADINGS:
            if heading in text:
                summary_part = text.split(heading)[-1].strip()
                return f"**{heading}**\n{summary_part}"

    # Fallback: Trọng tâm là 2000 ký tự đầu nếu không parse được
    if len(text) > 3000:
        trimmed = (
            "... [Report truncated to save tokens]"
            if is_en else
            "... [Báo cáo được cắt ngắn để tiết kiệm token]"
        )
        return text[:2500] + trimmed

    return text


# ── Prompt builders ────────────────────────────────────────────────────────────

def _build_prompt_vi(stock_name, time_frame, count, has_alpha, has_sentiment,
                     h_desc, h_val, h_note,
                     trend_report, pattern_report, indicator_report,
                     alpha_report, sentiment_report) -> str:
    prompt = f"""Bạn là một Chuyên gia Giao dịch Định lượng (Senior Quant Trader) với 20 năm kinh nghiệm tại thị trường chứng khoán Việt Nam.
Mã tài sản: **{stock_name}** | Khung thời gian: **{time_frame}**.

⚠️ QUY ĐỊNH THỊ TRƯỜNG: {h_note}

HỢP ĐỒNG PHÁN QUYẾT KINH TẾ: LONG chỉ khi kỳ vọng giá Close mục tiêu cao hơn đủ so với Open vào lệnh kế tiếp để lợi nhuận ròng vẫn dương sau phí môi giới 0,25% và trượt giá 0,10% ở MỖI chiều BUY/SELL (xấp xỉ 0,70% cho một vòng giao dịch). Nếu mức tăng kỳ vọng không đủ bù phí, đi ngang hoặc giảm, phải chọn SHORT. SHORT là tín hiệu bán toàn bộ cổ phiếu đang có; nếu tài khoản chưa có cổ phiếu thì giữ CASH, tuyệt đối không mở vị thế bán khống.

MỤC TIÊU CỐT LÕI: Đánh giá sâu sắc các báo cáo từ các AI Agent độc lập để dự đoán **{h_desc}** theo hợp đồng kinh tế trên. Từ đó, đưa ra phán quyết BẮT BUỘC: bạn phải chọn dứt khoát **LONG** hoặc **SHORT** (TUYỆT ĐỐI KHÔNG được trả về NEUTRAL). Kể cả khi tín hiệu yếu hoặc có mâu thuẫn, hãy nghiêng về bên có xác suất cao hơn để buộc hệ thống phải phân loại.

Dưới đây là {count} báo cáo phân tích đã được tổng hợp:

---
### [1] PHÂN TÍCH XU HƯỚNG (Trend Agent - Quan trọng nhất về Bối cảnh & Cản)
{trend_report}

---
### [2] MÔ HÌNH NẾN (Pattern Agent - Quan trọng nhất về Thời điểm & Lực giá)
{pattern_report}

---
### [3] CHỈ BÁO KỸ THUẬT (Indicator Agent - Xác nhận Động lượng & Quá mua/bán)
{indicator_report}
"""

    next_section = 4
    if has_alpha:
        prompt += f"""
---
### [{next_section}] ALPHA FACTORS ĐỊNH LƯỢNG (Alpha Agent)
{alpha_report}
"""
        next_section += 1

    if has_sentiment:
        prompt += f"""
---
### [{next_section}] TIN TỨC & TÂM LÝ THỊ TRƯỜNG (Sentiment Analysis)
{sentiment_report}
"""

    prompt += f"""
---
## HƯỚNG DẪN TƯ DUY (Chain of Thought)
Hãy phân tích theo thứ tự bắt buộc:

## THỨ TỰ ƯU TIÊN BẰNG CHỨNG & NGUYÊN TẮC HỘI TỤ
1. **Phân định vai trò trực giao giữa các Agent:**
   - **Trend & Pattern:** Xác định bối cảnh không gian (kênh giá, hỗ trợ/kháng cự) và hình thái giá tức thời. Phân tích thị giác có độ trễ pha và dễ mắc bẫy giá giả (false breakout).
   - **Alpha Factors (Lợi thế định lượng & Vi cấu trúc):** Cung cấp bằng chứng định lượng độc lập về tương quan giá - khối lượng, độ kiệt sức dòng tiền và động lượng ngầm mà biểu đồ mắt thường không thể thấy. Alpha Agent đóng vai trò là "Bộ lọc bẫy giá" và "Công cụ nhận diện đảo chiều sớm".
   - **Indicator:** Xác nhận pha động lượng và trạng thái quá mua/quá bán chu kỳ.
   - **Sentiment:** Trọng số thấp nhất, chỉ dùng làm ngữ cảnh tham khảo bổ trợ, tuyệt đối không lấn át dữ liệu kỹ thuật và định lượng.

2. **Quyền hạn và Tác dụng cốt lõi của Alpha Agent trong việc ra quyết định:**
   - **Quyền Phủ quyết Bẫy giá (Veto False Breakouts):** Khi Trend/Pattern báo bứt phá (Breakout) nhưng Alpha Agent phát hiện phân kỳ giá - khối lượng âm hoặc kiệt sức dòng tiền (OFE/WQ2), Alpha Agent có quyền VETO tín hiệu mua đuổi để ngăn ngừa bẫy tăng giá (Bull trap) hoặc bẫy bán tháo (Bear trap).
   - **Quyền Dẫn dắt Đón đầu Đảo chiều (Leading at Exhaustion/Reversal):** Khi giá chạm vùng hỗ trợ/kháng cự then chốt, nến chưa kịp đảo chiều nhưng đa số các Alpha Mean-Reversion/Liquidity/Exhaustion hội tụ tín hiệu đảo chiều mạnh, Alpha Agent là căn cứ trọng yếu để kích hoạt vị thế đón đầu với tỷ lệ R:R tối ưu thay vì chờ đợi trễ pha.
   - **Quyền Trọng tài trong Thị trường Đi ngang (Sideways Dominance):** Khi Trend Agent xác định thị trường không có xu hướng (Sideway/Chop), tín hiệu Trend bị triệt tiêu; Alpha Agent trở thành kim chỉ nam quyết định phương hướng giao dịch.
   - **Cổng kỷ luật xu hướng (Trend & Momentum Gate):** Khi Trend và Pattern cùng xác nhận xu hướng giảm mạnh và giá đang rơi tự do giữa kênh (chưa chạm hỗ trợ hay vùng kiệt sức cung), không được chọn LONG chỉ vì Alpha có 1-2 tín hiệu riêng lẻ hoặc Sentiment tích cực. Lệnh LONG ngược xu hướng chỉ hợp lệ khi có sự hội tụ rõ ràng: giá tại hỗ trợ cứng + Alpha đảo chiều áp đảo + nến/chỉ báo xác nhận; nếu không, ưu tiên SHORT trong bài toán nhị phân.

### 1. Bối cảnh thị trường (Trend)
- Giá đang ở gần Support hay Resistance?
- Xu hướng chính: Uptrend / Downtrend / Sideway?
- Có dấu hiệu phá vỡ (breakout/breakdown) hay bị từ chối?

### 2. Hành động giá & Thời điểm (Pattern)
- Có nến đảo chiều mạnh không? (pin bar, engulfing, exhaustion)
- Lực giá hiện tại: tiếp diễn hay suy yếu?
- Đây là điểm vào lệnh tốt hay vùng rủi ro cao?

### 3. Động lượng (Indicator)
- RSI: quá mua / quá bán / phân kỳ?
- MACD: cắt lên / cắt xuống / phân kỳ?
- Momentum có ủng hộ hướng giá không?

"""

    if has_alpha:
        prompt += """
### 4. Dòng tiền định lượng (Alpha Factors)
- Phân bố các tín hiệu alpha chuẩn hóa (Z-score) đang nghiêng về TĂNG, GIẢM hay TRUNG TÍNH?
- Alpha đang xác nhận xu hướng hiện tại hay đang phát hiện phân kỳ cảnh báo đảo chiều / bẫy giá?
- Mức độ đồng thuận giữa các công thức alpha có đủ mạnh (từ 3/5 alpha trở lên) để dẫn dắt hoặc phủ quyết tín hiệu hình thái hay không?
"""
    if has_sentiment:
        prompt += """
### 5. Tâm lý thị trường (Sentiment)
- Tin tức đang nghiêng về bullish hay bearish?
- Sentiment chỉ là tín hiệu tham khảo, không lấn át dữ liệu kỹ thuật.
"""

    prompt += f"""
## ĐỊNH DẠNG ĐẦU RA BẮT BUỘC
Đầu tiên, bạn BẮT BUỘC phải viết ra một đoạn văn ngắn gọn (nhưng vô cùng logic) bằng tiếng Việt để phân tích theo Hướng dẫn Tư duy ở trên.
Ngay sau phần phân tích đó, hãy kết thúc câu trả lời của bạn bằng MỘT VÀ CHỈ MỘT khối JSON chứa quyết định cuối cùng, đúng chuẩn format sau:

```json
{{
  "decision": "<LONG hoặc SHORT>",
  "forecast_horizon": "{h_val}",
  "confidence": "<Rất cao | Cao | Trung bình | Thấp>",
  "risk_reward_ratio": <số thực, ví dụ 1.5, 2.0>,
  "evidence_for": "<3 câu tóm tắt lý do cốt lõi hỗ trợ mạnh nhất cho quyết định>",
  "evidence_against": "<Rủi ro chốt chặn lớn nhất, hoặc tín hiệu từ báo cáo nào đang đi ngược lại>",
  "justification": "<Tóm gọn mạch lạc nhất vì sao lại chốt giao dịch tại thời điểm này>"
}}
```"""
    return prompt


def _build_prompt_en(stock_name, time_frame, count, has_alpha, has_sentiment,
                     h_desc, h_val, h_note,
                     trend_report, pattern_report, indicator_report,
                     alpha_report, sentiment_report) -> str:
    prompt = f"""You are a Senior Quant Trader with 20 years of experience in the Vietnamese stock market.
Asset: **{stock_name}** | Timeframe: **{time_frame}**.

⚠️ MARKET RULE: {h_note}

ECONOMIC DECISION CONTRACT: Choose LONG only when the target Close is expected to exceed the next entry Open by enough to leave a positive net return after the 0.25% broker fee and 0.10% slippage on EACH BUY/SELL leg (approximately 0.70% round trip). SHORT sells every share currently held; when no shares are held it keeps CASH and never opens a short position.

CORE OBJECTIVE: Critically evaluate the reports produced by the independent AI agents in order to forecast **{h_desc}** under the economic contract above. You must then issue a MANDATORY verdict: choose decisively **LONG** or **SHORT** (you must NEVER return NEUTRAL). Even when the signals are weak or contradictory, lean towards the higher-probability side so the system is forced to classify.

Below are the {count} analysis reports that have been aggregated for you:

---
### [1] TREND ANALYSIS (Trend Agent - most important for context & barriers)
{trend_report}

---
### [2] CANDLESTICK PATTERNS (Pattern Agent - most important for timing & price force)
{pattern_report}

---
### [3] TECHNICAL INDICATORS (Indicator Agent - confirms momentum & overbought/oversold)
{indicator_report}
"""

    next_section = 4
    if has_alpha:
        prompt += f"""
---
### [{next_section}] QUANTITATIVE ALPHA FACTORS (Alpha Agent)
{alpha_report}
"""
        next_section += 1

    if has_sentiment:
        prompt += f"""
---
### [{next_section}] NEWS & MARKET SENTIMENT (Sentiment Analysis)
{sentiment_report}
"""

    prompt += f"""
---
## REASONING GUIDE (Chain of Thought)
Work through the analysis in this mandatory order:

## EVIDENCE PRIORITY & CONFLUENCE PRINCIPLES
1. **Orthogonal Roles of Specialized Agents:**
   - **Trend & Pattern:** Define market spatial context (channels, support/resistance) and immediate price morphology. Visual analysis inherently lags and is vulnerable to false breakouts.
   - **Alpha Factors (Quantitative Edge & Microstructure):** Provide independent quantitative evidence on price-volume divergence, flow exhaustion, and latent momentum invisible on charts. Alpha Agent acts as a "False Breakout Filter" and a "Leading Turning-Point Detector".
   - **Indicator:** Confirms momentum phases and cyclical overbought/oversold states.
   - **Sentiment:** Lowest weight; used purely as supplemental background context, never overruling technical or quantitative data.

2. **Core Decision-Making Authority & Value of Alpha Agent:**
   - **Veto on False Breakouts:** When Trend or Pattern signals a breakout, but Alpha factors detect negative price-volume divergence or flow exhaustion (e.g., OFE/WQ2), Alpha Agent has the authority to VETO chasing the breakout, protecting the system from bull traps or bear traps.
   - **Leading Turning-Point Detection at Extremes:** When price tests major support/resistance, even if candles have not yet formed a complete visual reversal, strong consensus among mean-reversion/liquidity alphas serves as primary evidence to trigger early counter-trend entry with superior Risk:Reward instead of lagging behind.
   - **Dominance in Sideways Regimes:** When Trend Agent identifies a sideways/choppy market, trend signals become noisy; Alpha Agent factors become the primary compass guiding trade direction.
   - **Trend Discipline & Conflict Gate:** When Trend and Pattern both confirm a downtrend and price is in freefall mid-channel, do not choose LONG solely because Alpha has 1-2 isolated positive signals or Sentiment is optimistic. Counter-trend LONG is valid only with decisive multi-agent confluence: price at major structural support + strong alpha consensus + confirmation from reversal patterns/indicators; otherwise choose SHORT in the binary task.

### 1. Market context (Trend)
- Is price sitting near support or resistance?
- Primary trend: uptrend / downtrend / sideways?
- Any sign of a breakout/breakdown, or a rejection?

### 2. Price action & timing (Pattern)
- Are there strong reversal candles? (pin bar, engulfing, exhaustion)
- Current price force: continuation or weakening?
- Is this a good entry point or a high-risk zone?

### 3. Momentum (Indicator)
- RSI: overbought / oversold / divergence?
- MACD: bullish cross / bearish cross / divergence?
- Does momentum support the price direction?

"""

    if has_alpha:
        prompt += """
### 4. Quantitative money flow (Alpha Factors)
- Which direction does the distribution of normalized alpha signals (Z-score) support?
- Is Alpha confirming the prevailing trend or uncovering latent divergence warning of a turning point or false breakout?
- Is the consensus among alpha factors decisive (>= 3 of 5 alphas) to guide or veto morphological signals?
"""
    if has_sentiment:
        prompt += """
### 5. Market sentiment
- Is the news flow bullish or bearish?
- Treat sentiment as supporting evidence, never as a substitute for technical data.
"""

    prompt += f"""
## MANDATORY OUTPUT FORMAT
First, you MUST write a concise (but rigorously logical) passage in English analysing the data according to the Reasoning Guide above.
Immediately after that analysis, end your answer with ONE AND ONLY ONE JSON block containing the final decision, in exactly this format:

```json
{{
  "decision": "<LONG or SHORT>",
  "forecast_horizon": "{h_val}",
  "confidence": "<Very high | High | Medium | Low>",
  "risk_reward_ratio": <a real number, e.g. 1.5, 2.0>,
  "evidence_for": "<3 sentences summarising the core reasons that most strongly support the decision>",
  "evidence_against": "<The single largest blocking risk, or which report is signalling the opposite>",
  "justification": "<The most coherent summary of why the trade is taken at this moment>"
}}
```"""
    return prompt


# ── Main agent factory ─────────────────────────────────────────────────────────

def create_final_trade_decider(llm):
    """
    Decision Agent v3 — Pure LLM reasoning.
    Đọc 3–5 báo cáo theo cấu hình ablation và tự ra quyết định.
    """

    def trade_decision_node(state) -> dict:
        # ── i18n ──────────────────────────────────────────────────────────────
        from utils.i18n import lang_of, get_horizon, language_directive, t as _t
        lang  = lang_of(state)
        is_en = lang == "en"

        no_data = _t("no_data", lang)

        indicator_raw = state.get("indicator_report", no_data)
        pattern_raw   = state.get("pattern_report",   no_data)
        trend_raw     = state.get("trend_report",     no_data)
        sentiment_raw = state.get("sentiment_report", no_data)
        alpha_raw     = state.get("alpha_report",     no_data)

        # Rút gọn báo cáo để tránh lỗi TPM Groq
        indicator_report = _distill_report("indicator", indicator_raw, lang)
        alpha_report     = _distill_report("alpha",     alpha_raw,     lang)
        sentiment_report = _distill_report("sentiment", sentiment_raw, lang)
        pattern_report   = pattern_raw  # Thường đã ngắn
        trend_report     = trend_raw    # Thường đã ngắn

        def has_report(value) -> bool:
            return bool(
                isinstance(value, str)
                and value.strip()
                and value.strip() != str(no_data).strip()
                and value not in ("Không có dữ liệu.", "No data.")
            )

        has_alpha = has_report(alpha_raw)
        has_sentiment = has_report(sentiment_raw)
        count = 3 + int(has_alpha) + int(has_sentiment)

        time_frame = state.get("time_frame", "1 day")
        stock_name = state.get("stock_name", "Unknown")

        # ── Horizon động theo quy định T+2.5 Việt Nam ──────────────────
        horizon = get_horizon(time_frame, lang)
        h_desc  = horizon["horizon_desc"]   # e.g. "xu hướng 3 phiên giao dịch tiếp theo..."
        h_val   = horizon["horizon_val"]    # e.g. "T+2.5"
        h_note  = horizon["note"]

        print(f"[DecisionAgent] Tổng hợp {count} báo cáo (condensed, horizon={h_val}, lang={lang})...")

        build = _build_prompt_en if is_en else _build_prompt_vi
        prompt = build(
            stock_name, time_frame, count, has_alpha, has_sentiment,
            h_desc, h_val, h_note,
            trend_report, pattern_report, indicator_report,
            alpha_report, sentiment_report,
        )
        prompt += f"\n\n{language_directive(lang)}"

        response = _invoke_with_retry(llm.invoke, prompt)

        # Chuẩn hoá ngay tại nguồn: mọi nơi tiêu thụ `final_trade_decision`
        # (web_interface, backtest_engine, template) đều nhận được JSON hợp lệ
        # thay vì phải tự đoán lại từ văn bản thô.
        normalized = _safe_parse_and_enrich(response.content, stock_name, lang=lang)

        return {
            "final_trade_decision": normalized,
            "messages": [response],
            "decision_prompt": prompt,
        }

    return trade_decision_node
