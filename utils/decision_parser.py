"""
Bộ trích xuất quyết định giao dịch từ output thô của LLM.

Vấn đề gốc: cả ba nơi tiêu thụ `final_trade_decision` (decision_agent,
web_interface, backtest_engine) đều cắt JSON bằng `raw.find("{")` →
`raw.rfind("}")`. Cách này hỏng ngay khi model chèn suy luận có chứa dấu ngoặc
nhọn trước khối JSON, hoặc viết nhiều khối JSON: lát cắt thu được là từ dấu `{`
ĐẦU TIÊN bất kỳ (có thể nằm trong văn xuôi) tới dấu `}` CUỐI CÙNG, nên không
parse được → `decision` rơi về "N/A".

Prompt của Decision Agent yêu cầu model viết một đoạn phân tích TRƯỚC rồi mới
tới khối JSON, nên đây là đường đi thường gặp chứ không phải trường hợp hiếm.

Chiến lược ở đây đi từ chắc chắn nhất tới nới lỏng dần:
  1. Bóc <think>...</think> (suy luận thô khi `reasoning_format` không có hiệu lực).
  2. Ưu tiên khối ```json ... ``` — dạng prompt yêu cầu tường minh.
  3. Quét cân bằng ngoặc nhọn, thử parse từng ứng viên, LẤY KHỐI CUỐI hợp lệ có
     chứa khoá "decision" (model kết thúc bằng phán quyết cuối cùng).
  4. Khôi phục bằng regex: dò từ khoá LONG/SHORT/MUA/BÁN cùng R:R và lý do.
Nhờ bước 4, quyết định không bao giờ mất trắng khi trong văn bản có phán quyết.
"""

import json
import re
from typing import Any, Dict, Optional

# Khoá bắt buộc để coi một khối JSON là "khối quyết định" chứ không phải ví dụ
# hay đoạn JSON phụ mà model trích dẫn lại từ prompt.
_DECISION_KEY = "decision"

# Từ khoá phán quyết song ngữ → giá trị canonical.
_DECISION_WORDS = [
    (r"\bLONG\b", "LONG"),
    (r"\bSHORT\b", "SHORT"),
    (r"\bMUA\b", "LONG"),
    (r"\bBÁN\b", "SHORT"),
    (r"\bBAN\b", "SHORT"),
]

# Giá trị placeholder model hay chép lại nguyên văn từ prompt mẫu.
_PLACEHOLDER_RE = re.compile(r"^[\s_\-—–\.]*$|^<.*>$|^\[.*\]$|^n/?a$", re.IGNORECASE)


def strip_thinking(raw: str) -> str:
    """Bỏ <think>...</think>; thẻ lẻ thì chỉ bỏ thẻ và giữ nội dung."""
    if not raw:
        return ""
    text = re.sub(r"<think>.*?</think>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r"</?think>", " ", text, flags=re.IGNORECASE)


def _iter_balanced_json_blocks(text: str):
    """
    Sinh ra từng chuỗi con `{...}` cân bằng ngoặc nhọn ở cấp ngoài cùng.

    Bỏ qua ngoặc nằm trong chuỗi JSON và tôn trọng ký tự escape, nhờ vậy một dấu
    `}` trong `"justification": "giá vượt vùng {kháng cự}"` không cắt sớm khối.
    """
    depth = 0
    start = -1
    in_str = False
    escaped = False

    for i, ch in enumerate(text):
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    yield text[start:i + 1]
                    start = -1


def _try_load(candidate: str) -> Optional[dict]:
    """Parse một ứng viên JSON, thử lại sau khi sửa vài lỗi cú pháp thường gặp."""
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    # Sửa nhẹ: bỏ dấu phẩy thừa trước } hoặc ], đổi nháy đơn thành nháy kép ở khoá.
    repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
    repaired = re.sub(r"'([A-Za-z_][A-Za-z0-9_]*)'\s*:", r'"\1":', repaired)
    try:
        data = json.loads(repaired)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def extract_json_block(raw: str) -> Optional[dict]:
    """
    Trả về dict quyết định đầu tiên tìm được, hoặc None.

    Thứ tự ưu tiên: khối ```json fence → khối cân bằng ngoặc có khoá "decision"
    (lấy khối CUỐI, vì model kết thúc câu trả lời bằng phán quyết) → khối cân
    bằng ngoặc bất kỳ parse được.
    """
    if not raw:
        return None

    text = strip_thinking(raw)

    # (1) Khối fence ```json ... ``` — dạng prompt yêu cầu tường minh.
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    for block in reversed(fenced):
        for candidate in _iter_balanced_json_blocks(block):
            data = _try_load(candidate)
            if data and _DECISION_KEY in {k.lower() for k in data}:
                return data

    # (2) Quét toàn văn, ưu tiên khối CUỐI có khoá "decision".
    parsed_any = None
    for candidate in _iter_balanced_json_blocks(text):
        data = _try_load(candidate)
        if not data:
            continue
        if _DECISION_KEY in {k.lower() for k in data}:
            parsed_any = data          # tiếp tục quét để lấy khối cuối cùng
        elif parsed_any is None:
            parsed_any = data          # giữ tạm khối hợp lệ đầu tiên

    return parsed_any


def _clean_text_value(value: Any) -> str:
    """Bỏ placeholder (`__`, `—`, `<...>`, `N/A`) → chuỗi rỗng."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text or _PLACEHOLDER_RE.match(text):
        return ""
    return text


def normalize_decision(value: Any) -> str:
    """Chuẩn hoá giá trị `decision` về LONG / SHORT / UNKNOWN."""
    text = _clean_text_value(value).upper()
    if not text:
        return "UNKNOWN"
    for pattern, canon in _DECISION_WORDS:
        if re.search(pattern, text, re.IGNORECASE):
            return canon
    return "UNKNOWN"


def normalize_rr(value: Any, default: str = "1.5") -> str:
    """Ép R:R về số thực trong khoảng [1.0, 5.0], trả về dạng chuỗi một chữ số thập phân."""
    text = _clean_text_value(value)
    if text:
        m = re.search(r"\d+(?:[.,]\d+)?", text)
        if m:
            try:
                rr = float(m.group(0).replace(",", "."))
                return str(round(max(1.0, min(5.0, rr)), 1))
            except ValueError:
                pass
    return default


def _recover_from_text(text: str) -> Dict[str, str]:
    """
    Không có JSON hợp lệ → dò phán quyết trực tiếp trong văn xuôi.

    Ưu tiên từ khoá xuất hiện SAU CÙNG: model thường cân nhắc cả hai chiều rồi
    mới chốt, nên lần nhắc cuối là kết luận thật.
    """
    result: Dict[str, str] = {}

    best_pos, best_val = -1, ""
    for pattern, canon in _DECISION_WORDS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            if m.start() > best_pos:
                best_pos, best_val = m.start(), canon
    if best_val:
        result["decision"] = best_val

    # R:R viết dưới nhiều dạng: "risk_reward_ratio: 2.0", "R:R = 1.8", "tỷ lệ 2:1".
    rr_match = re.search(
        r"(?:risk[_\s\-]*reward[_\s\-]*ratio|R\s*[:/]\s*R|tỷ\s*lệ\s*R\s*[:/]\s*R)"
        r"\D{0,12}(\d+(?:[.,]\d+)?)",
        text, re.IGNORECASE,
    )
    if rr_match:
        result["risk_reward_ratio"] = normalize_rr(rr_match.group(1))

    conf_match = re.search(
        r"(?:confidence|độ\s*tin\s*cậy)\s*[:\-]?\s*"
        r"(Very\s*high|High|Medium|Low|Rất\s*cao|Cao|Trung\s*bình|Thấp)",
        text, re.IGNORECASE,
    )
    if conf_match:
        result["confidence"] = conf_match.group(1).strip()

    just_match = re.search(
        r"(?:justification|lý\s*do|nhận\s*định)\s*[:\-]\s*(.+)",
        text, re.IGNORECASE,
    )
    if just_match:
        justification = re.sub(r"\s+", " ", just_match.group(1)).strip()
        result["justification"] = justification[:400]
    elif best_val:
        # Không có nhãn lý do → lấy câu chứa phán quyết làm justification.
        window = text[max(0, best_pos - 300): best_pos + 300]
        window = re.sub(r"\s+", " ", window).strip()
        if window:
            result["justification"] = window[:400]

    return result


def parse_decision(raw: str, lang: str = "vi") -> Dict[str, Any]:
    """
    Trích xuất quyết định từ output thô, KHÔNG BAO GIỜ mất trắng.

    Luôn trả về dict có đủ các khoá `decision`, `confidence`,
    `risk_reward_ratio`, `justification`. `decision` chỉ là "UNKNOWN" khi trong
    văn bản thực sự không có phán quyết nào.
    """
    is_en = lang == "en"
    text  = strip_thinking(raw or "")

    data = extract_json_block(raw) or {}
    # Chuẩn hoá khoá về chữ thường để không phụ thuộc cách model viết hoa.
    data = {str(k).lower(): v for k, v in data.items()}

    decision = normalize_decision(data.get("decision"))

    # JSON thiếu/không có phán quyết → khôi phục từ văn xuôi.
    recovered: Dict[str, str] = {}
    if decision == "UNKNOWN" or not _clean_text_value(data.get("justification")):
        recovered = _recover_from_text(text)
        if decision == "UNKNOWN":
            decision = normalize_decision(recovered.get("decision"))

    confidence = (
        _clean_text_value(data.get("confidence"))
        or _clean_text_value(recovered.get("confidence"))
        or ("Low" if is_en else "Thấp")
    )

    rr_source = data.get("risk_reward_ratio")
    if not _clean_text_value(rr_source):
        rr_source = recovered.get("risk_reward_ratio")
    risk_reward_ratio = normalize_rr(rr_source)

    justification = (
        _clean_text_value(data.get("justification"))
        or _clean_text_value(recovered.get("justification"))
        or (
            "No explicit justification was provided by the model."
            if is_en else
            "Model không nêu lý do tường minh."
        )
    )

    result: Dict[str, Any] = {
        "decision":          decision,
        "confidence":        confidence,
        "risk_reward_ratio": risk_reward_ratio,
        "justification":     justification,
        "forecast_horizon":  _clean_text_value(data.get("forecast_horizon")),
        "evidence_for":      _clean_text_value(data.get("evidence_for")),
        "evidence_against":  _clean_text_value(data.get("evidence_against")),
        "alpha_consensus":   _clean_text_value(data.get("alpha_consensus")),
        "consensus_count":   _clean_text_value(data.get("consensus_count")),
        "key_risk":          _clean_text_value(data.get("key_risk")),
    }
    return result
