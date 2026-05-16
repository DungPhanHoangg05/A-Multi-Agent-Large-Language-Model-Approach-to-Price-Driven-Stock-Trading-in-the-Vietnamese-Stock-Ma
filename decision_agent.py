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

def _safe_parse_and_enrich(raw: str, stock_name: str) -> str:
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start != -1 and end > start:
        try:
            data = json.loads(raw[start:end])
            
            decision = str(data.get("decision", "UNKNOWN")).upper().strip()
            try:
                rr = float(str(data.get("risk_reward_ratio", 1.5)))
                data["risk_reward_ratio"] = str(round(max(1.0, min(5.0, rr)), 1))
            except Exception:
                data["risk_reward_ratio"] = "1.5"
                
            return json.dumps(data, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
            
    print("[DecisionAgent] Không parse được JSON → fallback.")
    fallback = {
        "decision": "UNKNOWN",
        "confidence": "Thấp",
        "risk_reward_ratio": "1.0",
        "justification": f"Không trích xuất được quyết định rõ ràng cho {stock_name}.",
        "_raw_llm_response": raw[:500],
    }
    return json.dumps(fallback, ensure_ascii=False, indent=2)


# ── Distill reports to save tokens ─────────────────────────────────────────────

def _distill_report(report_type: str, text: str) -> str:
    """
    Rút gọn báo cáo để tiết kiệm token khi gửi cho Decision Agent.
    Giữ lại các bảng tóm tắt và kết luận, loại bỏ các chi tiết tính toán dài dòng.
    """
    if not text or text == "Không có dữ liệu.":
        return text
    
    if report_type == "alpha":
        # Alpha report thường có Table -> --- -> Phân tích chi tiết hoặc LLM Reasoning
        parts = text.split("---")
        if len(parts) >= 2:
            # Lấy phần đầu (Table) và phần cuối (Reasoning)
            return f"{parts[0].strip()}\n\n---\n\n{parts[-1].strip()}"
            
    if report_type == "sentiment":
        # Sentiment report có Kết quả tổng hợp -> 15 bài gần nhất -> --- -> LLM Text
        # Loại bỏ phần 15 bài gần nhất
        if "### 15 BÀI GẦN NHẤT" in text:
            header = text.split("### 15 BÀI GẦN NHẤT")[0]
            parts = text.split("---")
            reasoning = parts[-1] if len(parts) > 1 else ""
            return f"{header.strip()}\n\n---\n\n{reasoning.strip()}"
            
    if report_type == "indicator":
        # Indicator report có chi tiết 5 chỉ báo -> --- -> Tổng hợp
        if "Tổng hợp hội tụ tín hiệu" in text:
            summary_part = text.split("Tổng hợp hội tụ tín hiệu")[-1].strip()
            return f"**Tổng hợp hội tụ tín hiệu**\n{summary_part}"
            
    # Fallback: Trọng tâm là 2000 ký tự đầu nếu không parse được
    if len(text) > 3000:
        return text[:2500] + "... [Báo cáo được cắt ngắn để tiết kiệm token]"
        
    return text


# ── Main agent factory ─────────────────────────────────────────────────────────

def create_final_trade_decider(llm):
    """
    Decision Agent v3 — Pure LLM reasoning.
    Đọc 4 báo cáo và tự ra quyết định, không có điểm số hay trọng số.
    """

    def trade_decision_node(state) -> dict:
        indicator_raw = state.get("indicator_report", "Không có dữ liệu.")
        pattern_raw    = state.get("pattern_report",   "Không có dữ liệu.")
        trend_raw      = state.get("trend_report",     "Không có dữ liệu.")
        sentiment_raw  = state.get("sentiment_report", "Không có dữ liệu.")
        alpha_raw      = state.get("alpha_report", "Không có dữ liệu.")

        # Rút gọn báo cáo để tránh lỗi TPM Groq
        indicator_report = _distill_report("indicator", indicator_raw)
        alpha_report     = _distill_report("alpha",     alpha_raw)
        sentiment_report = _distill_report("sentiment", sentiment_raw)
        pattern_report   = pattern_raw # Thường đã ngắn
        trend_report     = trend_raw   # Thường đã ngắn

        has_alpha        = bool(alpha_raw and alpha_raw.strip() and alpha_raw != "Không có dữ liệu.")
        count            = 4 if has_alpha else 3
        
        time_frame       = state.get("time_frame", "1 day")
        stock_name       = state.get("stock_name", "Unknown")

        # ── Horizon động theo quy định T+2.5 Việt Nam ──────────────────
        from static_util import get_forecast_horizon
        horizon = get_forecast_horizon(time_frame)
        h_desc  = horizon["horizon_desc"]      # e.g. "xu hướng 3 phiên giao dịch tiếp theo..."
        h_val   = horizon["horizon_val"]        # e.g. "T+2.5"
        h_note  = horizon["note"]

        print(f"[DecisionAgent] Tổng hợp {count} báo cáo (condensed, horizon={h_val})...")

        prompt = f"""Bạn là một Chuyên gia Giao dịch Định lượng (Senior Quant Trader) với 20 năm kinh nghiệm tại thị trường chứng khoán Việt Nam.
Mã tài sản: **{stock_name}** | Khung thời gian: **{time_frame}**.

⚠️ QUY ĐỊNH THỊ TRƯỜNG: {h_note}

MỤC TIÊU CỐT LÕI: Đánh giá sâu sắc các báo cáo từ các AI Agent độc lập để dự đoán **{h_desc}**. Từ đó, đưa ra phán quyết BẮT BUỘC: bạn phải chọn dứt khoát **LONG** hoặc **SHORT** (TUYỆT ĐỐI KHÔNG được trả về NEUTRAL). Kể cả khi tín hiệu yếu hoặc có mâu thuẫn, hãy nghiêng về bên có xác suất cao hơn để buộc hệ thống phải giao dịch.

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

        if has_alpha:
            prompt += f"""
---
### [4] ALPHA FACTORS & DÒNG TIỀN (Alpha Agent)
{alpha_report}

### [5] TIN TỨC & TÂM LÝ THỊ TRƯỜNG (Sentiment Analysis)
{sentiment_report}
"""

        prompt += f"""
---
## HƯỚNG DẪN TƯ DUY (Chain of Thought)
Hãy phân tích theo thứ tự bắt buộc:

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

### 4. Dòng tiền & Tâm lý (Alpha + Sentiment)
- Các công thức alpha đang cho tín hiệu như nào?
- Dòng tiền lớn đang vào hay rút ra?
- Sentiment: bullish hay bearish? (chỉ để tham khảo, không quá quan trọng)
- Alpha có xác nhận hoặc phủ nhận tín hiệu kỹ thuật không?

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

        response = _invoke_with_retry(llm.invoke, prompt)

        return {
            "final_trade_decision": response.content,
            "messages": [response],
            "decision_prompt": prompt,
        }

    return trade_decision_node