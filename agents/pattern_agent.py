from agents import indicator_agent
import time
import json
import re

from utils import static_util
from langchain_core.messages import HumanMessage, SystemMessage

# ── Các trường bắt buộc trong báo cáo mô hình (thứ tự cố định) ────────────
_PATTERN_FIELDS = [
    "Mô hình",
    "Độ tin cậy",
    "Thiên lệch dự báo",
    "Bằng chứng",
    "Nến quan trọng",
    "Hàm ý giao dịch",
]

# ── Regex nhận diện từng nhãn (linh hoạt dấu *, khoảng trắng, số thứ tự) ──
_LABEL_REGEXES = {
    "Mô hình":          r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:\*{0,2})Mô\s*hình(?:\*{0,2})\s*:",
    "Độ tin cậy":       r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:\*{0,2})Độ\s*tin\s*cậy(?:\*{0,2})\s*:",
    "Thiên lệch dự báo": r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:\*{0,2})Thiên\s*lệch(?:\s*dự\s*báo)?(?:\*{0,2})\s*:",
    "Bằng chứng":      r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:\*{0,2})Bằng\s*chứng(?:\*{0,2})\s*:",
    "Nến quan trọng":   r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:\*{0,2})Nến\s*quan\s*trọng(?:\*{0,2})\s*:",
    "Hàm ý giao dịch":  r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:\*{0,2})Hàm\s*ý(?:\s*giao\s*dịch)?(?:\*{0,2})\s*:",
}

# ── Các marker đánh dấu nội dung "suy luận nội bộ" cần loại bỏ ────────────
_GARBAGE_PATTERNS = [
    # Tiếng Anh
    r"Alternative\s*:", r"Note\s*:", r"Wait\s*,", r"However\s*,",
    r"Self[- ]?Correction\s*:", r"Refinement\s*:", r"Final\s*Check\s*:",
    r"One\s+more\s+look", r"Let\s+me\s+reconsider",
    # Tiếng Việt
    r"Lưu\s*ý\s*:", r"Hoặc\s*:", r"Tuy\s*nhiên\s*,", r"Nhìn\s*kỹ\s*lại",
    r"Nhưng\s+", r"Vậy\s+", r"Quyết\s*định\s*:", r"Kiểm\s*tra\s*lại",
    # Đánh dấu số thứ tự lặp (LLM lải nhải lặp trường)
    r"\d+\.\s*\*{0,2}(?:Mô hình|Độ tin cậy|Thiên lệch|Bằng chứng|Nến quan trọng|Hàm ý)",
]
_GARBAGE_RE = re.compile("|".join(f"(?:{p})" for p in _GARBAGE_PATTERNS), re.IGNORECASE)


def _strip_thinking_blocks(text: str) -> str:
    """Xoá toàn bộ nội dung trong <think>...</think> và ```markdown``` wrappers."""
    # Xoá <think> blocks (Qwen3 reasoning)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Xoá markdown/json code fences
    text = text.replace("```markdown", "").replace("```json", "").replace("```", "")
    return text.strip()


def _extract_field_value(text: str, start: int, end: int) -> str:
    """
    Trích xuất và làm sạch giá trị của một trường từ vị trí start đến end.
    Cắt bỏ mọi nội dung lải nhải, suy luận, tiếng Anh trong ngoặc.
    """
    raw = text[start:end].strip()

    # Xoá ký tự thừa ở đầu (dấu *, -, :, khoảng trắng)
    raw = re.sub(r'^[\s\*:\-]+', '', raw)

    # Cắt đứt tại vị trí xuất hiện garbage đầu tiên
    m = _GARBAGE_RE.search(raw)
    if m:
        raw = raw[:m.start()]

    # Xoá giải thích tiếng Anh thuần trong ngoặc, vd: "(Head and Shoulders)"
    # Giữ nguyên ngoặc chứa số hoặc tiếng Việt, vd: "(70)", "(04/06)"
    raw = re.sub(r'\s*\([A-Za-z]{3,}[A-Za-z\s\-&]*\)', '', raw)

    # Xoá các dấu * thừa bên trong
    raw = re.sub(r'\*{2,}', '', raw)

    # Xoá các giải thích phụ thường xuất hiện trong output lải nhải
    # "Lý do: ...", "Vì ...", "Đây là ...", "Đánh giá ..."
    raw = re.sub(r'\.\s*\*?\s*Lý\s+do\s*:.*', '.', raw, flags=re.DOTALL)
    raw = re.sub(r'\.\s+Vì\s+.*', '.', raw, flags=re.DOTALL)
    raw = re.sub(r'\.\s+Đây\s+là\s+.*', '.', raw, flags=re.DOTALL)
    raw = re.sub(r'\.\s+Đánh\s+giá\b.*', '.', raw, flags=re.DOTALL)

    # Xoá số thứ tự rời rạc cuối dòng (vd: "... 3." hoặc "... 8.")
    raw = re.sub(r'\s+\d+\.\s*$', '', raw)

    # Xoá các bullet "* " lẫn trong text thành dấu phẩy/chấm phẩy
    raw = re.sub(r'\.\s*\*\s+', '. ', raw)
    raw = re.sub(r',\s*\*\s+', ', ', raw)
    # Bullet đầu dòng gộp thành text liền
    raw = re.sub(r'(?:^|\n)\s*\*\s+', ' ', raw)

    # Thu gọn khoảng trắng
    raw = re.sub(r'\s{2,}', ' ', raw).strip()

    # Xoá ký tự thừa ở cuối
    raw = re.sub(r'[\s\*:\-\.]+$', '', raw)

    # Thêm dấu chấm kết thúc nếu chưa có
    if raw and raw[-1] not in ('.', '!', '?', '—'):
        raw += '.'

    return raw


def _enforce_pattern_markdown_format(text: str) -> str:
    """
    Đảm bảo output luôn có đúng 6 trường markdown chuẩn.
    Chỉ giữ lần xuất hiện ĐẦU TIÊN của mỗi trường, loại bỏ
    toàn bộ suy luận nội bộ, lặp lại, kịch bản phụ.
    """
    if not text:
        return text

    text = _strip_thinking_blocks(text)

    # Quét tìm vị trí xuất hiện đầu tiên của mỗi trường
    first_occurrences = []
    seen = set()
    for label, regex in _LABEL_REGEXES.items():
        match = re.search(regex, text, re.IGNORECASE)
        if match and label not in seen:
            seen.add(label)
            first_occurrences.append({
                "label": label,
                "match_start": match.start(),
                "value_start": match.end(),
            })

    if len(first_occurrences) < 2:
        # Không đủ trường → trả nguyên text đã clean
        return f"**Lỗi trích xuất định dạng:**\n\n{text}"

    # Sắp xếp theo thứ tự xuất hiện trong văn bản
    first_occurrences.sort(key=lambda x: x["match_start"])

    # Trích xuất giá trị từng trường
    segments = []
    for i, item in enumerate(first_occurrences):
        val_start = item["value_start"]
        # Kết thúc = đầu trường tiếp theo, hoặc cuối text
        val_end = (
            first_occurrences[i + 1]["match_start"]
            if i + 1 < len(first_occurrences)
            else len(text)
        )

        value = _extract_field_value(text, val_start, val_end)
        if not value:
            value = "—"

        segments.append(f"**{item['label']}:** {value}")

    return "\n\n".join(segments)


def _invoke_with_retry(call_fn, *args, retries: int = 2, wait_sec: int = 3):
    last_err = None
    for attempt in range(retries):
        try:
            return call_fn(*args)
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if any(k in err_str for k in (
                "runner process has terminated", "status code: 500",
                "out of memory", "cuda out of memory",
            )):
                print(f"[PatternAgent] Lỗi nghiêm trọng (lần {attempt+1}): {e}")
                break
            print(f"[PatternAgent] Lỗi lần {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(wait_sec)
    raise RuntimeError(f"[PatternAgent] Thất bại sau {retries} lần thử. Lỗi: {last_err}")


def _text_fallback_analysis(tool_llm, kline_data: dict, time_frame: str) -> str:
    """Fallback thuần văn bản khi không có ảnh hoặc model thị giác crash."""
    try:
        import pandas as pd
        df = pd.DataFrame(kline_data).tail(20)
        rows = []
        for _, r in df.iterrows():
            rows.append(f"  {r['Datetime']}  O={round(float(r['Open']),2)}"
                        f"  H={round(float(r['High']),2)}"
                        f"  L={round(float(r['Low']),2)}"
                        f"  C={round(float(r['Close']),2)}")
        ohlcv = "\n".join(rows)
    except Exception as e:
        ohlcv = f"(lỗi đọc OHLCV: {e})"

    prompt = (
        f"/no_think\n"
        f"Phân tích dữ liệu OHLCV khung {time_frame} sau.\n"
        f"{ohlcv}\n\n"
        "CHỈ trả lời đúng 6 dòng theo format dưới. KHÔNG giải thích thêm.\n\n"
        "**Mô hình:** <Tên mô hình tiếng Việt>\n"
        "**Độ tin cậy:** Cao | Trung bình | Thấp\n"
        "**Thiên lệch dự báo:** Tăng | Giảm | Trung tính\n"
        "**Bằng chứng:** <Mô tả ngắn gọn cấu trúc giá>\n"
        "**Nến quan trọng:** <Liệt kê nến nổi bật>\n"
        "**Hàm ý giao dịch:** <Kịch bản hành động ngắn gọn>"
    )
    response = tool_llm.invoke([HumanMessage(content=prompt)])
    return response.content


def create_pattern_agent(tool_llm, graph_llm, toolkit):

    PATTERN_TEXT = """
        Tham khảo: Vai đầu vai ngược, Đáy đôi, Nêm giảm/tăng, Tam giác, Cờ tăng/giảm, Hộp giá, Đảo chiều chữ V, Xu hướng rõ rệt.
    """

    SYSTEM_PROMPT = """/no_think
Bạn là AI phân tích mô hình giá (Price Action).

QUY TẮC TUYỆT ĐỐI:
1. CHỈ trả lời đúng 6 trường bên dưới bằng TIẾNG VIỆT. KHÔNG thêm trường nào khác.
2. KHÔNG suy luận, KHÔNG giải thích, KHÔNG viết "Tuy nhiên", "Hoặc", "Alternative", "Lưu ý".
3. KHÔNG đưa ra kịch bản dự phòng. Chỉ MỘT nhận định duy nhất.
4. Mỗi trường trên MỘT dòng. Ngắn gọn, xúc tích.

FORMAT BẮT BUỘC:
**Mô hình:** <Tên>
**Độ tin cậy:** Cao | Trung bình | Thấp
**Thiên lệch dự báo:** Tăng | Giảm | Trung tính
**Bằng chứng:** <Mô tả ngắn>
**Nến quan trọng:** <Liệt kê>
**Hàm ý giao dịch:** <Kịch bản>"""

    USER_PROMPT = """/no_think
Phân tích biểu đồ nến {time_frame}. {PATTERN_TEXT}

Trả về ĐÚNG 6 trường sau (mỗi trường 1 dòng, ngắn gọn, KHÔNG giải thích thêm):

**Mô hình:** Tên mô hình tiếng Việt
**Độ tin cậy:** Cao | Trung bình | Thấp
**Thiên lệch dự báo:** Tăng | Giảm | Trung tính
**Bằng chứng:** Cấu trúc giá cụ thể (đỉnh, đáy, phá vỡ...)
**Nến quan trọng:** Nến nổi bật nhất
**Hàm ý giao dịch:** Hành động giao dịch ngắn gọn

VÍ DỤ OUTPUT CHUẨN:
**Mô hình:** Vai đầu vai
**Độ tin cậy:** Cao
**Thiên lệch dự báo:** Giảm
**Bằng chứng:** Ba đỉnh (76, 77, 74), đỉnh giữa cao nhất, phá vỡ đường cổ tại 70
**Nến quan trọng:** Nến đỏ phá vỡ hỗ trợ 70 với thân dài
**Hàm ý giao dịch:** Bán khi phá vỡ đường cổ, mục tiêu 63, ngừng lỗ trên 74"""

    def pattern_agent_node(state):
        time_frame = state["time_frame"]
        kline_data = state["kline_data"]

        from utils.static_util import get_forecast_horizon
        horizon = get_forecast_horizon(time_frame)
        h_desc  = horizon["horizon_desc"]

        pattern_image_b64 = state.get("pattern_image")

        if pattern_image_b64:
            print("[PatternAgent] Dùng ảnh từ state.")
        else:
            print("[PatternAgent] Không có ảnh trong state — đang tạo qua static_util...")
            try:
                result = static_util.generate_kline_image(kline_data)
                pattern_image_b64 = result.get("pattern_image")
            except Exception as e:
                print(f"[PatternAgent] Không tạo được ảnh: {e}")

        raw_output = None
        if pattern_image_b64:
            image_content = [
                {
                    "type": "text",
                    "text": USER_PROMPT.format(time_frame=time_frame, PATTERN_TEXT=PATTERN_TEXT, h_desc=h_desc),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{pattern_image_b64}"},
                },
            ]
            human_msg = HumanMessage(content=image_content)

            try:
                response = _invoke_with_retry(
                    graph_llm.invoke,
                    [SystemMessage(content=SYSTEM_PROMPT), human_msg],
                )
                raw_output = response.content
                print("[PatternAgent] Phân tích thị giác hoàn thành.")
            except Exception as e:
                err_str = str(e).lower()
                if "at least one message" in err_str or "system" in err_str:
                    try:
                        response = _invoke_with_retry(graph_llm.invoke, [human_msg])
                        raw_output = response.content
                        print("[PatternAgent] Phân tích thị giác hoàn thành (thử lại không system).")
                    except Exception as e2:
                        print(f"[PatternAgent] Thị giác thất bại: {e2}")
                else:
                    print(f"[PatternAgent] Lỗi model thị giác: {e}")

        if not raw_output:
            try:
                raw_output = _text_fallback_analysis(tool_llm, kline_data, time_frame)
                print("[PatternAgent] Dự phòng văn bản hoàn thành.")
            except Exception as e:
                print(f"[PatternAgent] Dự phòng văn bản thất bại: {e}")
                raw_output = (
                    "**Mô hình:** Không xác định\n"
                    "**Độ tin cậy:** Thấp\n"
                    "**Thiên lệch dự báo:** Trung tính\n"
                    "**Bằng chứng:** Lỗi toàn tập không thể chạy model\n"
                    "**Nến quan trọng:** —\n"
                    "**Hàm ý giao dịch:** —"
                )

        # ── ÁP DỤNG BỘ PARSER VĂN BẢN ────────────────────────────────
        report_content = _enforce_pattern_markdown_format(raw_output)
        print(f"[PatternAgent] Hoàn thành ({len(report_content)} ký tự).")

        return {
            "messages":      state.get("messages", []),
            "pattern_report": report_content,
        }

    return pattern_agent_node