from agents import indicator_agent
import time
import json
import re

from utils import static_util
from langchain_core.messages import HumanMessage, SystemMessage

# ── Các trường bắt buộc trong báo cáo mô hình (thứ tự cố định) ────────────
# Khoá canonical LUÔN là tiếng Việt; nhãn hiển thị được dịch khi render.
_PATTERN_FIELDS = [
    "Mô hình",
    "Độ tin cậy",
    "Thiên lệch dự báo",
    "Bằng chứng",
    "Nến quan trọng",
    "Hàm ý giao dịch",
]

# Nhãn hiển thị theo ngôn ngữ / Display labels per language
_FIELD_LABELS = {
    "vi": {f: f for f in _PATTERN_FIELDS},
    "en": {
        "Mô hình":           "Pattern",
        "Độ tin cậy":        "Confidence",
        "Thiên lệch dự báo": "Directional bias",
        "Bằng chứng":        "Evidence",
        "Nến quan trọng":    "Key candles",
        "Hàm ý giao dịch":   "Trading implication",
    },
}

# ── Regex nhận diện từng nhãn (song ngữ, linh hoạt dấu *, khoảng trắng, số) ──
# Mỗi khoá canonical khớp CẢ nhãn tiếng Việt và tiếng Anh để một parser duy nhất
# xử lý được output của cả hai ngôn ngữ.
# Đuôi `\*{0,2}` sau dấu hai chấm là bắt buộc: model sinh ra `**Pattern:**` (dấu
# hai chấm nằm TRONG cặp **), nếu không nuốt hai dấu * này thì chúng lọt vào đầu
# giá trị và bị bước làm sạch cắt mất.
#
# Mỗi nhánh còn nhận các BIẾN THỂ rút gọn mà model thực sự sinh ra
# ("Implication:" thay vì "Trading implication:", "Candles:" thay vì
# "Key candles:"). Không có chúng thì parser trượt nhãn, trường bị bỏ trống và
# hiển thị thành "—"/"__".
_LABEL_REGEXES = {
    "Mô hình":
        r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:\*{0,2})(?:Mô\s*hình|Pattern(?:\s*name)?"
        r"|Chart\s*pattern|Price\s*pattern)(?:\*{0,2})\s*:\*{0,2}",
    "Độ tin cậy":
        r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:\*{0,2})(?:Độ\s*tin\s*cậy|Tin\s*cậy"
        r"|Confidence(?:\s*level)?|Certainty)(?:\*{0,2})\s*:\*{0,2}",
    "Thiên lệch dự báo":
        r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:\*{0,2})(?:Thiên\s*lệch(?:\s*dự\s*báo)?"
        r"|Directional\s*bias|Direction(?:al)?|Bias|Outlook)(?:\*{0,2})\s*:\*{0,2}",
    "Bằng chứng":
        r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:\*{0,2})(?:Bằng\s*chứng|Chứng\s*cứ"
        r"|Evidence|Rationale|Reasoning)(?:\*{0,2})\s*:\*{0,2}",
    "Nến quan trọng":
        r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:\*{0,2})(?:Nến\s*quan\s*trọng|Nến\s*chính"
        r"|Key\s*candles?|Notable\s*candles?|Candles?)(?:\*{0,2})\s*:\*{0,2}",
    "Hàm ý giao dịch":
        r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?(?:\*{0,2})(?:Hàm\s*ý(?:\s*giao\s*dịch)?"
        r"|Trading\s*implication|Implication|Trade\s*setup|Action)(?:\*{0,2})\s*:\*{0,2}",
}

# Chuỗi placeholder model để lại khi không điền được trường — phải coi như RỖNG
# để cơ chế dự phòng tính giá trị thật, thay vì hiển thị nguyên "__" cho người dùng.
_PLACEHOLDER_VALUE_RE = re.compile(
    r"^[\s_\-—–\.\*]*$|^n/?a\.?$|^unknown\.?$|^none\.?$|^không\s*xác\s*định\.?$",
    re.IGNORECASE,
)

# ── Các marker đánh dấu nội dung "suy luận nội bộ" cần loại bỏ ────────────
# Chỉ khớp ở đầu chuỗi / sau dấu kết câu / đầu dòng — nhiều mẫu ("However,",
# "Wait,") cũng xuất hiện trong văn xuôi hợp lệ, khớp giữa câu sẽ cắt cụt nội dung.
_GARBAGE_PATTERNS = [
    # Tiếng Anh & meta-reasoning
    r"Alternative\s*:", r"Note\s*:", r"Wait\s*[,.]", r"However\s*,",
    r"Self[-\s]?Correction\s*:", r"Refinement\s*:", r"Final\s*Check\s*:",
    r"One\s+more\s+look", r"Let\s+me\s+", r"Let['']s\s+",
    r"Okay\s*[,.]", r"Alright\s*[,.]", r"Sure\s*[,.]",
    r"Looking\s+at\s+(?:the\s+)?(?:chart|image|graph|data)",
    r"Based\s+on\s+(?:the\s+)?(?:chart|image|graph|data)",
    r"I\s+(?:need|will|should|can|must|am|have)\b",
    r"I[''](?:ll|m|ve)\b",
    # Model nói về NGƯỜI DÙNG ở ngôi thứ ba — dấu hiệu suy luận rõ nhất của
    # qwen3: "The user wants me to analyze a candlestick chart...".
    r"The\s+user\s+(?:wants|asks|is\s+asking|has\s+asked|requests|would\s+like)",
    r"The\s+user['']?s\s+(?:request|prompt|question|query)",
    r"Người\s*dùng\s+(?:muốn|yêu\s*cầu|đang\s*hỏi)",
    r"First\s*,\s*I\b", r"Now\s*,\s*I\b",
    r"To\s+summari[sz]e", r"In\s+summary", r"Overall\s*,",
    r"As\s+an\s+AI", r"I\s+cannot\b",
    r"Input\s*Data\s*:", r"visual\s*cues", r"prompt['']?s\s*context",
    r"simulate\s*a\s*standard", r"stick\s*to\s*the\s*rules",
    # Tiếng Việt
    r"Lưu\s*ý\s*:", r"Hoặc\s*:", r"Nhìn\s*kỹ\s*lại",
    r"Quyết\s*định\s*:", r"Kiểm\s*tra\s*lại", r"Tóm\s*lại\s*[,:]",
    r"Nhìn\s*vào\s*biểu\s*đồ", r"Dựa\s*vào\s*biểu\s*đồ",
    # Đánh dấu số thứ tự lặp (LLM lải nhải lặp trường)
    r"\d+\.\s*\*{0,2}(?:Mô hình|Độ tin cậy|Thiên lệch|Bằng chứng|Nến quan trọng|Hàm ý)",
]
_GARBAGE_RE = re.compile(
    r"(?:^|(?<=[.!?…])\s+|\n\s*)(?:" + "|".join(_GARBAGE_PATTERNS) + r")",
    re.IGNORECASE,
)

# ── Biến thể tiếng Anh: chỉ cắt ở ĐẦU giá trị hoặc đầu dòng ──────────────────
# `_GARBAGE_RE` dùng lookbehind `(?<=[.!?…])\s+` nên khớp sau MỌI dấu chấm.
# Ở tiếng Anh điều đó cắt nhầm câu thứ hai hợp lệ, ví dụ:
#   "Price holds above support. Overall, momentum slows."
# → phần sau dấu chấm bị xoá, trường rỗng và biến mất khỏi báo cáo.
# Với EN chỉ cắt khi mẫu đứng đầu giá trị / đầu dòng mới — nơi model thật sự
# chèn lời tự thoại.
_GARBAGE_RE_EN = re.compile(
    r"(?:^|\n\s*)(?:" + "|".join(_GARBAGE_PATTERNS) + r")",
    re.IGNORECASE,
)

# ── Giới hạn độ dài mỗi trường (ký tự) ────────────────────────────────────
# Không có giới hạn thì output của model thị giác tràn ra ngoài khung UI.
_MAX_FIELD_CHARS = {
    "Mô hình":           70,
    "Độ tin cậy":        30,
    "Thiên lệch dự báo": 30,
    "Bằng chứng":        200,
    "Nến quan trọng":    120,
    "Hàm ý giao dịch":   200,
}
_DEFAULT_MAX_CHARS = 120

# Trường liệt kê — khôi phục khi bị làm sạch thành rỗng
_ENUM_FALLBACKS = {
    "Độ tin cậy":        {"vi": ["Cao", "Trung bình", "Thấp"],
                          "en": ["High", "Medium", "Low"]},
    "Thiên lệch dự báo": {"vi": ["Tăng", "Giảm", "Trung tính"],
                          "en": ["Bullish", "Bearish", "Neutral"]},
}


# ── Prompt thử lại "cộc lốc" khi model mải suy luận mà không sinh báo cáo ────
# Không lời dẫn, không ví dụ, không nhắc quy tắc — chỉ khung 6 dòng cần điền.
# Càng ít chữ thì model suy luận càng ít cớ để mở đầu bằng chain-of-thought.
_TERSE_RETRY_EN = (
    "Fill in these six lines from the chart. Output only these lines, nothing before "
    "or after. Do not explain.\n\n"
    "**Pattern:**\n"
    "**Confidence:**\n"
    "**Directional bias:**\n"
    "**Evidence:**\n"
    "**Key candles:**\n"
    "**Trading implication:**"
)

_TERSE_RETRY_VI = (
    "Điền sáu dòng sau dựa vào biểu đồ. Chỉ xuất đúng các dòng này, không thêm gì "
    "trước hay sau. Không giải thích.\n\n"
    "**Mô hình:**\n"
    "**Độ tin cậy:**\n"
    "**Thiên lệch dự báo:**\n"
    "**Bằng chứng:**\n"
    "**Nến quan trọng:**\n"
    "**Hàm ý giao dịch:**"
)


def _truncate_at_sentence(value: str, limit: int) -> str:
    """Cắt `value` về <= limit ký tự tại ranh giới câu gần nhất."""
    if len(value) <= limit:
        return value
    window = value[:limit]
    cut = max(window.rfind('. '), window.rfind('! '), window.rfind('? '))
    if cut > limit * 0.4:
        return window[:cut + 1].strip()
    return window.rsplit(' ', 1)[0].rstrip(' ,;:-')


def _strip_thinking_blocks(text: str, restore_if_empty: bool = True) -> str:
    """
    Xoá <think>...</think>, phần mở bài meta và ```markdown``` wrappers.

    QUAN TRỌNG: phiên bản cũ dùng `re.sub(r"<think>.*", "")` nên khi thẻ KHÔNG
    ĐÓNG (model suy luận Qwen3 bị cắt ở giới hạn token) thì toàn bộ báo cáo phía
    sau bị xoá sạch. Formatter nhận chuỗi rỗng → không khớp trường nào → xuất ra
    đúng khung "Pattern: Unknown" + 5 dấu "—". Đây là nguyên nhân báo cáo tiếng
    Anh trắng hoàn toàn (EN dài hơn VI nên bị cắt thường xuyên hơn).

    Nay: chỉ xoá CẶP thẻ hoàn chỉnh. Thẻ lẻ thì bỏ chính thẻ và GIỮ nội dung —
    các trường thường nằm ngay trong phần suy luận nên vẫn tách được.

    `restore_if_empty=True` (mặc định, dùng khi render): nếu sau khi xoá cặp thẻ
    mà rỗng thì khôi phục nội dung bên trong — còn hơn là trả khung trắng.
    `restore_if_empty=False` (dùng khi *phát hiện* nội dung): KHÔNG khôi phục,
    vì reply chỉ gồm một cặp <think> đóng kín là suy luận thuần, không phải báo
    cáo — lúc đó phải chạy dự phòng văn bản.
    """
    if not text:
        return text

    original = text

    # Cặp thẻ hoàn chỉnh — nội dung bên trong là suy luận thật, xoá an toàn.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Thẻ lẻ (mở không đóng, hoặc đóng không mở): chỉ xoá thẻ, GIỮ nội dung.
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)

    # Xoá markdown/json code fences
    text = text.replace("```markdown", "").replace("```json", "").replace("```", "")

    # Lưới an toàn: nếu làm sạch đã xoá hết thì dùng lại bản gốc chỉ bỏ thẻ.
    if restore_if_empty and not text.strip():
        text = re.sub(r"</?think>", "", original, flags=re.IGNORECASE)
        text = text.replace("```markdown", "").replace("```json", "").replace("```", "")

    # Nếu model mở bài bằng meta-reasoning rồi mới xuống các trường, chỉ bỏ phần
    # mở bài. KHÔNG dùng .* + DOTALL ở đây: nó sẽ xoá luôn toàn bộ báo cáo phía sau.
    first_field = re.search(
        r"(?:^|\n)\s*(?:\d+[\.\)]\s*)?\*{0,2}"
        r"(?:Mô\s*hình|Pattern)\*{0,2}\s*:\*{0,2}",
        text, re.IGNORECASE,
    )
    if first_field and first_field.start() > 0:
        preamble = text[:first_field.start()]
        if _GARBAGE_RE.search(preamble) or len(preamble.split()) > 12:
            text = text[first_field.start():]

    return text.strip()


def _has_usable_content(raw: str) -> bool:
    """
    Output thô của model có phải là một BÁO CÁO dùng được, hay chỉ là suy luận?

    Dùng để phát hiện trường hợp model thị giác trả về chuỗi rỗng hoặc bị cắt ở
    giữa phần suy luận: formatter vẫn xuất đủ 6 trường nhưng giá trị toàn "—",
    nhìn như hệ thống chạy xong mà thực chất không có phân tích nào. Khi đó phải
    chạy dự phòng văn bản thay vì trả khung rỗng cho UI.

    QUAN TRỌNG — câu hỏi phải là "có BÁO CÁO không?", KHÔNG phải "có CHỮ không?".
    Bản cũ chỉ đếm ký tự chữ-số (>= 8) nên một đoạn suy luận dài bất kỳ cũng đạt.
    Model suy luận (qwen3 qua Groq, `/no_think` KHÔNG có hiệu lực) thường xuyên
    hết token khi còn đang suy luận, chưa kịp sinh `**Pattern:**` nào. Đoạn suy
    luận đó vượt qua guard → bỏ qua dự phòng văn bản ở `pattern_agent_node` →
    formatter không khớp nhãn nào → xuất đúng khung "Pattern: Unknown" + 5 dấu
    "—", với lời tự thoại lọt vào trường "Evidence". Đây là bug báo cáo EN trắng.

    Nay: KHÔNG có nhãn trường nào mà lại còn dấu hiệu meta-reasoning → coi như
    KHÔNG dùng được, để rơi xuống dự phòng và có báo cáo thật.
    """
    if not raw or not raw.strip():
        return False

    # Không khôi phục nội dung <think>: reply chỉ gồm suy luận thì KHÔNG dùng được.
    probe = _strip_thinking_blocks(raw, restore_if_empty=False)

    # Có ít nhất một nhãn trường thật không? Nếu có, đây là báo cáo (dù bị cắt
    # dở) và parser tách được — chấp nhận. Nếu không, phải xét kỹ bên dưới.
    has_label = any(
        re.search(rx, probe, re.IGNORECASE) for rx in _LABEL_REGEXES.values()
    )

    # Không nhãn + có dấu hiệu tự thoại ("The user wants me to...", "I need to",
    # "Looking at the chart"...) → suy luận thuần, không phải báo cáo.
    if not has_label and (_GARBAGE_RE.search(probe) or _GARBAGE_RE_EN.search(probe)):
        return False

    # Bỏ nhãn trường (cả VI và EN) — chỉ giữ phần GIÁ TRỊ để đánh giá.
    # Không tái dùng `_LABEL_REGEXES` vì chúng neo vào `(?:^|\n)`: sau lần thay
    # thứ nhất, neo không còn đúng cho các nhãn tiếp theo trên cùng dòng và phần
    # nhãn còn sót sẽ bị đếm thành "nội dung thật".
    probe = re.sub(
        r"\*{0,2}(?:Mô\s*hình|Pattern|Độ\s*tin\s*cậy|Confidence"
        r"|Thiên\s*lệch(?:\s*dự\s*báo)?|Directional\s*bias|Bias"
        r"|Bằng\s*chứng|Evidence|Nến\s*quan\s*trọng|Key\s*candles?"
        r"|Hàm\s*ý(?:\s*giao\s*dịch)?|Trading\s*implication)"
        r"\*{0,2}\s*:\*{0,2}",
        " ", probe, flags=re.IGNORECASE,
    )

    # Bỏ placeholder và ký tự trang trí, chỉ đếm ký tự có nghĩa.
    probe = re.sub(r"<[^>]*>", "", probe)
    probe = re.sub(r"[^0-9A-Za-zÀ-ỹ]+", "", probe)
    return len(probe) >= 8


def _extract_field_value(text: str, start: int, end: int, lang: str = "vi",
                         label: str = "") -> str:
    """
    Trích xuất và làm sạch giá trị của một trường từ vị trí start đến end.
    Cắt bỏ mọi nội dung lải nhải, suy luận, tiếng Anh trong ngoặc và thẻ placeholder <...>,
    rồi giới hạn độ dài để UI không bị tràn.
    """
    raw = text[start:end].strip()
    original = raw

    # Xoá mọi thẻ ngoặc nhọn placeholder như <tên>, <mô tả ngắn>, <liệt kê>, <kịch bản>...
    raw = re.sub(r'<[^>]*>', '', raw)
    raw = re.sub(r'\[[^\]]*\]', '', raw)

    # Xoá ký tự thừa ở đầu (dấu *, -, :, khoảng trắng)
    raw = re.sub(r'^[\s\*:\-]+', '', raw)

    # Cắt đứt tại vị trí xuất hiện garbage đầu tiên.
    # EN dùng biến thể chỉ khớp ở đầu giá trị/đầu dòng (xem `_GARBAGE_RE_EN`).
    garbage_re = _GARBAGE_RE_EN if lang == "en" else _GARBAGE_RE
    m = garbage_re.search(raw)
    if m:
        raw = raw[:m.start()]

    # Xoá giải thích tiếng Anh thuần trong ngoặc, vd: "(Head and Shoulders)".
    # CHỈ áp dụng cho tiếng Việt — ở chế độ tiếng Anh đây là nội dung hợp lệ.
    if lang != "en":
        raw = re.sub(r'\s*\([A-Za-z]{3,}[A-Za-z\s\-&]*\)', '', raw)

    # Xoá các dấu * thừa bên trong
    raw = re.sub(r'\*{2,}', '', raw)

    # Xoá các giải thích phụ thường xuất hiện trong output lải nhải
    raw = re.sub(r'\.\s*\*?\s*Lý\s+do\s*:.*', '.', raw, flags=re.DOTALL)
    raw = re.sub(r'\.\s+Vì\s+.*', '.', raw, flags=re.DOTALL)
    raw = re.sub(r'\.\s+Đây\s+là\s+.*', '.', raw, flags=re.DOTALL)
    raw = re.sub(r'\.\s+Đánh\s+giá\b.*', '.', raw, flags=re.DOTALL)

    # Xoá số thứ tự rời rạc cuối dòng (vd: "... 3." hoặc "... 8.")
    raw = re.sub(r'\s+\d+\.\s*$', '', raw)

    # Xoá các bullet "* " lẫn trong text thành dấu phẩy/chấm phẩy
    raw = re.sub(r'\.\s*\*\s+', '. ', raw)
    raw = re.sub(r',\s*\*\s+', ', ', raw)
    raw = re.sub(r'(?:^|\n)\s*\*\s+', ' ', raw)

    # Gộp mọi xuống dòng về một đoạn liền mạch (mỗi trường đúng 1 dòng)
    raw = re.sub(r'\s*\n+\s*', ' ', raw)

    # Thu gọn khoảng trắng
    raw = re.sub(r'\s{2,}', ' ', raw).strip()

    # Xoá ký tự thừa ở cuối
    raw = re.sub(r'[\s\*:\-\.]+$', '', raw)

    # Trường liệt kê bị làm sạch thành rỗng → khôi phục từ khoá trong văn bản gốc
    if not raw and label in _ENUM_FALLBACKS:
        options = _ENUM_FALLBACKS[label].get(lang if lang == "en" else "vi", [])
        for option in options:
            if re.search(rf'\b{re.escape(option)}\b', original, re.IGNORECASE):
                raw = option
                break

    # Giới hạn độ dài — nguyên nhân chính khiến UI không hiển thị hết
    if raw:
        raw = _truncate_at_sentence(raw, _MAX_FIELD_CHARS.get(label, _DEFAULT_MAX_CHARS))
        raw = raw.rstrip(' ,;:-')

    # Thêm dấu chấm kết thúc nếu chưa có
    if raw and raw[-1] not in ('.', '!', '?', '—'):
        raw += '.'

    return raw


def _describe_recent_candles(kline_data: dict, lang: str) -> dict:
    """
    Mô tả cấu trúc nến gần nhất trực tiếp từ OHLCV.

    Dùng để điền các trường model bỏ trống: thay vì hiển thị "—"/"__" (vô nghĩa
    với người dùng và với Decision Agent đọc lại báo cáo này), ta mô tả bằng số
    liệu THẬT tính từ chính dữ liệu model vừa nhìn.
    Trả về dict rỗng nếu dữ liệu không đủ.
    """
    try:
        opens  = [float(v) for v in kline_data.get("Open",  [])]
        highs  = [float(v) for v in kline_data.get("High",  [])]
        lows   = [float(v) for v in kline_data.get("Low",   [])]
        closes = [float(v) for v in kline_data.get("Close", [])]
        if not (opens and highs and lows and closes):
            return {}

        n      = min(len(opens), len(highs), len(lows), len(closes))
        window = min(20, n)
        c      = closes[:n][-window:]
        o      = opens[:n][-window:]
        h      = highs[:n][-window:]
        l      = lows[:n][-window:]

        first, last = c[0], c[-1]
        change_pct  = ((last - first) / first * 100) if first else 0.0
        support, resistance = min(l), max(h)

        # Nến có thân dài nhất trong cửa sổ — "nến quan trọng" theo nghĩa biến động.
        bodies   = [abs(c[i] - o[i]) for i in range(window)]
        idx      = bodies.index(max(bodies)) if bodies else 0
        bullish  = c[idx] >= o[idx]
        ago      = window - idx - 1

        is_en = lang == "en"
        if change_pct > 1.0:
            trend_word = "uptrend" if is_en else "xu hướng tăng"
            bias       = "Bullish" if is_en else "Tăng"
        elif change_pct < -1.0:
            trend_word = "downtrend" if is_en else "xu hướng giảm"
            bias       = "Bearish" if is_en else "Giảm"
        else:
            trend_word = "sideways range" if is_en else "vùng đi ngang"
            bias       = "Neutral" if is_en else "Trung tính"

        strong = abs(change_pct) >= 3.0
        mid    = abs(change_pct) >= 1.0
        if is_en:
            confidence = "High" if strong else ("Medium" if mid else "Low")
        else:
            confidence = "Cao" if strong else ("Trung bình" if mid else "Thấp")

        def fmt(v):
            return f"{v:,.0f}" if v >= 1000 else f"{round(v, 2):g}"

        if is_en:
            candle_word = "bullish" if bullish else "bearish"
            return {
                "Mô hình": f"{window}-candle {trend_word}",
                "Độ tin cậy": confidence,
                "Thiên lệch dự báo": bias,
                "Bằng chứng": (
                    f"Close moved {change_pct:+.1f}% over the last {window} candles, "
                    f"between {fmt(support)} and {fmt(resistance)}."
                ),
                "Nến quan trọng": (
                    f"Largest {candle_word} body {ago} candle(s) ago, "
                    f"range {fmt(l[idx])}–{fmt(h[idx])}."
                ),
                "Hàm ý giao dịch": (
                    f"Favour the {bias.lower()} side while "
                    f"{fmt(support)} support holds; invalidation below it."
                ),
            }

        candle_word = "tăng" if bullish else "giảm"
        return {
            "Mô hình": f"{trend_word.capitalize()} {window} nến",
            "Độ tin cậy": confidence,
            "Thiên lệch dự báo": bias,
            "Bằng chứng": (
                f"Giá đóng cửa thay đổi {change_pct:+.1f}% trong {window} nến gần nhất, "
                f"dao động {fmt(support)}–{fmt(resistance)}."
            ),
            "Nến quan trọng": (
                f"Nến {candle_word} thân dài nhất cách đây {ago} phiên, "
                f"biên độ {fmt(l[idx])}–{fmt(h[idx])}."
            ),
            "Hàm ý giao dịch": (
                f"Ưu tiên chiều {bias.lower()} khi hỗ trợ {fmt(support)} còn giữ; "
                f"huỷ kịch bản nếu thủng mức này."
            ),
        }
    except (TypeError, ValueError, ZeroDivisionError, IndexError):
        return {}


def _enforce_pattern_markdown_format(text: str, lang: str = "vi",
                                     kline_data: dict = None) -> str:
    """
    Đảm bảo output luôn có đúng 6 trường markdown chuẩn.
    Chỉ giữ lần xuất hiện ĐẦU TIÊN của mỗi trường, loại bỏ
    toàn bộ suy luận nội bộ, lặp lại, kịch bản phụ.

    Trường model bỏ trống được điền bằng mô tả tính từ `kline_data` thay vì
    placeholder "—"/"__".
    """
    if not text:
        return text

    text = _strip_thinking_blocks(text)
    computed = _describe_recent_candles(kline_data or {}, lang)

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

    if len(first_occurrences) < 1:
        # Không tìm thấy trường nào → dọn sạch rồi CẮT NGẮN, không đổ nguyên khối vào UI
        cleaned = re.sub(r'<[^>]*>', '', text)
        cleaned = _strip_thinking_blocks(cleaned)
        m = (_GARBAGE_RE_EN if lang == "en" else _GARBAGE_RE).search(cleaned)
        if m:
            cleaned = cleaned[:m.start()]
        cleaned = re.sub(r'\s*\n+\s*', ' ', cleaned)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
        if cleaned:
            cleaned = _truncate_at_sentence(cleaned, 240)

        labels = _FIELD_LABELS[lang if lang in _FIELD_LABELS else "vi"]

        # Không tách được trường nào → dùng mô tả tính từ OHLCV để báo cáo vẫn
        # có nội dung thật, thay vì khung "Unknown" + 5 dấu "—".
        values = dict(computed) if computed else {}
        if cleaned:
            # Văn bản còn dùng được đặt vào "Bằng chứng" — nơi hợp nghĩa nhất.
            values["Bằng chứng"] = _truncate_at_sentence(
                cleaned, _MAX_FIELD_CHARS["Bằng chứng"])

        if lang == "en":
            # EN: luôn xuất đủ 6 trường để khung UI ổn định.
            if not values.get("Mô hình"):
                values["Mô hình"] = "Unknown"
            return "\n\n".join(
                f"**{labels[field]}:** {values.get(field) or '—'}"
                for field in _PATTERN_FIELDS
            )

        if values:
            return "\n\n".join(
                f"**{labels[field]}:** {values[field]}"
                for field in _PATTERN_FIELDS if values.get(field)
            )

        if not cleaned:
            cleaned = "Phân tích không khả dụng."
        return f"**{labels['Mô hình']}:** {cleaned}"

    # Sắp xếp theo thứ tự xuất hiện trong văn bản
    first_occurrences.sort(key=lambda x: x["match_start"])

    # Trích xuất giá trị từng trường
    labels = _FIELD_LABELS[lang if lang in _FIELD_LABELS else "vi"]
    values = {}
    for i, item in enumerate(first_occurrences):
        val_start = item["value_start"]
        # Kết thúc = đầu trường tiếp theo, hoặc cuối text
        val_end = (
            first_occurrences[i + 1]["match_start"]
            if i + 1 < len(first_occurrences)
            else len(text)
        )

        value = _extract_field_value(text, val_start, val_end, lang=lang,
                                     label=item['label'])
        # Placeholder ("__", "—", "N/A", ".") coi như rỗng → điền dự phòng bên dưới.
        if not value or _PLACEHOLDER_VALUE_RE.match(value):
            value = ""

        values[item['label']] = value

    # Trường trống → lấy mô tả tính từ OHLCV. Áp dụng cho CẢ hai ngôn ngữ nên
    # không còn "__"/"—" lọt ra UI khi model bỏ sót trường.
    for field in _PATTERN_FIELDS:
        if not values.get(field) and computed.get(field):
            values[field] = computed[field]

    if lang == "en":
        # Luôn xuất đủ 6 trường theo thứ tự chuẩn để khung UI ổn định.
        if not values.get("Mô hình"):
            values["Mô hình"] = "Unknown"
        return "\n\n".join(
            f"**{labels[field]}:** {values.get(field) or '—'}"
            for field in _PATTERN_FIELDS
        )

    # VI: xuất theo thứ tự chuẩn, bỏ qua trường vẫn không có giá trị.
    return "\n\n".join(
        f"**{labels[field]}:** {values[field]}"
        for field in _PATTERN_FIELDS if values.get(field)
    )


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


def _text_fallback_analysis(tool_llm, kline_data: dict, time_frame: str,
                           lang: str = "vi") -> str:
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

    if lang == "en":
        prompt = (
            f"Analyse the following {time_frame} OHLCV data.\n"
            f"{ohlcv}\n\n"
            "Reply with EXACTLY the 6 lines in the format below. No extra explanation. "
            "NEVER use angle brackets < > or copy the placeholder wording.\n\n"
            "**Pattern:** Specific pattern name\n"
            "**Confidence:** High | Medium | Low\n"
            "**Directional bias:** Bullish | Bearish | Neutral\n"
            "**Evidence:** Description of the price structure\n"
            "**Key candles:** The most notable candle\n"
            "**Trading implication:** Concise action scenario"
        )
    else:
        prompt = (
            f"/no_think\n"
            f"Phân tích dữ liệu OHLCV khung {time_frame} sau.\n"
            f"{ohlcv}\n\n"
            "CHỈ trả lời đúng 6 dòng theo format dưới. KHÔNG giải thích thêm. TUYỆT ĐỐI KHÔNG dùng ngoặc nhọn < > hay copy lại chữ mẫu.\n\n"
            "**Mô hình:** Tên mô hình cụ thể\n"
            "**Độ tin cậy:** Cao | Trung bình | Thấp\n"
            "**Thiên lệch dự báo:** Tăng | Giảm | Trung tính\n"
            "**Bằng chứng:** Mô tả cấu trúc giá\n"
            "**Nến quan trọng:** Nến nổi bật nhất\n"
            "**Hàm ý giao dịch:** Kịch bản hành động ngắn gọn"
        )
    response = tool_llm.invoke([HumanMessage(content=prompt)])
    return response.content


def create_pattern_agent(tool_llm, graph_llm, toolkit):

    PATTERN_TEXT_VI = """
        Tham khảo: Vai đầu vai ngược, Đáy đôi, Nêm giảm/tăng, Tam giác, Cờ tăng/giảm, Hộp giá, Đảo chiều chữ V, Xu hướng rõ rệt.
    """

    PATTERN_TEXT_EN = """
        Reference patterns: Inverse head and shoulders, Double bottom, Falling/rising wedge, Triangle, Bull/bear flag, Rectangle range, V-reversal, Clear trend.
    """

    SYSTEM_PROMPT_VI = """/no_think
Bạn là AI chuyên phân tích mô hình giá (Price Action).

QUY TẮC BẮT BUỘC:
1. CHỈ trả lời đúng 6 trường bên dưới bằng TIẾNG VIỆT. Phải phân tích thật và điền giá trị cụ thể.
2. TUYỆT ĐỐI KHÔNG sử dụng các ngoặc nhọn `< >` hay lặp lại các chữ mẫu như `<tên>`, `<mô tả ngắn>`, `<liệt kê>`, `<kịch bản>`.
3. TUYỆT ĐỐI KHÔNG viết lời thoại tiếng Anh hay câu tự thoại meta (như "Input Data...", "I need to visually analyze...").
4. KHÔNG suy luận lan man, KHÔNG giải thích thừa, KHÔNG đưa kịch bản dự phòng.
5. Mỗi trường đúng MỘT dòng ngắn gọn.

FORMAT CHUẨN:
**Mô hình:** Tên mô hình giá cụ thể (ví dụ: Xu hướng tăng tích luỹ / Đáy đôi / Tam giác)
**Độ tin cậy:** Cao hoặc Trung bình hoặc Thấp
**Thiên lệch dự báo:** Tăng hoặc Giảm hoặc Trung tính
**Bằng chứng:** Mô tả ngắn cấu trúc các nến gần nhất
**Nến quan trọng:** Các nến biến động mạnh nổi bật
**Hàm ý giao dịch:** Kịch bản hành động cụ thể"""

    # Không dùng `/no_think`: đó là quy ước template Ollama/Qwen, qua Groq API nó
    # chỉ là chữ vô nghĩa. Việc tắt suy luận xử lý ở `trading_graph._create_llm`
    # bằng `reasoning_format="hidden"`.
    SYSTEM_PROMPT_EN = """You are an AI specialised in price-action pattern analysis.

MANDATORY RULES:
1. Output EXACTLY the 6 fields below, in ENGLISH, and nothing else.
2. Start your reply directly with "**Pattern:**". No preamble, no greeting, no closing remark.
3. NEVER narrate your reasoning ("Okay", "Let me", "Looking at the chart", "I need to...").
4. NEVER use angle brackets `< >` or repeat placeholder wording such as `<name>`, `<scenario>`.
5. Each field is ONE short line. Hard limits: Pattern <= 8 words; Confidence and
   Directional bias are a SINGLE word; Evidence, Key candles and Trading implication
   <= 25 words each.
6. State conclusions only — no hedging, no alternative scenarios, no repeated fields.

REQUIRED FORMAT:
**Pattern:** Specific price pattern name (e.g. Accumulating uptrend / Double bottom / Triangle)
**Confidence:** High or Medium or Low
**Directional bias:** Bullish or Bearish or Neutral
**Evidence:** Short description of the most recent candle structure
**Key candles:** The most notable high-volatility candles
**Trading implication:** Concrete action scenario"""

    USER_PROMPT_VI = """/no_think
Phân tích biểu đồ nến {time_frame}. {PATTERN_TEXT}

Hãy phân tích biểu đồ và trả về ĐÚNG 6 trường sau (mỗi trường 1 dòng, điền phân tích THẬT, KHÔNG dùng ngoặc nhọn `< >`, KHÔNG giải thích thêm):

**Mô hình:** Tên mô hình tiếng Việt cụ thể
**Độ tin cậy:** Cao | Trung bình | Thấp
**Thiên lệch dự báo:** Tăng | Giảm | Trung tính
**Bằng chứng:** Cấu trúc giá cụ thể (đỉnh, đáy, phá vỡ...)
**Nến quan trọng:** Nến nổi bật nhất
**Hàm ý giao dịch:** Hành động giao dịch ngắn gọn

VÍ DỤ OUTPUT CHUẨN:
**Mô hình:** Vai đầu vai
**Độ tin cậy:** Cao
**Thiên lệch dự báo:** Giảm
**Bằng chứng:** Ba đỉnh, đỉnh giữa cao nhất, phá vỡ đường cổ tại 70
**Nến quan trọng:** Nến đỏ phá vỡ hỗ trợ 70 với thân dài
**Hàm ý giao dịch:** Bán khi phá vỡ đường cổ, mục tiêu 63, ngừng lỗ trên 74"""

    USER_PROMPT_EN = """Analyse this {time_frame} candlestick chart. {PATTERN_TEXT}

Return EXACTLY the 6 fields below and nothing else. Begin directly with "**Pattern:**".
No preamble, no reasoning, no closing summary. Keep every field on ONE short line
(Evidence / Key candles / Trading implication: max 25 words each).

**Pattern:** Specific pattern name in English
**Confidence:** High | Medium | Low
**Directional bias:** Bullish | Bearish | Neutral
**Evidence:** Concrete price structure (peaks, troughs, breakouts...)
**Key candles:** The most notable candle
**Trading implication:** Concise trading action

EXAMPLE OF A CORRECT OUTPUT:
**Pattern:** Head and shoulders
**Confidence:** High
**Directional bias:** Bearish
**Evidence:** Three peaks, middle peak highest, neckline broken at 70
**Key candles:** Long-bodied red candle breaking support at 70
**Trading implication:** Sell on the neckline break, target 63, stop above 74"""

    def pattern_agent_node(state):
        time_frame = state["time_frame"]
        kline_data = state["kline_data"]

        from utils.i18n import lang_of, get_horizon, localize_timeframe
        lang    = lang_of(state)
        horizon = get_horizon(time_frame, lang)
        h_desc  = horizon["horizon_desc"]

        tf_display   = localize_timeframe(time_frame, lang)
        is_en        = lang == "en"
        SYSTEM_PROMPT = SYSTEM_PROMPT_EN if is_en else SYSTEM_PROMPT_VI
        USER_PROMPT   = USER_PROMPT_EN   if is_en else USER_PROMPT_VI
        PATTERN_TEXT  = PATTERN_TEXT_EN  if is_en else PATTERN_TEXT_VI

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
                    "text": USER_PROMPT.format(time_frame=tf_display, PATTERN_TEXT=PATTERN_TEXT, h_desc=h_desc),
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
                if _has_usable_content(raw_output):
                    print("[PatternAgent] Phân tích thị giác hoàn thành.")
                else:
                    # Model trả rỗng / chỉ có <think> bị cắt → coi như thất bại
                    # để rơi xuống dự phòng văn bản, thay vì xuất khung toàn "—".
                    print("[PatternAgent] Thị giác trả về nội dung rỗng — dùng dự phòng.")
                    raw_output = None
            except Exception as e:
                err_str = str(e).lower()
                if "at least one message" in err_str or "system" in err_str:
                    try:
                        response = _invoke_with_retry(graph_llm.invoke, [human_msg])
                        raw_output = response.content
                        if _has_usable_content(raw_output):
                            print("[PatternAgent] Phân tích thị giác hoàn thành (thử lại không system).")
                        else:
                            print("[PatternAgent] Thị giác (không system) rỗng — dùng dự phòng.")
                            raw_output = None
                    except Exception as e2:
                        print(f"[PatternAgent] Thị giác thất bại: {e2}")
                else:
                    print(f"[PatternAgent] Lỗi model thị giác: {e}")

        # Thị giác không cho ra BÁO CÁO (thường do model mải suy luận rồi hết
        # token) → thử lại đúng một lần với chỉ thị cộc lốc, vẫn dùng ảnh. Rẻ hơn
        # nhiều so với bỏ hẳn thị giác mà rơi xuống dự phòng chỉ đọc OHLCV.
        if not raw_output and pattern_image_b64:
            try:
                terse = _TERSE_RETRY_EN if is_en else _TERSE_RETRY_VI
                retry_msg = HumanMessage(content=[
                    {"type": "text", "text": terse},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{pattern_image_b64}"},
                    },
                ])
                response = _invoke_with_retry(graph_llm.invoke, [retry_msg], retries=1)
                if _has_usable_content(response.content):
                    raw_output = response.content
                    print("[PatternAgent] Thị giác thành công ở lần thử cộc lốc.")
                else:
                    print("[PatternAgent] Lần thử cộc lốc vẫn rỗng — dùng dự phòng.")
            except Exception as e:
                print(f"[PatternAgent] Lần thử cộc lốc thất bại: {e}")

        if not raw_output:
            try:
                fallback = _text_fallback_analysis(tool_llm, kline_data, time_frame,
                                                   lang=lang)
                if _has_usable_content(fallback):
                    raw_output = fallback
                    print("[PatternAgent] Dự phòng văn bản hoàn thành.")
                else:
                    # Dự phòng cũng rỗng → để rơi xuống khung lỗi tường minh bên
                    # dưới, thay vì xuất báo cáo trắng không rõ nguyên nhân.
                    raise ValueError("dự phòng văn bản trả về nội dung rỗng")
            except Exception as e:
                print(f"[PatternAgent] Dự phòng văn bản thất bại: {e}")
                if is_en:
                    raw_output = (
                        "**Pattern:** Unknown\n"
                        "**Confidence:** Low\n"
                        "**Directional bias:** Neutral\n"
                        "**Evidence:** All analysis models failed\n"
                        "**Key candles:** —\n"
                        "**Trading implication:** —"
                    )
                else:
                    raw_output = (
                        "**Mô hình:** Không xác định\n"
                        "**Độ tin cậy:** Thấp\n"
                        "**Thiên lệch dự báo:** Trung tính\n"
                        "**Bằng chứng:** Lỗi toàn tập không thể chạy model\n"
                        "**Nến quan trọng:** —\n"
                        "**Hàm ý giao dịch:** —"
                    )

        # ── ÁP DỤNG BỘ PARSER VĂN BẢN ────────────────────────────────
        # Truyền `kline_data` để trường model bỏ trống được điền bằng mô tả thật
        # tính từ OHLCV thay vì placeholder "—"/"__".
        report_content = _enforce_pattern_markdown_format(raw_output, lang=lang,
                                                          kline_data=kline_data)
        print(f"[PatternAgent] Hoàn thành ({len(report_content)} ký tự).")

        return {
            "messages":      state.get("messages", []),
            "pattern_report": report_content,
        }

    return pattern_agent_node