import json
import re
import time

import static_util
from langchain_core.messages import HumanMessage, SystemMessage


# ── Các trường bắt buộc trong báo cáo xu hướng ────────────────────────────────
_REQUIRED_FIELDS = [
    ("Hướng xu hướng",        r"h[uướ]?[oờ]?ng\s*xu\s*h[uướ]?[oờ]?ng"),
    ("Mức hỗ trợ",            r"m[uứ]?[cứ]?\s*h[oỗ]?\s*tr[oợ]?"),
    ("Mức kháng cự",          r"m[uứ]?[cứ]?\s*kh[aá]ng\s*c[uự]?"),
    ("Độ dốc đường xu hướng", r"[dđ][oộ]\s*d[oố]c"),
    ("Giá so với hỗ trợ",     r"gi[aá]\s*so\s*v[oớ]?i"),
    ("Phân tích chi tiết",    r"ph[aâ]n\s*t[ií]ch\s*chi\s*ti[eế]t"),
    ("Dự đoán xu hướng",      r"d[uự]\s*[dđ]o[aá]n"),
    ("Độ tin cậy",            r"[dđ][oộ]\s*tin\s*c[aậ]y"),
]

_FIELD_LABELS = [
    "Hướng xu hướng",
    "Mức hỗ trợ",
    "Mức kháng cự",
    "Độ dốc đường xu hướng",
    "Giá so với hỗ trợ",
    "Phân tích chi tiết",
    "Dự đoán xu hướng",
    "Độ tin cậy",
]


def _enforce_markdown_format(text: str) -> str:
    """
    Đảm bảo output luôn có định dạng markdown đúng chuẩn.

    Xử lý 2 trường hợp LLM trả về:
    1. Plain text một dòng kiểu "Hướng xu hướng: Tăng Mức hỗ trợ: 10.5 ..."
       → Tách ra thành các dòng markdown **Trường:** Giá trị
    2. Markdown đã đúng → chỉ đảm bảo có dấu xuống dòng đúng chỗ

    Luôn trả về chuỗi có đầy đủ **Trường:** trên mỗi dòng riêng.
    """
    if not text:
        return text

    # Bước 1: Kiểm tra xem đã có markdown chưa (có ít nhất 3 trường **...**)
    bold_count = len(re.findall(r'\*\*[^*]+\*\*\s*:', text))
    has_newlines = text.count('\n') >= 3

    if bold_count >= 3 and has_newlines:
        # Đã đúng format — chỉ chuẩn hóa xuống dòng giữa các trường
        return _normalize_existing_markdown(text)

    # Bước 2: Xử lý plain text — tách theo các từ khóa trường
    # Xây dựng pattern tách: tìm vị trí của từng label (có hoặc không có **)
    result = _parse_plain_text(text)
    if result:
        return result

    # Bước 3: Nếu không tách được, bọc nguyên văn bản trong section phân tích
    return f"**Phân tích xu hướng:**\n\n{text}"


def _normalize_existing_markdown(text: str) -> str:
    """Chuẩn hóa markdown đã có: đảm bảo mỗi **Trường:** nằm trên dòng mới."""
    # Chèn xuống dòng trước mỗi **...:** nếu chưa có
    normalized = re.sub(
        r'(?<!\n)(\*\*[^*\n]+\*\*\s*:)',
        r'\n\n\1',
        text
    )
    # Loại bỏ dòng trắng thừa đầu chuỗi
    return normalized.strip()


def _parse_plain_text(text: str) -> str:
    """
    Tách plain text thành markdown.
    """
    # Pattern: tìm các label (có thể có ** hoặc không)
    label_pattern = '|'.join(
        r'\*{0,2}' + re.escape(label) + r'\*{0,2}\s*:'
        for label in _FIELD_LABELS
    )
    # Tìm tất cả các vị trí match
    matches = list(re.finditer(label_pattern, text, re.IGNORECASE))

    if len(matches) < 2:
        return ""  # Không đủ trường để tách

    segments = []
    for i, match in enumerate(matches):
        label_raw = match.group(0).strip().rstrip(':').strip('*').strip()
        # Lấy nội dung từ sau dấu : đến label tiếp theo (hoặc hết chuỗi)
        start = match.end()
        end   = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[start:end].strip()
        # Loại bỏ các trường label tiếp theo lẫn vào value (phòng khi regex overlap)
        value = re.sub(label_pattern, '', value, flags=re.IGNORECASE).strip()
        if value:
            segments.append(f"**{label_raw}:** {value}")

    return "\n\n".join(segments) if segments else ""


def _invoke_with_retry(call_fn, *args, retries: int = 2, wait_sec: int = 3):
    """Wrapper thử lại — giảm số lần thử để tránh treo lâu với model thị giác."""
    last_err = None
    for attempt in range(retries):
        try:
            return call_fn(*args)
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if any(k in err_str for k in (
                "runner process has terminated",
                "status code: 500",
                "out of memory",
                "cuda out of memory",
            )):
                print(f"[TrendAgent] Lỗi nghiêm trọng của model (lần {attempt+1}): {e}")
                break
            print(f"[TrendAgent] Lỗi lần {attempt+1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(wait_sec)
    raise RuntimeError(f"[TrendAgent] Thất bại sau {retries} lần thử. Lỗi cuối: {last_err}")


def _text_fallback_analysis(tool_llm, kline_data: dict, time_frame: str) -> str:
    """
    Chạy phân tích xu hướng chỉ văn bản dùng agent LLM (qwen2.5:3b).
    Dùng làm dự phòng khi model thị giác không khả dụng.
    """
    from static_util import get_forecast_horizon
    horizon = get_forecast_horizon(time_frame)
    h_desc  = horizon["horizon_desc"]

    try:
        import pandas as pd
        df    = pd.DataFrame(kline_data).tail(30)
        lines = []
        for _, row in df.iterrows():
            lines.append(
                f"  {row['Datetime']}  M={round(float(row['Open']),2)}"
                f"  C={round(float(row['High']),2)}"
                f"  T={round(float(row['Low']),2)}"
                f"  Đ={round(float(row['Close']),2)}"
            )
        ohlcv_str = "\n".join(lines)
    except Exception:
        ohlcv_str = json.dumps(kline_data, indent=2)[:2000]

    fallback_prompt = (
        "Bạn là trợ lý nhận dạng mô hình xu hướng K-line trong bối cảnh giao dịch tần số cao.\n\n"
        f"Phân tích dữ liệu OHLCV {time_frame} sau đây. Mục tiêu: DỰ ĐOÁN {h_desc}. "
        f"Xác định mức hỗ trợ và kháng cự từ đỉnh/đáy gần đây, "
        f"sau đó dự đoán khả năng tăng/giảm.\n\n"
        f"=== DỮ LIỆU OHLCV (30 NẾN GẦN NHẤT) ===\n{ohlcv_str}\n\n"
        "ĐỊNH DẠNG TRẢ LỜI BẮT BUỘC — mỗi trường phải trên một dòng riêng, có dấu ** và xuống dòng:\n\n"
        "**Hướng xu hướng:** Tăng | Giảm | Đi ngang\n\n"
        "**Mức hỗ trợ:** <mức giá cụ thể>\n\n"
        "**Mức kháng cự:** <mức giá cụ thể>\n\n"
        "**Độ dốc đường xu hướng:** Đang tăng | Đang giảm | Nằm ngang\n\n"
        "**Giá so với hỗ trợ:** <đang bật lên / xuyên phá / nén lại>\n\n"
        "**Phân tích chi tiết:** <2–3 câu phân tích hành động giá, tương tác với hỗ trợ/kháng cự>\n\n"
        f"**Dự đoán xu hướng:** <1–2 câu dự báo cụ thể cho {h_desc} — tăng hay giảm và lý do>\n\n"
        "**Độ tin cậy:** Cao | Trung bình | Thấp\n\n"
        "QUAN TRỌNG: KHÔNG viết tất cả trên một dòng. Mỗi trường PHẢI trên dòng riêng."
    )
    response = tool_llm.invoke([HumanMessage(content=fallback_prompt)])
    return response.content


def create_trend_agent(tool_llm, graph_llm, toolkit):
    """
    Tạo nút tác nhân phân tích xu hướng cho HFT.
    - tool_llm  : qwen2.5:3b — phân tích văn bản & dự phòng
    - graph_llm : llava:13b  — phân tích thị giác (chỉ invoke, không bind_tools)
    """

    def trend_agent_node(state):
        time_frame = state["time_frame"]
        kline_data = state["kline_data"]

        # ── Horizon động ──────────────────────────────────────────────────
        from static_util import get_forecast_horizon
        horizon = get_forecast_horizon(time_frame)
        h_desc  = horizon["horizon_desc"]
        h_val   = horizon["horizon_val"]

        # ── Bước 1: Lấy ảnh xu hướng ─────────────────────────────────────
        trend_image_b64 = state.get("trend_image")

        if trend_image_b64:
            print("[TrendAgent] Dùng ảnh xu hướng đã tính sẵn từ state.")
        else:
            print("[TrendAgent] Không có ảnh trong state — đang tạo qua static_util...")
            try:
                result = static_util.generate_trend_image(kline_data)
                trend_image_b64 = result.get("trend_image")
                if trend_image_b64:
                    print("[TrendAgent] Tạo ảnh xu hướng thành công.")
                else:
                    print("[TrendAgent] generate_trend_image không trả về ảnh.")
            except Exception as e:
                print(f"[TrendAgent] Không tạo được ảnh xu hướng: {e}")

        # ── Bước 2: Thử phân tích thị giác, dự phòng văn bản nếu crash ───
        report_content = None

        if trend_image_b64:
            image_prompt = [
                {
                    "type": "text",
                    "text": (
                        f"Đây là biểu đồ nến {time_frame} (K-line) có kèm các đường xu hướng tự động:\n"
                        f"- **Đường xanh** = đường hỗ trợ (dẫn xuất từ giá đóng cửa)\n"
                        f"- **Đường đỏ** = đường kháng cự (dẫn xuất từ giá đóng cửa)\n\n"
                        f"MỤC TIÊU: Dự đoán {h_desc}.\n\n"
                        f"Nhiệm vụ của bạn:\n"
                        f"1. Phân tích cách giá tương tác với đường xanh và đường đỏ\n"
                        f"2. Xác định các nến đang bật lên, xuyên phá hay nén lại giữa hai đường\n"
                        f"3. Đánh giá độ dốc và khoảng cách giữa hai đường\n"
                        f"4. Dự đoán hướng cho **{h_val}**: tăng, giảm hoặc đi ngang\n\n"
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{trend_image_b64}"},
                },
            ]

            human_msg = HumanMessage(content=image_prompt)

            # Thử với SystemMessage trước
            try:
                vision_messages = [
                    SystemMessage(
                        content=(
                            "Bạn là chuyên gia phân tích xu hướng K-line trong giao dịch tần số cao. "
                            f"Mục tiêu duy nhất: DỰ ĐOÁN {h_desc}. "
                            "Bạn luôn trả lời theo đúng định dạng markdown được yêu cầu: "
                            "mỗi trường trên một dòng riêng, có dấu ** bao quanh tên trường. "
                            "KHÔNG BAO GIỜ viết tất cả trường trên một dòng. "
                            "Toàn bộ câu trả lời bằng tiếng Việt."
                        )
                    ),
                    human_msg,
                ]
                response = _invoke_with_retry(graph_llm.invoke, vision_messages)
                report_content = response.content
                print("[TrendAgent] Phân tích thị giác hoàn thành.")
            except Exception as e:
                err_str = str(e).lower()
                if "at least one message" in err_str or "system" in err_str:
                    try:
                        response = _invoke_with_retry(graph_llm.invoke, [human_msg])
                        report_content = response.content
                        print("[TrendAgent] Phân tích thị giác hoàn thành (thử lại không system).")
                    except Exception as e2:
                        print(f"[TrendAgent] Thử lại thị giác cũng thất bại: {e2}")
                else:
                    print(f"[TrendAgent] Lỗi model thị giác: {e}")

        # ── Bước 3: Dự phòng văn bản nếu thị giác thất bại hoặc không có ảnh ──
        if not report_content:
            ly_do = "không có ảnh" if not trend_image_b64 else "model thị giác không khả dụng"
            print(f"[TrendAgent] Dùng phân tích chỉ văn bản ({ly_do}).")
            try:
                report_content = _text_fallback_analysis(tool_llm, kline_data, time_frame)
                print("[TrendAgent] Phân tích dự phòng văn bản hoàn thành.")
            except Exception as e:
                print(f"[TrendAgent] Dự phòng văn bản cũng thất bại: {e}")
                report_content = (
                    "**Hướng xu hướng:** Không thể xác định — phân tích không khả dụng.\n\n"
                    "**Ghi chú:** Cả phân tích thị giác lẫn văn bản đều thất bại. "
                )

        # ── Bước 4: Đảm bảo output luôn có định dạng markdown đúng ───────
        report_content = _enforce_markdown_format(report_content)
        print(f"[TrendAgent] Hoàn thành ({len(report_content)} ký tự).")

        messages_out = state.get("messages", [])
        return {
            "messages": messages_out,
            "trend_report": report_content,
            "trend_image": trend_image_b64,
            "trend_image_filename": "trend_graph.png",
            "trend_image_description": (
                "Biểu đồ nến tăng cường xu hướng với đường hỗ trợ/kháng cự"
                if trend_image_b64 else None
            ),
        }

    return trend_agent_node