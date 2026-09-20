"""
Trung tâm i18n phía backend / Backend-side i18n catalogue.

Toàn bộ chuỗi hiển thị cho người dùng (thông báo lỗi Flask, khung báo cáo của
các tác tử, nhãn UI trong Jinja template, chuỗi động trong JavaScript, và chỉ
thị ngôn ngữ cho LLM) được tập trung tại đây. Thêm ngôn ngữ mới = thêm một khoá
vào `SUPPORTED_LANGS` và một nhánh trong các từ điển bên dưới - không cần sửa
business logic.

All user-facing strings live here so a new language only requires adding one
more branch to the dictionaries below.
"""

from typing import Any, Dict

DEFAULT_LANG = "vi"
SUPPORTED_LANGS = ("vi", "en")


def normalize_lang(lang: Any) -> str:
    """Chuẩn hoá giá trị ngôn ngữ bất kỳ về 'vi' | 'en' (mặc định 'vi')."""
    if not lang:
        return DEFAULT_LANG
    code = str(lang).strip().lower().replace("_", "-").split("-")[0]
    return code if code in SUPPORTED_LANGS else DEFAULT_LANG


def lang_of(state: Any) -> str:
    """Lấy ngôn ngữ từ LangGraph state (an toàn với state thiếu khoá)."""
    try:
        return normalize_lang(state.get("language"))
    except AttributeError:
        return DEFAULT_LANG


# ── Catalogue chuỗi hiển thị / Display-string catalogue ───────────────────────

MESSAGES: Dict[str, Dict[str, str]] = {
    "vi": {},
    "en": {},
}

MESSAGES["vi"] = {
    # ── Tên hệ thống ──────────────────────────────────────────────────────────
    "system_name":              "Hệ thống đa tác tử dự đoán chứng khoán cho thị trường Việt Nam",
    "system_name_short":        "Hệ thống AI đầu tư chứng khoán",
    "system_subtitle":          "Phân tích chứng khoán bằng AI đa tác tử",

    # ── Chung ─────────────────────────────────────────────────────────────────
    "language":                 "Ngôn ngữ",
    "lang_vi":                  "Tiếng Việt",
    "lang_en":                  "English",
    "home":                     "Trang chủ",
    "back_home":                "Trang chính",
    "no_data":                  "Không có dữ liệu",
    "loading":                  "Đang tải...",
    "candles":                  "nến",
    "articles":                 "bài",
    "minutes":                  "phút",
    "agents_count":             "5 tác tử",
    "locale_tag":               "vi-VN",

    # ── Tiêu đề trang ─────────────────────────────────────────────────────────
    "page_title_home":          "Hệ thống AI đầu tư chứng khoán - Hệ thống đa tác tử dự đoán chứng khoán cho thị trường Việt Nam",
    "page_title_output":        "Hệ thống AI đầu tư chứng khoán - Kết quả phân tích",
    "page_title_backtest":      "Hệ thống AI đầu tư chứng khoán - Kiểm định lại",

    # ── Hero ──────────────────────────────────────────────────────────────────
    "hero_desc":                "Hệ thống đa tác tử dự đoán chứng khoán cho thị trường Việt Nam.",
    "hero_desc2":               "Sử dụng <strong>Groq API</strong> (miễn phí) - dữ liệu thời gian thực từ <strong>vnstock (VCI / MSN)</strong>.",
    "hero_tag_text_agents":     "Indicator &amp; Sentiment &amp; Alpha &amp; Decision",
    "hero_tag_vision_agents":   "Pattern &amp; Trend",
    "hero_tag_sentiment":       "ViSoBERT · Sentiment",
    "hero_tag_realtime":        "Thời gian thực · vnstock",
    "hero_btn":                 "Bắt đầu phân tích",

    # ── Lớp phủ đang tải ──────────────────────────────────────────────────────
    "loading_title":            "Đang phân tích...",
    "loading_sub":              "Hệ thống đa tác tử đang xử lý dữ liệu thị trường",
    "load_step1":               "Lấy dữ liệu thời gian thực",
    "load_step1_tf":            "Lấy dữ liệu {tf}",
    "load_step2":               "Tác tử Chỉ báo - Tính chỉ báo kỹ thuật",
    "load_step3":               "Tác tử Alpha - Phân tích tâm lý &amp; tạo nhân tố alpha",
    "load_step4":               "Tác tử Mô hình nến - Nhận dạng mô hình nến",
    "load_step5":               "Tác tử Xu hướng - Phân tích xu hướng",
    "load_step6":               "Tác tử Quyết định - Đưa ra quyết định",

    # ── Thanh trạng thái ──────────────────────────────────────────────────────
    "st_checking_groq":         "Đang kiểm tra Groq...",
    "st_groq_ready":            "Groq sẵn sàng",
    "st_groq_unconfigured":     "Groq chưa cấu hình",
    "st_groq_check_failed":     "Không kiểm tra được Groq",
    "st_checking_vnstock":      "Đang kiểm tra vnstock...",
    "st_rt_ready":              "Thời gian thực sẵn sàng",
    "st_vnstock_missing":       "vnstock chưa cài",
    "st_connect_failed":        "Kết nối thất bại",
    "st_status_check_failed":   "Kiểm tra trạng thái thất bại",
    "st_loading_symbols":       "Đang tải mã...",
    "st_symbol_count":          "{n} mã cổ phiếu (HOSE / HNX / UPCOM)",
    "st_updated":               "Cập nhật:",
    "st_refresh":               "Làm mới",

    # ── Biểu mẫu phân tích ────────────────────────────────────────────────────
    "form_title":               "Cấu hình phân tích",
    "api_notice_title":         "Cần Groq API Key!",
    "api_notice_body":          "Lấy key miễn phí tại <a href=\"https://console.groq.com/keys\" target=\"_blank\">console.groq.com/keys</a> rồi nhập vào phần <strong>Cài đặt Groq API</strong> bên dưới.",
    "select_stock":             "Chọn mã cổ phiếu",
    "search_placeholder":       "Tìm: VNM, VIC, ACB, FPT...",
    "loading_symbol_list":      "Đang tải danh sách mã...",
    "loading_from_vnstock":     "Đang tải từ vnstock...",
    "err_load_symbol_list":     "Không tải được danh sách mã.",
    "no_symbol_found":          "Không tìm thấy mã nào",
    "selected":                 "Đã chọn:",
    "stock_info":               "Thông tin mã",
    "timeframe":                "Khung thời gian",
    "tf_note":                  "Dữ liệu thời gian thực từ vnstock · Số nến tối ưu cho từng khung.",
    "selected_stock_detail":    "Chi tiết mã đã chọn",
    "click_symbol_hint":        "Nhấn vào mã để xem thông tin",
    "company":                  "Công ty",
    "symbol":                   "Mã",
    "industry":                 "Ngành",
    "live":                     "Trực tiếp",
    "realtime":                 "Thời gian thực",
    "fetch_on_run_hint":        "Dữ liệu sẽ được lấy trực tiếp khi chạy phân tích.",
    "err_load_stock_info":      "Không tải được thông tin",
    "run_analysis":             "Chạy phân tích",
    "analyzing":                "Đang phân tích...",

    # ── Nhãn khung thời gian ──────────────────────────────────────────────────
    "tf_5m":                    "5 Phút",
    "tf_15m":                   "15 Phút",
    "tf_30m":                   "30 Phút",
    "tf_1h":                    "1 Giờ",
    "tf_1d":                    "1 Ngày",
    "tf_1w":                    "1 Tuần",
    "tf_1mo":                   "1 Tháng",
    "tf_desc_5m":               "Lướt sóng, 78 nến gần nhất",
    "tf_desc_15m":              "Swing ngắn, 60 nến gần nhất",
    "tf_desc_30m":              "Swing trung, 50 nến gần nhất",
    "tf_desc_1h":               "Swing ngày, 45 nến gần nhất",
    "tf_desc_1d":               "Phân tích ngày, 45 nến gần nhất",
    "tf_desc_1w":               "Phân tích tuần, 52 nến gần nhất",
    "tf_desc_1mo":              "Phân tích tháng, 36 nến gần nhất",
    "tf_recent_candles":        "{n} nến gần nhất",

    # ── Cài đặt Groq ──────────────────────────────────────────────────────────
    "groq_settings":            "Cài đặt Groq API",
    "api_key_label":            "Groq API Key",
    "free_tag":                 "Miễn phí",
    "toggle_key":               "Hiện/ẩn key",
    "get_key_at":               "Lấy key tại",
    "save_api_key":             "Lưu API Key &amp; Kết nối",
    "text_agent_model":         "Model tác tử văn bản",
    "vision_agent_model":       "Model tác tử thị giác",
    "text_agent_roles":         "Chỉ báo · Tâm lý · Alpha · Quyết định",
    "vision_agent_roles":       "Mô hình nến · Xu hướng",
    "key_enter_prompt":         "Vui lòng nhập API key",
    "key_bad_format":           "Key không đúng định dạng (phải bắt đầu bằng gsk_)",
    "key_connecting":           "Đang kết nối Groq...",
    "key_ok":                   "API key hợp lệ - Groq đã kết nối!",
    "key_invalid":              "Key không hợp lệ",
    "err_connection_prefix":    "Lỗi kết nối: ",
    "models_saved":             "Đã lưu: văn bản={text}, thị giác={vision}",

    # ── vnstock ───────────────────────────────────────────────────────────────
    "vnstock_panel":            "vnstock - Dữ liệu thời gian thực",
    "vnstock_library":          "Thư viện vnstock",
    "vnstock_installed":        "Đã cài đặt ✓",
    "data_connection":          "Kết nối dữ liệu",
    "data_sources":             "Nguồn dữ liệu",
    "cache":                    "Bộ nhớ đệm",
    "cache_items":              "{n} mục · TTL {ttl}s",
    "clear_cache":              "Xóa bộ nhớ đệm",
    "recheck":                  "Kiểm tra lại",
    "cache_cleared":            "Bộ nhớ đệm đã được xóa ✓",
    "err_clear_cache":          "Xóa bộ nhớ đệm thất bại: ",

    # ── Thông báo phía client ─────────────────────────────────────────────────
    "warn_select_stock":        "Vui lòng chọn mã cổ phiếu trước khi phân tích.",
    "warn_save_key":            "Vui lòng nhập Groq API key và nhấn \"Lưu API Key\" trước.",
    "err_no_job_id":            "Lỗi server: không có job_id.",
    "err_no_flask":             "Không kết nối được server Flask.",
    "err_timeout":              "Phân tích quá thời gian. Vui lòng thử lại.",
    "err_poll":                 "Lỗi poll: ",

    # ── Trang kết quả ─────────────────────────────────────────────────────────
    "header_sub_output":        "Kết quả phân tích kỹ thuật đa tác tử",
    "new_analysis":             "Phân tích mới",
    "analyze_another":          "Phân tích mã khác",
    "stat_candles":             "Số nến phân tích",
    "stat_timeframe":           "Khung thời gian",
    "stat_symbol":              "Mã cổ phiếu",
    "stat_decision":            "Quyết định",
    "final_decision":           "Quyết định giao dịch cuối cùng",
    "rr_ratio":                 "Tỷ lệ R:R:",
    "confidence":               "Độ tin cậy",
    "justification":            "Cơ sở quyết định",

    "agent_indicator":          "Tác tử Chỉ báo",
    "agent_alpha":              "Tác tử Alpha",
    "agent_pattern":            "Tác tử Mô hình nến",
    "agent_trend":              "Tác tử Xu hướng",
    "agent_sub_indicator":      "MACD · RSI · Stochastic · Williams %R · ROC",
    "agent_sub_alpha":          "Tâm lý CafeF · ViSoBERT",
    "agent_sub_pattern":        "Phân tích thị giác",
    "agent_sub_trend":          "Phân tích thị giác · Hỗ trợ &amp; Kháng cự",
    "no_indicator_data":        "Không có dữ liệu chỉ báo",
    "no_alpha_data":            "Không có dữ liệu nhân tố alpha",

    # Sentiment
    "sentiment_data_title":     "Dữ liệu Tâm lý (CafeF · ViSoBERT)",
    "sent_positive":            "Tích cực",
    "sent_negative":            "Tiêu cực",
    "sent_neutral":             "Trung tính",
    "sent_positive_up":         "TÍCH CỰC",
    "sent_negative_up":         "TIÊU CỰC",
    "sent_neutral_up":          "TRUNG TÍNH",
    "sent_pos_short":           "TC",
    "sent_neg_short":           "TiC",
    "sent_neu_short":           "Trung",
    "article_distribution":     "Phân bổ bài báo - {n} bài",
    "related_companies":        "Công ty liên quan (top {n})",
    "norm_title":               "Biến Tâm lý đã chuẩn hóa - Đầu vào cho Alpha",
    "norm_reliable":            "Tin cậy",
    "norm_unreliable":          "Thấp - ít bài",
    "nv_zscore_formula":        "(avg − μ_lô) / (σ_lô + ε)",
    "nv_zscore_desc":           "Chuẩn hóa điểm trung bình theo độ lệch chuẩn lô bài.<br><strong>≈ 0</strong> = tin tức bình thường (không phải trung tính).<br><strong>&gt; +1.5</strong> = tin bất thường tích cực.<br><strong>&lt; −1.5</strong> = tin bất thường tiêu cực.",
    "nv_zscore_usage":          "Dùng phát hiện tin bất thường:",
    "nv_zscore_code":           "sign(SENT_ZSCORE) × tanh(|SENT_ZSCORE|) × kỹ_thuật",
    "nv_rel_formula":           "avg_mã − avg_ngành",
    "nv_rel_desc":              "So sánh tương đối với tâm lý trung bình ngành.<br><strong>&gt; 0</strong> = cổ phiếu vượt trội ngành về tin tức.<br><strong>&lt; 0</strong> = cổ phiếu kém hơn ngành.<br>Thiên lệch toàn thị trường tự triệt tiêu qua phép trừ.",
    "nv_rel_usage":             "Dùng trong chiến lược mua-bán khống:",
    "related_zscore_title":     "SENT_ZSCORE Công ty liên quan - Alpha liên ngành",
    "related_zscore_note":      "Ký hiệu trong công thức alpha: <code class=\"zc-code\">ZSCORE_[MÃ]</code> - ví dụ: <code class=\"zc-code\">ZSCORE_VHM</code>, <code class=\"zc-code\">ZSCORE_ACB</code>. Dùng để phát hiện phân kỳ ngành.",
    "alpha_factors":            "Nhân tố Alpha",
    "no_sentiment_note":        "Không có dữ liệu tâm lý - alpha được tạo thuần kỹ thuật.",
    "alpha_consensus":          "Đồng thuận Alpha",
    "consensus_buy":            "▲ MUA",
    "consensus_sell":           "▼ BÁN",
    "consensus_mixed":          "◆ HỖN HỢP",
    "alpha_summary":            "TỔNG HỢP",
    "alpha_expert_note":        "Nhận định của chuyên gia Alpha",

    # ── Báo cáo alpha sinh bởi Python (alpha_agent._build_alpha_report) ───────
    "ar_title":                 "5 Alpha Factor",
    "ar_th_alpha":              "Alpha",
    "ar_th_type":               "Loại",
    "ar_th_value":              "Giá trị",
    "ar_th_signal":             "Tín hiệu",
    "ar_th_horizon":            "Horizon",
    "ar_sig_up":                "▲ TĂNG",
    "ar_sig_down":              "▼ GIẢM",
    "ar_sig_neutral":           "◆ Trung tính",
    "ar_sentiment":             "Tâm lý",
    "ar_reliable":              "✅ Đáng tin",
    "ar_few_articles":          "⚠️ Ít bài",
    "ar_volume":                "Khối lượng",
    "ar_vol_real":              "thực",
    "ar_vol_proxy":             "proxy range",
    "ar_lbl_type":              "Loại",
    "ar_lbl_horizon":           "Horizon",
    "ar_full_formula":          "Công thức đầy đủ",
    "ar_calc_steps":            "Các bước tính toán",
    "ar_interpretation":        "Diễn giải",
    "ar_final_value":           "Kết quả cuối cùng",
    "ar_signal":                "Tín hiệu",

    # ── Nhãn alpha mặc định (fallback 5 alpha hardcode) ──────────────────────
    "ar_type_fallback":         "Quantitative Alpha",
    "ar_flipped_note":          "[Đảo chiều tín hiệu do tương quan lịch sử âm (IC < 0)]",
    "ar_a1_type":               "Cú hích T+1 (Tiếp diễn)",
    "ar_a1_interp":             "ROC(1) hiệu chỉnh={roc:+.2f}, Đột biến Vol={vol:.2f}x. {verdict}.",
    "ar_a1_up":                 "Xung lực tăng mạnh có thể kéo dài sang nến T+1",
    "ar_a1_down":               "Áp lực bán mạnh dự báo nến T+1 giảm",
    "ar_a1_neutral":            "Dòng tiền không rõ ràng",
    "ar_a2_name":               "Sentiment-Flow (SFA) / Proxy",
    "ar_a2_type":               "Cú hích T+1 (Tiếp diễn / Phân kỳ)",
    "ar_a2_formula":            "Tanh( Z_Sent×0.5 + ROC_adj×0.5 ) hoặc Proxy MACD_Hist",
    "ar_a2_logic_reliable":     "Tin cậy. Z_Sent={z:+.2f}, ROC_adj={roc:+.2f}.",
    "ar_a2_logic_proxy":        "Backtest/Sentiment yếu. Dùng Proxy MACD_Hist={macd:+.4f} (Z~{zm:+.2f}) và ROC_adj={roc:+.2f}.",
    "ar_a2_interp":             "{logic} → Cân bằng lực lượng cho T+1: Value={value:+.4f}.",
    "ar_a3_type":               "Đảo chiều T+1 (Mean-Reversion)",
    "ar_a3_interp":             "Z-Score lệch pha SMA(5)={z:+.2f}. {verdict}",
    "ar_a3_up":                 "Giá bị đẩy rớt xa xuống, mồi thanh khoản để bật lại T+1",
    "ar_a3_down":               "Giá hưng phấn rướn quá khỏi SMA5, rủi ro rũ nền T+1",
    "ar_a3_neutral":            "Dao động bám quanh SMA5, không có khoảng trống.",
    "ar_a4_type":               "Bùng nổ dải Band T+1",
    "ar_a4_interp":             "BB %B={b:.2f}, Z-Score(Vol, 5)={z:+.2f}. {verdict}",
    "ar_a4_up":                 "Xác nhận bứt phá biên trên cùng Vol",
    "ar_a4_down":               "Áp lực đè biên dưới cùng Vol",
    "ar_a4_neutral":            "Chưa có sự ép biên rõ ràng",
    "ar_a5_type":               "Nén xả nội phiên T+1",
    "ar_a5_formula":            "Tanh( ROC_adj × Vị_trí_đóng_nến × 3.0 )",
    "ar_a5_interp":             "Động lực qua ngày ROC_adj={roc:+.2f}, Vị trí đóng nến (Pos)={pos:+.2f}. {verdict}",
    "ar_a5_up":                 "Sự ủng hộ giá đóng cửa trên cao",
    "ar_a5_down":               "Râu nến ngược hướng giá, đuối dòng tiền",
    "ar_a5_neutral":            "Thân nến trung bình",

    # Biểu đồ
    "pattern_analysis":         "Phân tích mô hình",
    "candlestick_chart":        "Biểu đồ nến Nhật",
    "trend_analysis":           "Phân tích xu hướng",
    "trend_chart":              "Biểu đồ xu hướng",
    "chart_unavailable":        "Biểu đồ không có sẵn",
    "support":                  "Hỗ trợ",
    "resistance":               "Kháng cự",

    # Nhãn báo cáo xu hướng (dùng để chuẩn hoá markdown phía client)
    "trend_lbl_direction":      "Hướng xu hướng",
    "trend_lbl_support":        "Mức hỗ trợ",
    "trend_lbl_resistance":     "Mức kháng cự",
    "trend_lbl_slope":          "Độ dốc đường xu hướng",
    "trend_lbl_price_vs_sup":   "Giá so với hỗ trợ",
    "trend_lbl_detail":         "Phân tích chi tiết",
    "trend_lbl_forecast":       "Dự đoán",
    "trend_lbl_confidence":     "Độ tin cậy",

    # ── Trang kiểm định lại ───────────────────────────────────────────────────
    "bt_brand":                 "Hệ thống AI đầu tư chứng khoán - Kiểm định lại",
    "bt_sub":                   "Kiểm định trượt tiến · So sánh Hệ đầy đủ với Hệ không Alpha",
    "bt_config":                "Cấu hình kiểm định",
    "bt_config_sub":            "Cửa sổ trượt tiến",
    "bt_symbol":                "Mã cổ phiếu",
    "bt_symbol_placeholder":    "VNM, ACB, FPT...",
    "bt_n_tests":               "Số điểm kiểm định",
    "bt_n_tests_hint":          "Mỗi lần ≈ 3–4 phút",
    "bt_window":                "Kích thước cửa sổ",
    "bt_window_hint":           "Số nến mỗi phân tích",
    "bt_step":                  "Bước nhảy giữa các lần",
    "bt_step_hint":             "Số nến trượt mỗi lần (≥1)",
    "bt_start":                 "Bắt đầu kiểm định",
    "bt_stop":                  "Dừng kiểm định",
    "bt_warning":               "Mỗi điểm kiểm định chạy <strong>2 lần LLM</strong> (Đầy đủ + Không Alpha) với độ trễ tránh giới hạn tần suất Groq. 10 lần ≈ <strong>25–45 phút</strong>. Không tắt tab trong quá trình chạy.",
    "bt_status":                "Trạng thái",
    "bt_not_started":           "Chưa chạy",
    "bt_progress":              "Tiến độ",
    "bt_step_data":             "Tải dữ liệu lịch sử",
    "bt_step_full":             "Hệ đầy đủ (có Alpha)",
    "bt_step_no":               "Hệ không Alpha",
    "bt_step_save":             "Lưu kết quả",
    "bt_full_system":           "Hệ đầy đủ",
    "bt_no_alpha":              "Không Alpha",
    "bt_waiting":               "Chờ kết quả...",
    "bt_calculating":           "Đang tính...",
    "bt_waiting_data":          "Đang chờ dữ liệu...",
    "bt_alpha_lift":            "Mức cải thiện nhờ Alpha (Độ chính xác)",
    "bt_acc_gain":              "Độ chính xác tăng thêm",
    "bt_pnl_full":              "Lợi nhuận Đầy đủ (α)",
    "bt_pnl_no":                "Lợi nhuận Không α",
    "bt_pnl_sub":               "Lãi/lỗ mô phỏng (lũy kế)",
    "bt_chart_pnl":             "Mô phỏng lợi nhuận (Lãi/lỗ %)",
    "bt_chart_acc":             "Độ chính xác lũy tiến",
    "bt_chart_x":               "Lần kiểm định #",
    "bt_chart_y_pnl":           "Lợi nhuận lũy kế (%)",
    "bt_ds_full_pnl":           "Đầy đủ (α)",
    "bt_ds_no_pnl":             "Không α",
    "bt_ds_full_correct":       "Đầy đủ đúng",
    "bt_ds_no_correct":         "Không α đúng",
    "bt_compare":               "So sánh chi tiết",
    "bt_compare_sub":           "Tỷ lệ thắng theo chiều giao dịch",
    "bt_no_data":               "Chưa có dữ liệu",
    "bt_timeline":              "Chi tiết từng điểm kiểm định",
    "bt_th_window":             "Cửa sổ",
    "bt_th_actual":             "Thực tế",
    "bt_th_full_pred":          "Dự đoán Đầy đủ",
    "bt_th_full_ok":            "Đầy đủ ✓",
    "bt_th_no_pred":            "Dự đoán Không α",
    "bt_th_no_ok":              "Không α ✓",
    "bt_th_alpha_adds":         "Alpha có ích?",
    "bt_waiting_first":         "Chờ lần kiểm định đầu tiên...",
    "bt_enter_symbol":          "Nhập mã cổ phiếu!",
    "bt_running":               "Đang chạy - {symbol} | {n} lần",
    "bt_stopped":               "Đã dừng",
    "bt_done":                  "✅ Kiểm định hoàn thành!",
    "bt_test_points":           "{n} điểm kiểm định",
    "bt_valid_correct":         "{valid} lần hợp lệ · {correct} đúng",
    "bt_lift_strong":           "🟢 Alpha cải thiện đáng kể",
    "bt_lift_slight":           "🟡 Alpha cải thiện nhẹ",
    "bt_lift_none":             "⚪ Không đổi",
    "bt_lift_neg":              "🔴 Alpha chưa giúp ích",
    "bt_eta":                   "Dự kiến còn ~{n} phút",
    "bt_finished":              "Hoàn thành",
    "bt_test":                  "Lần",
    "bt_actual":                "Thực tế",
    "bt_acc_total":             "Độ chính xác tổng",
    "bt_pnl_sim":               "Lợi nhuận mô phỏng (%)",
    "bt_win_long":              "Tỷ lệ thắng MUA",
    "bt_win_short":             "Tỷ lệ thắng BÁN",
    "bt_alpha_helps":           "🟢 Có ích",
    "bt_alpha_hurts":           "🔴 Có hại",
    "bt_both_right":            "⚪ Cả 2 đúng",
    "bt_both_wrong":            "⚫ Cả 2 sai",

    # ── Thông báo lỗi backend ─────────────────────────────────────────────────
    "err_api_key_missing":      "❌ Groq API key chưa được cấu hình. Vui lòng nhập API key trong phần cài đặt.",
    "err_api_key_missing_short": "❌ Groq API key chưa được cấu hình.",
    "err_api_key_not_set":      "API key chưa được cấu hình",
    "err_api_key_invalid":      "❌ Groq API key không hợp lệ. Vui lòng kiểm tra lại key tại console.groq.com",
    "err_api_key_empty":        "API key không được để trống.",
    "err_api_key_format":       "Key sai định dạng (phải bắt đầu bằng gsk_)",
    "err_api_key_first":        "Vui lòng cấu hình API key trước.",
    "err_rate_limit":           "⏳ Groq đã đạt giới hạn tần suất - vui lòng chờ vài giây rồi thử lại.",
    "err_model_not_found":      "❌ Model không tồn tại. Kiểm tra tên model trong cài đặt.",
    "err_connection":           "🌐 Không kết nối được Groq API. Kiểm tra kết nối internet.",
    "err_analysis":             "❌ Lỗi phân tích: {detail}",
    "err_missing_columns":      "Thiếu cột dữ liệu. Cột hiện có: {columns}",
    "err_select_stock":         "Vui lòng chọn mã cổ phiếu.",
    "err_enter_stock":          "Vui lòng nhập mã cổ phiếu.",
    "err_vnstock_missing":      "vnstock chưa cài. Chạy: pip install vnstock",
    "err_no_data_for":          "Không có dữ liệu cho {symbol}.",
    "err_job_not_found":        "Tác vụ không tồn tại.",
    "err_not_finished":         "Chưa hoàn thành.",
    "err_unknown":              "Lỗi không xác định",
    "err_models_both":          "Vui lòng nhập cả hai tên model.",
    "err_update_failed":        "Cập nhật thất bại",
    "no_results":               "Không có kết quả.",
}

MESSAGES["en"] = {
    # ── System names ──────────────────────────────────────────────────────────
    "system_name":              "Multi-Agent Stock Prediction System for the Vietnamese Market",
    "system_name_short":        "AI Stock Investment System",
    "system_subtitle":          "AI Multi-Agent Stock Analysis",

    # ── Common ────────────────────────────────────────────────────────────────
    "language":                 "Language",
    "lang_vi":                  "Tiếng Việt",
    "lang_en":                  "English",
    "home":                     "Home",
    "back_home":                "Main page",
    "no_data":                  "No data",
    "loading":                  "Loading...",
    "candles":                  "candles",
    "articles":                 "articles",
    "minutes":                  "minutes",
    "agents_count":             "5 agents",
    "locale_tag":               "en-US",

    # ── Page titles ───────────────────────────────────────────────────────────
    "page_title_home":          "AI Stock Investment System - Multi-Agent Stock Prediction System for the Vietnamese Market",
    "page_title_output":        "AI Stock Investment System - Analysis Results",
    "page_title_backtest":      "AI Stock Investment System - Backtest",

    # ── Hero ──────────────────────────────────────────────────────────────────
    "hero_desc":                "A multi-agent stock prediction system for the Vietnamese market.",
    "hero_desc2":               "Powered by <strong>Groq API</strong> (free) - real-time data from <strong>vnstock (VCI / MSN)</strong>.",
    "hero_tag_text_agents":     "Indicator &amp; Sentiment &amp; Alpha &amp; Decision",
    "hero_tag_vision_agents":   "Pattern &amp; Trend",
    "hero_tag_sentiment":       "ViSoBERT · Sentiment",
    "hero_tag_realtime":        "Real-time · vnstock",
    "hero_btn":                 "Start analysis",

    # ── Loading overlay ───────────────────────────────────────────────────────
    "loading_title":            "Analyzing...",
    "loading_sub":              "The multi-agent system is processing market data",
    "load_step1":               "Fetching real-time data",
    "load_step1_tf":            "Fetching {tf} data",
    "load_step2":               "Indicator Agent - Computing technical indicators",
    "load_step3":               "Alpha Agent - Sentiment analysis &amp; alpha factor generation",
    "load_step4":               "Pattern Agent - Candlestick pattern recognition",
    "load_step5":               "Trend Agent - Trend analysis",
    "load_step6":               "Decision Agent - Making the decision",

    # ── Status bar ────────────────────────────────────────────────────────────
    "st_checking_groq":         "Checking Groq...",
    "st_groq_ready":            "Groq ready",
    "st_groq_unconfigured":     "Groq not configured",
    "st_groq_check_failed":     "Could not check Groq",
    "st_checking_vnstock":      "Checking vnstock...",
    "st_rt_ready":              "Real-time ready",
    "st_vnstock_missing":       "vnstock not installed",
    "st_connect_failed":        "Connection failed",
    "st_status_check_failed":   "Status check failed",
    "st_loading_symbols":       "Loading symbols...",
    "st_symbol_count":          "{n} stock symbols (HOSE / HNX / UPCOM)",
    "st_updated":               "Updated:",
    "st_refresh":               "Refresh",

    # ── Analysis form ─────────────────────────────────────────────────────────
    "form_title":               "Analysis configuration",
    "api_notice_title":         "A Groq API key is required!",
    "api_notice_body":          "Get a free key at <a href=\"https://console.groq.com/keys\" target=\"_blank\">console.groq.com/keys</a> then enter it under <strong>Groq API settings</strong> below.",
    "select_stock":             "Select a stock symbol",
    "search_placeholder":       "Search: VNM, VIC, ACB, FPT...",
    "loading_symbol_list":      "Loading symbol list...",
    "loading_from_vnstock":     "Loading from vnstock...",
    "err_load_symbol_list":     "Could not load the symbol list.",
    "no_symbol_found":          "No symbol found",
    "selected":                 "Selected:",
    "stock_info":               "Symbol information",
    "timeframe":                "Timeframe",
    "tf_note":                  "Real-time data from vnstock · Candle count optimised per timeframe.",
    "selected_stock_detail":    "Selected symbol details",
    "click_symbol_hint":        "Click a symbol to see its details",
    "company":                  "Company",
    "symbol":                   "Symbol",
    "industry":                 "Industry",
    "live":                     "Live",
    "realtime":                 "Real-time",
    "fetch_on_run_hint":        "Data will be fetched live when the analysis runs.",
    "err_load_stock_info":      "Could not load information",
    "run_analysis":             "Run analysis",
    "analyzing":                "Analyzing...",

    # ── Timeframe labels ──────────────────────────────────────────────────────
    "tf_5m":                    "5 Minutes",
    "tf_15m":                   "15 Minutes",
    "tf_30m":                   "30 Minutes",
    "tf_1h":                    "1 Hour",
    "tf_1d":                    "1 Day",
    "tf_1w":                    "1 Week",
    "tf_1mo":                   "1 Month",
    "tf_desc_5m":               "Scalping, latest 78 candles",
    "tf_desc_15m":              "Short swing, latest 60 candles",
    "tf_desc_30m":              "Medium swing, latest 50 candles",
    "tf_desc_1h":               "Intraday swing, latest 45 candles",
    "tf_desc_1d":               "Daily analysis, latest 45 candles",
    "tf_desc_1w":               "Weekly analysis, latest 52 candles",
    "tf_desc_1mo":              "Monthly analysis, latest 36 candles",
    "tf_recent_candles":        "latest {n} candles",

    # ── Groq settings ─────────────────────────────────────────────────────────
    "groq_settings":            "Groq API settings",
    "api_key_label":            "Groq API Key",
    "free_tag":                 "Free",
    "toggle_key":               "Show/hide key",
    "get_key_at":               "Get a key at",
    "save_api_key":             "Save API key &amp; connect",
    "text_agent_model":         "Text agent model",
    "vision_agent_model":       "Vision agent model",
    "text_agent_roles":         "Indicator · Sentiment · Alpha · Decision",
    "vision_agent_roles":       "Pattern · Trend",
    "key_enter_prompt":         "Please enter an API key",
    "key_bad_format":           "Invalid key format (must start with gsk_)",
    "key_connecting":           "Connecting to Groq...",
    "key_ok":                   "API key is valid - Groq connected!",
    "key_invalid":              "Invalid key",
    "err_connection_prefix":    "Connection error: ",
    "models_saved":             "Saved: text={text}, vision={vision}",

    # ── vnstock ───────────────────────────────────────────────────────────────
    "vnstock_panel":            "vnstock - Real-time data",
    "vnstock_library":          "vnstock library",
    "vnstock_installed":        "Installed ✓",
    "data_connection":          "Data connection",
    "data_sources":             "Data sources",
    "cache":                    "Cache",
    "cache_items":              "{n} items · TTL {ttl}s",
    "clear_cache":              "Clear cache",
    "recheck":                  "Re-check",
    "cache_cleared":            "Cache cleared ✓",
    "err_clear_cache":          "Failed to clear the cache: ",

    # ── Client-side messages ──────────────────────────────────────────────────
    "warn_select_stock":        "Please select a stock symbol before analyzing.",
    "warn_save_key":            "Please enter your Groq API key and click \"Save API key\" first.",
    "err_no_job_id":            "Server error: no job_id returned.",
    "err_no_flask":             "Could not reach the Flask server.",
    "err_timeout":              "The analysis timed out. Please try again.",
    "err_poll":                 "Polling error: ",

    # ── Results page ──────────────────────────────────────────────────────────
    "header_sub_output":        "Multi-agent technical analysis results",
    "new_analysis":             "New analysis",
    "analyze_another":          "Analyze another symbol",
    "stat_candles":             "Candles analyzed",
    "stat_timeframe":           "Timeframe",
    "stat_symbol":              "Stock symbol",
    "stat_decision":            "Decision",
    "final_decision":           "Final trading decision",
    "rr_ratio":                 "R:R ratio:",
    "confidence":               "Confidence",
    "justification":            "Rationale",

    "agent_indicator":          "Indicator Agent",
    "agent_alpha":              "Alpha Agent",
    "agent_pattern":            "Pattern Agent",
    "agent_trend":              "Trend Agent",
    "agent_sub_indicator":      "MACD · RSI · Stochastic · Williams %R · ROC",
    "agent_sub_alpha":          "CafeF sentiment · ViSoBERT",
    "agent_sub_pattern":        "Vision analysis",
    "agent_sub_trend":          "Vision analysis · Support &amp; Resistance",
    "no_indicator_data":        "No indicator data",
    "no_alpha_data":            "No alpha factor data",

    # Sentiment
    "sentiment_data_title":     "Sentiment data (CafeF · ViSoBERT)",
    "sent_positive":            "Positive",
    "sent_negative":            "Negative",
    "sent_neutral":             "Neutral",
    "sent_positive_up":         "POSITIVE",
    "sent_negative_up":         "NEGATIVE",
    "sent_neutral_up":          "NEUTRAL",
    "sent_pos_short":           "POS",
    "sent_neg_short":           "NEG",
    "sent_neu_short":           "NEU",
    "article_distribution":     "Article distribution - {n} articles",
    "related_companies":        "Related companies (top {n})",
    "norm_title":               "Normalized sentiment variables - Alpha inputs",
    "norm_reliable":            "Reliable",
    "norm_unreliable":          "Low - few articles",
    "nv_zscore_formula":        "(avg − μ_batch) / (σ_batch + ε)",
    "nv_zscore_desc":           "Normalizes the mean score by the batch standard deviation.<br><strong>≈ 0</strong> = ordinary news flow (not neutral sentiment).<br><strong>&gt; +1.5</strong> = unusually positive news.<br><strong>&lt; −1.5</strong> = unusually negative news.",
    "nv_zscore_usage":          "Use it to detect news anomalies:",
    "nv_zscore_code":           "sign(SENT_ZSCORE) × tanh(|SENT_ZSCORE|) × technical",
    "nv_rel_formula":           "avg_target − avg_sector",
    "nv_rel_desc":              "Relative comparison against the sector's mean sentiment.<br><strong>&gt; 0</strong> = the stock outperforms its sector on news.<br><strong>&lt; 0</strong> = the stock underperforms its sector.<br>Market-wide bias cancels out through the subtraction.",
    "nv_rel_usage":             "Use it in long-short strategies:",
    "related_zscore_title":     "Related-company SENT_ZSCORE - Cross-sector alpha",
    "related_zscore_note":      "Symbol used in alpha formulas: <code class=\"zc-code\">ZSCORE_[SYMBOL]</code> - e.g. <code class=\"zc-code\">ZSCORE_VHM</code>, <code class=\"zc-code\">ZSCORE_ACB</code>. Used to detect sector divergence.",
    "alpha_factors":            "Alpha factors",
    "no_sentiment_note":        "No sentiment data - alpha factors were generated from technicals alone.",
    "alpha_consensus":          "Alpha consensus",
    "consensus_buy":            "▲ BUY",
    "consensus_sell":           "▼ SELL",
    "consensus_mixed":          "◆ MIXED",
    "alpha_summary":            "SUMMARY",
    "alpha_expert_note":        "Alpha expert commentary",

    # ── Python-generated alpha report (alpha_agent._build_alpha_report) ──────
    "ar_title":                 "5 Alpha Factors",
    "ar_th_alpha":              "Alpha",
    "ar_th_type":               "Type",
    "ar_th_value":              "Value",
    "ar_th_signal":             "Signal",
    "ar_th_horizon":            "Horizon",
    "ar_sig_up":                "▲ BULLISH",
    "ar_sig_down":              "▼ BEARISH",
    "ar_sig_neutral":           "◆ Neutral",
    "ar_sentiment":             "Sentiment",
    "ar_reliable":              "✅ Reliable",
    "ar_few_articles":          "⚠️ Few articles",
    "ar_volume":                "Volume",
    "ar_vol_real":              "actual",
    "ar_vol_proxy":             "range proxy",
    "ar_lbl_type":              "Type",
    "ar_lbl_horizon":           "Horizon",
    "ar_full_formula":          "Full formula",
    "ar_calc_steps":            "Calculation steps",
    "ar_interpretation":        "Interpretation",
    "ar_final_value":           "Final value",
    "ar_signal":                "Signal",

    # ── Default alpha labels (hardcoded 5-alpha fallback) ────────────────────
    "ar_type_fallback":         "Quantitative Alpha",
    "ar_flipped_note":          "[Signal inverted due to a negative historical correlation (IC < 0)]",
    "ar_a1_type":               "T+1 impulse (continuation)",
    "ar_a1_interp":             "Adjusted ROC(1)={roc:+.2f}, Volume surge={vol:.2f}x. {verdict}.",
    "ar_a1_up":                 "Strong upward momentum may carry into the T+1 candle",
    "ar_a1_down":               "Heavy selling pressure points to a lower T+1 candle",
    "ar_a1_neutral":            "Order flow gives no clear direction",
    "ar_a2_name":               "Sentiment-Flow (SFA) / Proxy",
    "ar_a2_type":               "T+1 impulse (continuation / divergence)",
    "ar_a2_formula":            "Tanh( Z_Sent×0.5 + ROC_adj×0.5 ) or MACD_Hist proxy",
    "ar_a2_logic_reliable":     "Reliable. Z_Sent={z:+.2f}, ROC_adj={roc:+.2f}.",
    "ar_a2_logic_proxy":        "Weak backtest/sentiment. Using the MACD_Hist proxy={macd:+.4f} (Z~{zm:+.2f}) and ROC_adj={roc:+.2f}.",
    "ar_a2_interp":             "{logic} → Balance of forces for T+1: Value={value:+.4f}.",
    "ar_a3_type":               "T+1 reversal (mean reversion)",
    "ar_a3_interp":             "SMA(5) deviation Z-Score={z:+.2f}. {verdict}",
    "ar_a3_up":                 "Price was pushed far below, baiting liquidity for a T+1 bounce",
    "ar_a3_down":               "Price stretched euphorically above SMA5, risking a T+1 shakeout",
    "ar_a3_neutral":            "Price oscillates around SMA5, leaving no void.",
    "ar_a4_type":               "T+1 band breakout",
    "ar_a4_interp":             "BB %B={b:.2f}, Z-Score(Vol, 5)={z:+.2f}. {verdict}",
    "ar_a4_up":                 "Upper-band breakout confirmed by volume",
    "ar_a4_down":               "Lower-band pressure confirmed by volume",
    "ar_a4_neutral":            "No clear band squeeze yet",
    "ar_a5_type":               "T+1 intraday absorption",
    "ar_a5_formula":            "Tanh( ROC_adj × Close_position × 3.0 )",
    "ar_a5_interp":             "Overnight momentum ROC_adj={roc:+.2f}, close position (Pos)={pos:+.2f}. {verdict}",
    "ar_a5_up":                 "The close settling high supports the price",
    "ar_a5_down":               "Wicks against the price direction show order flow fading",
    "ar_a5_neutral":            "Average candle body",

    # Charts
    "pattern_analysis":         "Pattern analysis",
    "candlestick_chart":        "Candlestick chart",
    "trend_analysis":           "Trend analysis",
    "trend_chart":              "Trend chart",
    "chart_unavailable":        "Chart unavailable",
    "support":                  "Support",
    "resistance":               "Resistance",

    # Trend report labels (used for client-side markdown normalisation)
    "trend_lbl_direction":      "Trend direction",
    "trend_lbl_support":        "Support level",
    "trend_lbl_resistance":     "Resistance level",
    "trend_lbl_slope":          "Trendline slope",
    "trend_lbl_price_vs_sup":   "Price vs support",
    "trend_lbl_detail":         "Detailed analysis",
    "trend_lbl_forecast":       "Forecast",
    "trend_lbl_confidence":     "Confidence",

    # ── Backtest page ─────────────────────────────────────────────────────────
    "bt_brand":                 "AI Stock Investment System - Backtest",
    "bt_sub":                   "Walk-forward backtesting · Full System vs No-Alpha System",
    "bt_config":                "Backtest configuration",
    "bt_config_sub":            "Walk-forward rolling window",
    "bt_symbol":                "Stock symbol",
    "bt_symbol_placeholder":    "VNM, ACB, FPT...",
    "bt_n_tests":               "Test points",
    "bt_n_tests_hint":          "Each test ≈ 3–4 minutes",
    "bt_window":                "Window size",
    "bt_window_hint":           "Candles per analysis",
    "bt_step":                  "Step between tests",
    "bt_step_hint":             "Candles to roll each time (≥1)",
    "bt_start":                 "Start backtest",
    "bt_stop":                  "Stop backtest",
    "bt_warning":               "Each test point runs <strong>2 LLM passes</strong> (Full + No-Alpha) with delays to avoid Groq rate limits. 10 tests ≈ <strong>25–45 minutes</strong>. Do not close this tab while it runs.",
    "bt_status":                "Status",
    "bt_not_started":           "Not started",
    "bt_progress":              "Progress",
    "bt_step_data":             "Load historical data",
    "bt_step_full":             "Full System (with Alpha)",
    "bt_step_no":               "No-Alpha System",
    "bt_step_save":             "Save results",
    "bt_full_system":           "Full System",
    "bt_no_alpha":              "No-Alpha",
    "bt_waiting":               "Waiting for results...",
    "bt_calculating":           "Calculating...",
    "bt_waiting_data":          "Waiting for data...",
    "bt_alpha_lift":            "Alpha Lift (Accuracy)",
    "bt_acc_gain":              "Additional accuracy gained",
    "bt_pnl_full":              "Full P&L (α)",
    "bt_pnl_no":                "No-α P&L",
    "bt_pnl_sub":               "Simulated P&L (cumulative)",
    "bt_chart_pnl":             "Simulated profit (P&L %)",
    "bt_chart_acc":             "Cumulative accuracy",
    "bt_chart_x":               "Test #",
    "bt_chart_y_pnl":           "Cumulative return (%)",
    "bt_ds_full_pnl":           "Full (α)",
    "bt_ds_no_pnl":             "No-α",
    "bt_ds_full_correct":       "Full correct",
    "bt_ds_no_correct":         "No-α correct",
    "bt_compare":               "Detailed comparison",
    "bt_compare_sub":           "Win rate by trade direction",
    "bt_no_data":               "No data yet",
    "bt_timeline":              "Per-test-point details",
    "bt_th_window":             "Window",
    "bt_th_actual":             "Actual",
    "bt_th_full_pred":          "Full pred",
    "bt_th_full_ok":            "Full ✓",
    "bt_th_no_pred":            "No-α pred",
    "bt_th_no_ok":              "No-α ✓",
    "bt_th_alpha_adds":         "Alpha adds?",
    "bt_waiting_first":         "Waiting for the first test...",
    "bt_enter_symbol":          "Enter a stock symbol!",
    "bt_running":               "Running - {symbol} | {n} tests",
    "bt_stopped":               "Stopped",
    "bt_done":                  "✅ Backtest complete!",
    "bt_test_points":           "{n} test points",
    "bt_valid_correct":         "{valid} valid tests · {correct} correct",
    "bt_lift_strong":           "🟢 Alpha improves results significantly",
    "bt_lift_slight":           "🟡 Alpha improves results slightly",
    "bt_lift_none":             "⚪ No change",
    "bt_lift_neg":              "🔴 Alpha does not help",
    "bt_eta":                   "ETA ~{n} minutes",
    "bt_finished":              "Finished",
    "bt_test":                  "Test",
    "bt_actual":                "Actual",
    "bt_acc_total":             "Overall accuracy",
    "bt_pnl_sim":               "Simulated return (%)",
    "bt_win_long":              "LONG win rate",
    "bt_win_short":             "SHORT win rate",
    "bt_alpha_helps":           "🟢 Helps",
    "bt_alpha_hurts":           "🔴 Hurts",
    "bt_both_right":            "⚪ Both correct",
    "bt_both_wrong":            "⚫ Both wrong",

    # ── Backend error messages ────────────────────────────────────────────────
    "err_api_key_missing":      "❌ The Groq API key is not configured. Please enter your API key in Settings.",
    "err_api_key_missing_short": "❌ The Groq API key is not configured.",
    "err_api_key_not_set":      "API key is not configured",
    "err_api_key_invalid":      "❌ Invalid Groq API key. Please verify your key at console.groq.com",
    "err_api_key_empty":        "The API key must not be empty.",
    "err_api_key_format":       "Invalid key format (must start with gsk_)",
    "err_api_key_first":        "Please configure the API key first.",
    "err_rate_limit":           "⏳ Groq rate limit reached - please wait a few seconds and try again.",
    "err_model_not_found":      "❌ Model not found. Check the model name in Settings.",
    "err_connection":           "🌐 Cannot reach the Groq API. Check your internet connection.",
    "err_analysis":             "❌ Analysis error: {detail}",
    "err_missing_columns":      "Missing data columns. Available columns: {columns}",
    "err_select_stock":         "Please select a stock symbol.",
    "err_enter_stock":          "Please enter a stock symbol.",
    "err_vnstock_missing":      "vnstock is not installed. Run: pip install vnstock",
    "err_no_data_for":          "No data available for {symbol}.",
    "err_job_not_found":        "Job not found.",
    "err_not_finished":         "Not finished yet.",
    "err_unknown":              "Unknown error",
    "err_models_both":          "Please enter both model names.",
    "err_update_failed":        "Update failed",
    "no_results":               "No results.",
}


def t(key: str, lang: str = DEFAULT_LANG, **fmt) -> str:
    """Tra cứu chuỗi đã dịch; fallback về tiếng Việt rồi về chính `key`."""
    lang = normalize_lang(lang)
    text = MESSAGES.get(lang, {}).get(key) or MESSAGES[DEFAULT_LANG].get(key) or key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError):
            return text
    return text


# ── Nhãn tín hiệu / Signal labels ─────────────────────────────────────────────
# Giá trị nội bộ (khoá) LUÔN giữ nguyên tiếng Việt để không phá vỡ logic đếm /
# so sánh sẵn có. Chỉ khi *render* mới ánh xạ sang ngôn ngữ hiển thị.

_SIGNAL_EN = {
    "TĂNG":        "BULLISH",
    "GIẢM":        "BEARISH",
    "TRUNG TÍNH":  "NEUTRAL",
    "TRUNG_TÍNH":  "NEUTRAL",
    "HỖN HỢP":     "MIXED",
    "ĐI NGANG":    "SIDEWAYS",
    "TĂNG TỐC":    "ACCELERATING",
    "GIẢM TỐC":    "DECELERATING",
}

_CONFIDENCE_EN = {
    "Rất cao":     "Very high",
    "Cao":         "High",
    "Trung bình":  "Medium",
    "Thấp":        "Low",
}

_TIMEFRAME_EN = {
    "1 phút":  "1 Minute",
    "5 phút":  "5 Minutes",
    "15 phút": "15 Minutes",
    "30 phút": "30 Minutes",
    "1 giờ":   "1 Hour",
    "1 ngày":  "1 Day",
    "1 tuần":  "1 Week",
    "1 tháng": "1 Month",
}


def signal_label(signal: str, lang: str = DEFAULT_LANG) -> str:
    """Nhãn hiển thị của một tín hiệu nội bộ (TĂNG / GIẢM / TRUNG TÍNH…)."""
    if normalize_lang(lang) == "vi":
        return signal
    return _SIGNAL_EN.get(signal, signal)


def confidence_label(value: str, lang: str = DEFAULT_LANG) -> str:
    """Nhãn hiển thị của mức độ tin cậy (Cao / Trung bình / Thấp)."""
    if normalize_lang(lang) == "vi":
        return value
    return _CONFIDENCE_EN.get(value, value)


def localize_timeframe(display: str, lang: str = DEFAULT_LANG) -> str:
    """
    Đổi nhãn khung thời gian hiển thị sang ngôn ngữ đích.

    QUAN TRỌNG: chỉ dùng cho *hiển thị*. Giá trị `state["time_frame"]` phải luôn
    giữ nguyên nhãn tiếng Việt vì `static_util.get_forecast_horizon` và
    `alpha_agent` ánh xạ ngược từ nhãn này về mã khung ("1d", "1w"…).
    """
    if not display or normalize_lang(lang) == "vi":
        return display
    return _TIMEFRAME_EN.get(str(display).strip().lower(), display)


# ── Horizon dự báo / Forecast horizon ─────────────────────────────────────────

_HORIZON_EN = {
    3: {
        "horizon_desc": (
            "the direction over the next 3 trading sessions (T → T+2) "
            "- per the T+2.5 settlement rule of the Vietnamese stock market"
        ),
        "horizon_short": "T+2.5 (3 sessions)",
        "note": (
            "Shares bought on day T can only be sold on the afternoon of T+2, "
            "so the investor carries the risk across at least 3 candles."
        ),
    },
    1: {
        "horizon_desc": "the next candle (T+1)",
        "horizon_short": "T+1 (next candle)",
        "note": (
            "Short timeframes suit VN30F derivatives (T+0) "
            "or fine-tuning entries on the underlying stock."
        ),
    },
}


def get_horizon(time_frame: str, lang: str = DEFAULT_LANG) -> dict:
    """
    Bọc `static_util.get_forecast_horizon` và dịch phần mô tả.

    Các giá trị dùng cho logic (`horizon_val`, `lookahead_candles`) giữ nguyên,
    chỉ phần văn bản inject vào prompt mới được dịch.
    """
    from utils.static_util import get_forecast_horizon

    horizon = dict(get_forecast_horizon(time_frame))
    if normalize_lang(lang) == "vi":
        return horizon

    override = _HORIZON_EN.get(horizon.get("lookahead_candles", 3))
    if override:
        horizon.update(override)
    return horizon


# ── Chỉ thị ngôn ngữ cho LLM / LLM language directive ─────────────────────────

_LANG_DIRECTIVE = {
    "vi": (
        "YÊU CẦU NGÔN NGỮ: Viết TOÀN BỘ câu trả lời bằng tiếng Việt tự nhiên, "
        "kể cả tên các trường và nhãn."
    ),
    "en": (
        "LANGUAGE REQUIREMENT: Write your ENTIRE response in natural, fluent English. "
        "Do NOT use any Vietnamese words or phrases anywhere in the output - "
        "field labels, headings and values must all be in English."
    ),
}


def language_directive(lang: str = DEFAULT_LANG) -> str:
    """Chỉ thị ngôn ngữ nối vào cuối mọi system prompt gửi tới LLM."""
    return _LANG_DIRECTIVE[normalize_lang(lang)]


# ── Xuất catalogue cho template / Catalogue export for templates ──────────────

def catalogue(lang: str = DEFAULT_LANG) -> Dict[str, str]:
    """
    Trả về toàn bộ từ điển chuỗi của một ngôn ngữ, đã merge fallback tiếng Việt.

    Dùng để inject vào Jinja template (`{{ T.system_name }}`) và serialise sang
    JSON cho JavaScript phía client (`window.T`).
    """
    lang = normalize_lang(lang)
    merged = dict(MESSAGES[DEFAULT_LANG])
    merged.update(MESSAGES.get(lang, {}))
    return merged
