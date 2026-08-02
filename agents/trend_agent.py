import json
import re
import time

from utils import static_util
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

# Nhãn tiếng Anh tương ứng — parser nhận diện CẢ hai bộ nhãn để một hàm duy nhất
# xử lý được output của cả hai ngôn ngữ.
_FIELD_LABELS_EN = [
    "Trend direction",
    "Support level",
    "Resistance level",
    "Trendline slope",
    "Price vs support",
    "Detailed analysis",
    "Trend forecast",
    "Confidence",
]

_ALL_FIELD_LABELS = _FIELD_LABELS + _FIELD_LABELS_EN

# ── Giới hạn độ dài mỗi trường (ký tự) ────────────────────────────────────────
# Trường mô tả dài được cắt tại ranh giới câu để UI không bị tràn.
_MAX_FIELD_CHARS = {
    "Phân tích chi tiết": 220,
    "Detailed analysis":  220,
    "Dự đoán xu hướng":   180,
    "Trend forecast":     180,
}
_DEFAULT_MAX_CHARS = 80

# Các trường chỉ nhận giá trị liệt kê ngắn — nếu bị làm sạch thành rỗng thì lấy
# lại từ khoá đầu tiên khớp được, thay vì bỏ hẳn trường khỏi báo cáo.
_ENUM_FALLBACKS = {
    "Trend direction":  ["Up", "Down", "Sideways"],
    "Hướng xu hướng":   ["Tăng", "Giảm", "Đi ngang"],
    "Trendline slope":  ["Rising", "Falling", "Flat"],
    "Độ dốc đường xu hướng": ["Đang tăng", "Đang giảm", "Nằm ngang"],
    "Price vs support": ["Bouncing", "Breaking through", "Compressing"],
    "Giá so với hỗ trợ": ["Bật lên", "Xuyên phá", "Nén lại"],
    "Confidence":       ["High", "Medium", "Low"],
    "Độ tin cậy":       ["Cao", "Trung bình", "Thấp"],
}

# ── Meta-reasoning cần loại bỏ (song ngữ) ─────────────────────────────────────
# QUAN TRỌNG: các mẫu này chỉ được khớp ở ĐẦU một câu (xem `_META_RE` bên dưới),
# vì nhiều mẫu trùng với văn xuôi hợp lệ. Ví dụ "price will continue upward" chứa
# "will" — nếu khớp ở giữa câu thì giá trị bị cắt cụt thành rỗng và cả trường bị
# loại bỏ, khiến báo cáo tiếng Anh trắng hoàn toàn.
_META_PATTERNS = [
    # Tiếng Anh — mở bài / tự thoại
    r"Okay\s*[,.]", r"Alright\s*[,.]", r"Sure\s*[,.]",
    r"Let\s+me\s+", r"Let['']s\s+",
    r"Looking\s+at\s+(?:the\s+)?(?:chart|image|graph|data)",
    r"Based\s+on\s+(?:the\s+)?(?:chart|image|graph|data)",
    r"I\s+(?:need|will|should|can|must|am|have)\b",
    r"I[''](?:ll|m|ve)\b",
    r"First\s*,\s*I\b", r"Now\s*,\s*I\b", r"Next\s*,\s*I\b",
    r"To\s+summari[sz]e", r"In\s+summary", r"Overall\s*,",
    r"Note\s*:", r"Wait\s*[,.]", r"Actually\s*[,.]",
    r"Self[-\s]?Correction\s*:", r"Refinement\s*:", r"Alternative\s*:",
    r"As\s+an\s+AI", r"I\s+cannot\b", r"Since\s+I\s+can(?:not|['']t)\b",
    # Tiếng Việt
    r"Lưu\s*ý\s*:", r"Nhìn\s*vào\s*biểu\s*đồ", r"Dựa\s*vào\s*biểu\s*đồ",
    r"Tôi\s+(?:sẽ|cần|không\s+thể)\b", r"Đầu\s*tiên\s*,\s*tôi",
    r"Tóm\s*lại\s*[,:]", r"Kiểm\s*tra\s*lại\s*:",
]

# Chỉ cắt khi mẫu đứng ở đầu chuỗi hoặc ngay sau dấu kết câu / xuống dòng.
_META_RE = re.compile(
    r"(?:^|(?<=[.!?…])\s+|\n\s*)(?:" + "|".join(_META_PATTERNS) + r")",
    re.IGNORECASE,
)

# ── Biến thể tiếng Anh: chỉ cắt meta-reasoning ở ĐẦU giá trị ─────────────────
# Ở chế độ tiếng Anh, `_META_RE` cắt nhầm câu thứ hai hợp lệ ("... support.
# Overall, momentum slows.") vì lookbehind `(?<=[.!?…])\s+` khớp sau MỌI dấu
# chấm. Với EN ta chỉ cắt khi mẫu đứng ngay đầu giá trị hoặc đầu một dòng mới —
# đó là nơi model thực sự chèn lời tự thoại, còn giữa câu văn là nội dung thật.
_META_RE_EN = re.compile(
    r"(?:^|\n\s*)(?:" + "|".join(_META_PATTERNS) + r")",
    re.IGNORECASE,
)

# Nhãn EN → khoá canonical VI, để tra `_MAX_FIELD_CHARS` / `_ENUM_FALLBACKS`
# không phụ thuộc vào dạng chữ hoa/thường hay dấu ** mà model sinh ra.
_LABEL_CANON = {lbl.lower(): lbl for lbl in _ALL_FIELD_LABELS}


def _strip_thinking_blocks(text: str) -> str:
    """
    Xoá <think>...</think> và code fence — KHÔNG BAO GIỜ xoá sạch nội dung.

    QUAN TRỌNG: phiên bản cũ xoá từ `<think>` tới HẾT chuỗi khi thẻ không đóng.
    Model suy luận (Qwen3) bị cắt ở giới hạn token sẽ để lại `<think>` mở → toàn
    bộ báo cáo bị xoá, formatter nhận chuỗi rỗng và xuất ra bộ trường toàn "—".
    Đây là nguyên nhân báo cáo tiếng Anh trắng hoàn toàn (EN dài hơn nên bị cắt
    thường xuyên hơn VI).

    Nay: chỉ xoá cặp thẻ đóng-mở hoàn chỉnh. Với thẻ không đóng thì bỏ CHÍNH THẺ
    và giữ lại nội dung phía sau — nếu các trường nằm trong phần suy luận thì vẫn
    còn cơ hội tách được. Chỉ khi phần còn lại thực sự rỗng mới quay về văn bản gốc.
    """
    if not text:
        return text

    original = text

    # Cặp thẻ hoàn chỉnh — nội dung bên trong là suy luận thật, xoá được an toàn.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Thẻ lẻ (mở không đóng, hoặc đóng không mở): chỉ xoá thẻ, GIỮ nội dung.
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)

    text = text.replace("```markdown", "").replace("```json", "").replace("```", "")
    text = text.strip()

    # Lưới an toàn cuối: làm sạch đã xoá hết → dùng lại bản gốc chỉ bỏ thẻ.
    if not text:
        text = re.sub(r"</?think>", "", original, flags=re.IGNORECASE)
        text = text.replace("```markdown", "").replace("```json", "").replace("```", "")
        text = text.strip()

    return text


def _has_usable_content(report: str) -> bool:
    """
    Báo cáo có nội dung thật hay chỉ còn khung trường rỗng?

    Dùng để phát hiện trường hợp model trả về chuỗi rỗng / chỉ có thẻ <think>:
    formatter vẫn xuất đủ 8 trường nhưng giá trị toàn "—", nhìn như hệ thống
    chạy xong mà thực chất không có phân tích nào. Khi đó nút agent phải chạy
    dự phòng văn bản thay vì trả về khung rỗng cho UI.
    """
    if not report or not report.strip():
        return False
    # Bỏ nhãn trường + dấu markdown, chỉ giữ phần GIÁ TRỊ để đánh giá.
    probe = report
    for label in _ALL_FIELD_LABELS:
        probe = re.sub(rf"\*{{0,2}}{re.escape(label)}\*{{0,2}}\s*:\*{{0,2}}", " ",
                       probe, flags=re.IGNORECASE)
    probe = re.sub(r"[^0-9A-Za-zÀ-ỹ]+", "", probe)
    return len(probe) >= 8


def _truncate_at_sentence(value: str, limit: int) -> str:
    """Cắt `value` về <= limit ký tự tại ranh giới câu gần nhất."""
    if len(value) <= limit:
        return value
    window = value[:limit]
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut > limit * 0.4:          # còn đủ nội dung thì cắt theo câu
        return window[:cut + 1].strip()
    return window.rsplit(" ", 1)[0].rstrip(" ,;:-") + "."


def _clean_field_value(label: str, value: str, lang: str = "vi") -> str:
    """Làm sạch giá trị một trường: bỏ meta-reasoning, placeholder, rồi cắt ngắn."""
    if not value:
        return value

    original = value

    # Chuẩn hoá nhãn về đúng khoá canonical — nhãn model sinh ra có thể lẫn dấu
    # ** hoặc khác chữ hoa/thường, khiến tra `_MAX_FIELD_CHARS` trượt và trường
    # mô tả dài bị cắt còn 80 ký tự thay vì 220.
    label = _LABEL_CANON.get(label.strip().strip('*').strip().lower(), label)

    # Bỏ thẻ placeholder <...> và [...] mà model copy lại từ prompt mẫu
    value = re.sub(r"<[^>\n]{0,80}>", "", value)
    value = re.sub(r"\[[^\]\n]{0,80}\]", "", value)

    # Cắt đứt tại vị trí meta-reasoning đầu tiên.
    # EN dùng biến thể chỉ khớp ở đầu giá trị/đầu dòng (xem `_META_RE_EN`).
    meta_re = _META_RE_EN if lang == "en" else _META_RE
    m = meta_re.search(value)
    if m:
        value = value[:m.start()]

    # Bỏ bullet / số thứ tự đầu dòng, gộp về một đoạn liền mạch
    value = re.sub(r"(?:^|\n)\s*(?:[-*•]|\d+[.)])\s+", " ", value)
    value = re.sub(r"\*{2,}", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^[\s*:\-]+", "", value)
    value = re.sub(r"[\s*:\-]+$", "", value)

    # Trường liệt kê bị làm sạch thành rỗng → khôi phục từ khoá trong văn bản gốc
    if not value:
        for option in _ENUM_FALLBACKS.get(label, []):
            if re.search(rf"\b{re.escape(option)}\b", original, re.IGNORECASE):
                value = option
                break

    if not value:
        return ""

    value = _truncate_at_sentence(value, _MAX_FIELD_CHARS.get(label, _DEFAULT_MAX_CHARS))

    if value and value[-1] not in ".!?—":
        value += "."
    return value


def _enforce_markdown_format(text: str, lang: str = "vi") -> str:
    """
    Đảm bảo output luôn có định dạng markdown đúng chuẩn, ngắn gọn.

    1. Xoá <think>...</think> và code fence
    2. Tách theo nhãn trường (song ngữ VI/EN) → mỗi trường một dòng
    3. Làm sạch + cắt ngắn từng giá trị (bỏ meta-reasoning, placeholder)
    4. Không tách được → cắt ngắn nguyên văn thay vì đổ nguyên khối vào UI
    """
    if not text:
        return text

    text = _strip_thinking_blocks(text)

    # Luôn ưu tiên parser theo nhãn: nó vừa tách dòng vừa làm sạch giá trị.
    result = _parse_plain_text(text, lang=lang)
    if result:
        return result

    # Không nhận diện được trường nào → EN vẫn xuất đủ 8 trường
    if lang == "en":
        # Giữ lại phần văn xuôi còn dùng được (nếu có) ở "Detailed analysis"
        # thay vì vứt đi và trả về 8 dấu "—" trống rỗng.
        salvage = re.sub(r"<[^>\n]{0,80}>", "", text)
        salvage = re.sub(r"\s+", " ", salvage).strip()
        m = _META_RE_EN.search(salvage)
        if m:
            salvage = salvage[:m.start()].strip()
        values = {label: "—" for label in _FIELD_LABELS_EN}
        if salvage:
            values["Detailed analysis"] = _truncate_at_sentence(
                salvage, _MAX_FIELD_CHARS["Detailed analysis"])
        return "\n\n".join(
            f"**{label}:** {values[label]}" for label in _FIELD_LABELS_EN
        )

    # VI: giữ nguyên văn nhưng chặn độ dài
    heading = "Phân tích xu hướng"
    body = _clean_field_value(heading, text, lang=lang)
    if not body:
        # Làm sạch đã xoá sạch nội dung → dùng lại văn bản thô đã rút gọn thay vì
        # trả về một khối rỗng
        raw = re.sub(r"<[^>\n]{0,80}>", "", text)
        raw = re.sub(r"\s+", " ", raw).strip()
        if raw:
            body = _truncate_at_sentence(raw, _MAX_FIELD_CHARS.get(heading, 320))
        else:
            body = "Phân tích không khả dụng."
    return f"**{heading}:**\n\n{body}"


def _parse_plain_text(text: str, lang: str = "vi") -> str:
    """
    Tách text thành markdown một trường / một dòng.

    Chỉ giữ lần xuất hiện ĐẦU TIÊN của mỗi trường — model hay lặp lại cả bộ
    trường sau khi "suy nghĩ lại", những lần sau bị loại bỏ.
    """
    # Pattern: tìm các label song ngữ VI + EN.
    # Dấu ** có thể bọc CẢ dấu hai chấm (`**Nhãn:**` — dạng model thực sự sinh
    # ra và cũng là dạng trong prompt mẫu) hoặc chỉ bọc tên nhãn (`**Nhãn**:`).
    # Regex cũ chỉ nhận dạng thứ hai nên báo cáo tiếng Anh không tách được trường.
    label_pattern = '|'.join(
        r'\*{0,2}' + re.escape(label) + r'\*{0,2}\s*:\*{0,2}'
        for label in _ALL_FIELD_LABELS
    )
    # Tìm tất cả các vị trí match
    matches = list(re.finditer(label_pattern, text, re.IGNORECASE))

    if len(matches) < 1:
        return ""  # Không tìm thấy trường nào

    segments = []
    seen = set()
    found = {}
    for i, match in enumerate(matches):
        label_raw = match.group(0).strip().strip('*').rstrip(':').strip('*').strip()
        key = label_raw.lower()
        if key in seen:
            continue          # trường lặp lại — bỏ qua
        # Lấy nội dung từ sau dấu : đến label tiếp theo (hoặc hết chuỗi)
        start = match.end()
        end   = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[start:end].strip()
        # Loại bỏ các trường label tiếp theo lẫn vào value (phòng khi regex overlap)
        value = re.sub(label_pattern, '', value, flags=re.IGNORECASE).strip()
        value = _clean_field_value(label_raw, value, lang=lang)
        seen.add(key)
        # Chuẩn hoá về nhãn canonical để EN dựng lại đủ bộ trường bên dưới
        canon = _LABEL_CANON.get(key, label_raw)
        found[canon] = value or "—"
        if value:
            segments.append(f"**{label_raw}:** {value}")
        elif lang == "en":
            # Không bỏ trường: giữ chỗ bằng "—" để báo cáo luôn đủ 8 mục và
            # người dùng phân biệt được "model không trả lời" với "thiếu trường".
            segments.append(f"**{label_raw}:** —")

    if lang == "en":
        # Luôn xuất đủ 8 trường theo THỨ TỰ CHUẨN. Trường model không trả lời
        # (hoặc bị làm sạch thành rỗng) giữ chỗ bằng "—", nhờ vậy bản tiếng Anh
        # có cùng cấu trúc với bản tiếng Việt thay vì thiếu mục.
        # Nhãn VI vẫn được nhận diện: map sang nhãn EN tương ứng theo vị trí.
        vi_to_en = dict(zip(_FIELD_LABELS, _FIELD_LABELS_EN))
        normalized = {}
        for canon, val in found.items():
            normalized[vi_to_en.get(canon, canon)] = val
        return "\n\n".join(
            f"**{label}:** {normalized.get(label, '—')}"
            for label in _FIELD_LABELS_EN
        )

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


def _text_fallback_analysis(tool_llm, kline_data: dict, time_frame: str,
                            lang: str = "vi") -> str:
    """
    Chạy phân tích xu hướng chỉ văn bản dùng agent LLM (qwen2.5:3b).
    Dùng làm dự phòng khi model thị giác không khả dụng.
    """
    from utils.i18n import get_horizon, language_directive
    horizon = get_horizon(time_frame, lang)
    h_desc  = horizon["horizon_desc"]
    h_val   = horizon["horizon_val"]

    try:
        import pandas as pd
        df    = pd.DataFrame(kline_data).tail(30)
        lines = []
        o_l, h_l, l_l, c_l = ("O", "H", "L", "C") if lang == "en" else ("M", "C", "T", "Đ")
        for _, row in df.iterrows():
            lines.append(
                f"  {row['Datetime']}  {o_l}={round(float(row['Open']),2)}"
                f"  {h_l}={round(float(row['High']),2)}"
                f"  {l_l}={round(float(row['Low']),2)}"
                f"  {c_l}={round(float(row['Close']),2)}"
            )
        ohlcv_str = "\n".join(lines)
    except Exception:
        ohlcv_str = json.dumps(kline_data, indent=2)[:2000]

    if lang == "en":
        fallback_prompt = (
            "/no_think\n"
            "You are an assistant that recognises K-line trend patterns in a "
            "high-frequency trading context.\n\n"
            f"Analyse the following {time_frame} OHLCV data. Objective: FORECAST {h_desc}. "
            f"Identify support and resistance levels from the recent highs/lows, "
            f"then forecast the probability of an up or down move.\n\n"
            f"=== OHLCV DATA (30 MOST RECENT CANDLES) ===\n{ohlcv_str}\n\n"
            "Return EXACTLY the 8 fields below, one per line. No reasoning, no preamble.\n\n"
            "**Trend direction:** Up | Down | Sideways\n"
            "**Support level:** one price number\n"
            "**Resistance level:** one price number\n"
            "**Trendline slope:** Rising | Falling | Flat\n"
            "**Price vs support:** Bouncing | Breaking through | Compressing\n"
            "**Detailed analysis:** max 2 sentences\n"
            f"**Trend forecast:** max 2 sentences for {h_val}\n"
            "**Confidence:** High | Medium | Low\n\n"
            "IMPORTANT: Do NOT write angle brackets < >. Do NOT repeat a field. "
            "Do NOT narrate your reasoning.\n\n"
            f"{language_directive(lang)}"
        )
    else:
        fallback_prompt = (
            "/no_think\n"
            "Bạn là trợ lý nhận dạng mô hình xu hướng K-line trong bối cảnh giao dịch tần số cao.\n\n"
            f"Phân tích dữ liệu OHLCV {time_frame} sau đây. Mục tiêu: DỰ ĐOÁN {h_desc}. "
            f"Xác định mức hỗ trợ và kháng cự từ đỉnh/đáy gần đây, "
            f"sau đó dự đoán khả năng tăng/giảm.\n\n"
            f"=== DỮ LIỆU OHLCV (30 NẾN GẦN NHẤT) ===\n{ohlcv_str}\n\n"
            "Trả về ĐÚNG 8 trường dưới đây, mỗi trường 1 dòng. Không suy luận, không mở bài.\n\n"
            "**Hướng xu hướng:** Tăng | Giảm | Đi ngang\n"
            "**Mức hỗ trợ:** một mức giá cụ thể\n"
            "**Mức kháng cự:** một mức giá cụ thể\n"
            "**Độ dốc đường xu hướng:** Đang tăng | Đang giảm | Nằm ngang\n"
            "**Giá so với hỗ trợ:** Bật lên | Xuyên phá | Nén lại\n"
            "**Phân tích chi tiết:** tối đa 2 câu\n"
            f"**Dự đoán xu hướng:** tối đa 2 câu cho {h_val}\n"
            "**Độ tin cậy:** Cao | Trung bình | Thấp\n\n"
            "QUAN TRỌNG: KHÔNG dùng ngoặc nhọn < >. KHÔNG lặp lại trường. "
            "KHÔNG thuật lại quá trình suy nghĩ.\n\n"
            f"{language_directive(lang)}"
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

        # ── i18n ──────────────────────────────────────────────────────────
        from utils.i18n import lang_of, get_horizon, language_directive
        lang    = lang_of(state)
        horizon = get_horizon(time_frame, lang)
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
            if lang == "en":
                prompt_text = (
                    f"/no_think\n"
                    f"This is a {time_frame} candlestick (K-line) chart with automatic trendlines:\n"
                    f"- **Green line** = support line (derived from closing prices)\n"
                    f"- **Red line** = resistance line (derived from closing prices)\n\n"
                    f"OBJECTIVE: Forecast {h_desc}.\n\n"
                    f"Return EXACTLY the 8 fields below and nothing else. "
                    f"Begin directly with \"**Trend direction:**\". "
                    f"No preamble, no reasoning, no closing remarks.\n\n"
                    "**Trend direction:** Up | Down | Sideways\n"
                    "**Support level:** one price number\n"
                    "**Resistance level:** one price number\n"
                    "**Trendline slope:** Rising | Falling | Flat\n"
                    "**Price vs support:** Bouncing | Breaking through | Compressing\n"
                    "**Detailed analysis:** max 2 sentences (<= 30 words) on price action vs the two lines\n"
                    f"**Trend forecast:** max 2 sentences (<= 25 words) on {h_val} — direction and why\n"
                    "**Confidence:** High | Medium | Low\n\n"
                    "RULES: The first five fields are a single word or number each. "
                    "Do not write angle brackets < >. Do not repeat a field. "
                    "Do not explain your reasoning process.\n\n"
                    "EXAMPLE OF A CORRECT OUTPUT:\n"
                    "**Trend direction:** Up\n"
                    "**Support level:** 61200\n"
                    "**Resistance level:** 63400\n"
                    "**Trendline slope:** Rising\n"
                    "**Price vs support:** Bouncing\n"
                    "**Detailed analysis:** Price holds above the green support line with higher lows. "
                    "Momentum slows as it approaches the red resistance.\n"
                    "**Trend forecast:** Continuation toward 63400 while support at 61200 holds.\n"
                    "**Confidence:** Medium"
                )
            else:
                prompt_text = (
                    f"/no_think\n"
                    f"Đây là biểu đồ nến {time_frame} (K-line) có kèm các đường xu hướng tự động:\n"
                    f"- **Đường xanh** = đường hỗ trợ (dẫn xuất từ giá đóng cửa)\n"
                    f"- **Đường đỏ** = đường kháng cự (dẫn xuất từ giá đóng cửa)\n\n"
                    f"MỤC TIÊU: Dự đoán {h_desc}.\n\n"
                    f"Trả về ĐÚNG 8 trường dưới đây, mỗi trường một dòng, không thêm gì khác. "
                    f"Không mở bài, không suy luận, không kết luận thừa.\n\n"
                    "**Hướng xu hướng:** Tăng | Giảm | Đi ngang\n"
                    "**Mức hỗ trợ:** một mức giá cụ thể\n"
                    "**Mức kháng cự:** một mức giá cụ thể\n"
                    "**Độ dốc đường xu hướng:** Đang tăng | Đang giảm | Nằm ngang\n"
                    "**Giá so với hỗ trợ:** Bật lên | Xuyên phá | Nén lại\n"
                    "**Phân tích chi tiết:** tối đa 2 câu về hành động giá so với hai đường\n"
                    f"**Dự đoán xu hướng:** tối đa 2 câu cho {h_val} — hướng và lý do\n"
                    "**Độ tin cậy:** Cao | Trung bình | Thấp\n\n"
                    "QUY TẮC: Không dùng ngoặc nhọn < >. Không lặp lại trường. "
                    "Không trình bày quá trình suy luận."
                )

            image_prompt = [
                {
                    "type": "text",
                    "text": prompt_text,
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{trend_image_b64}"},
                },
            ]

            human_msg = HumanMessage(content=image_prompt)

            if lang == "en":
                system_text = (
                    "You are an expert K-line trend analyst in high-frequency trading. "
                    f"Your single objective: FORECAST {h_desc}. "
                    "You reply ONLY with the requested fields, one per line, each field name "
                    "wrapped in **. You never narrate your thought process, never write a "
                    "preamble or a summary, and never repeat a field. Be terse and concrete: "
                    "numbers and short clauses, not paragraphs. "
                    f"{language_directive(lang)}"
                )
            else:
                system_text = (
                    "Bạn là chuyên gia phân tích xu hướng K-line trong giao dịch tần số cao. "
                    f"Mục tiêu duy nhất: DỰ ĐOÁN {h_desc}. "
                    "Bạn CHỈ trả lời đúng các trường được yêu cầu, mỗi trường một dòng, tên "
                    "trường bọc trong **. Không thuật lại quá trình suy nghĩ, không mở bài, "
                    "không tổng kết, không lặp lại trường. Viết ngắn gọn, cụ thể: số liệu và "
                    "mệnh đề ngắn, không viết thành đoạn văn. "
                    f"{language_directive(lang)}"
                )

            # Thử với SystemMessage trước
            try:
                vision_messages = [
                    SystemMessage(content=system_text),
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
            if lang == "en":
                ly_do = "no image" if not trend_image_b64 else "vision model unavailable"
            else:
                ly_do = "không có ảnh" if not trend_image_b64 else "model thị giác không khả dụng"
            print(f"[TrendAgent] Dùng phân tích chỉ văn bản ({ly_do}).")
            try:
                report_content = _text_fallback_analysis(
                    tool_llm, kline_data, time_frame, lang=lang
                )
                print("[TrendAgent] Phân tích dự phòng văn bản hoàn thành.")
            except Exception as e:
                print(f"[TrendAgent] Dự phòng văn bản cũng thất bại: {e}")
                if lang == "en":
                    report_content = (
                        "**Trend direction:** Cannot be determined — analysis unavailable.\n\n"
                        "**Note:** Both the vision and the text analysis failed. "
                    )
                else:
                    report_content = (
                        "**Hướng xu hướng:** Không thể xác định — phân tích không khả dụng.\n\n"
                        "**Ghi chú:** Cả phân tích thị giác lẫn văn bản đều thất bại. "
                    )

        # ── Bước 4: Đảm bảo output luôn có định dạng markdown đúng ───────
        report_content = _enforce_markdown_format(report_content, lang=lang)
        print(f"[TrendAgent] Hoàn thành ({len(report_content)} ký tự).")

        messages_out = state.get("messages", [])
        return {
            "messages": messages_out,
            "trend_report": report_content,
            "trend_image": trend_image_b64,
            "trend_image_filename": "trend_graph.png",
            "trend_image_description": (
                (
                    "Trend-enhanced candlestick chart with support/resistance lines"
                    if lang == "en" else
                    "Biểu đồ nến tăng cường xu hướng với đường hỗ trợ/kháng cự"
                )
                if trend_image_b64 else None
            ),
        }

    return trend_agent_node