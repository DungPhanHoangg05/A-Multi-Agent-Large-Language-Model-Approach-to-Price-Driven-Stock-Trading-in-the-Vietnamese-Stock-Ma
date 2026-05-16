import time

import static_util
from langchain_core.messages import HumanMessage, SystemMessage


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
        f"Phân tích mô hình nến {time_frame} từ dữ liệu OHLCV sau. "
        "Xác định mô hình cụ thể, thiên lệch định hướng và hàm ý giao dịch.\n\n"
        f"{ohlcv}\n\n"
        "Trả lời theo format:\n"
        "**Mô hình:** <tên>\n"
        "**Độ tin cậy:** Cao | Trung bình | Thấp\n"
        "**Thiên lệch:** Tăng | Giảm | Trung tính\n"
        "**Bằng chứng:** <dẫn chứng từ số liệu giá>\n"
        "**Hàm ý:** <1 câu hành động>"
    )
    response = tool_llm.invoke([HumanMessage(content=prompt)])
    return response.content


def create_pattern_agent(tool_llm, graph_llm, toolkit):

    PATTERN_TEXT = """
        Vui lòng tham khảo các mô hình nến kinh điển sau:
        
        1. Vai đầu vai ngược (Inverse Head and Shoulders)
        Ba đáy với đáy giữa thấp nhất; khi phá neckline, xác nhận đảo chiều sang xu hướng tăng mạnh.
        2. Đáy đôi (Double Bottom)
        Hai đáy ngang nhau tạo chữ W; breakout lên trên đỉnh giữa xác nhận đảo chiều tăng.
        3. Đáy vòng cung (Rounded Bottom)
        Giá tạo đáy chữ U mượt; cho thấy tích lũy dài hạn và chuyển sang xu hướng tăng ổn định.
        4. Nền ẩn (Hidden Base)
        Sideway chặt với biên độ nhỏ; breakout mạnh thường báo hiệu pha tăng mới bắt đầu.
        5. Nêm giảm (Falling Wedge)
        Giá giảm nhưng biên độ thu hẹp; breakout lên thường là tín hiệu đảo chiều tăng.
        6. Nêm tăng (Rising Wedge)
        Giá tăng nhưng lực yếu dần (hội tụ); breakdown xuống thường báo hiệu đảo chiều giảm.
        7. Tam giác tăng (Ascending Triangle)
        Hỗ trợ dốc lên, kháng cự ngang; breakout lên cho tín hiệu tiếp diễn xu hướng tăng.
        8. Tam giác giảm (Descending Triangle)
        Kháng cự dốc xuống, hỗ trợ ngang; breakdown xuống cho tín hiệu tiếp diễn xu hướng giảm.
        9. Cờ tăng (Bullish Flag)
        Sau impulse tăng mạnh, giá điều chỉnh nhẹ dạng kênh; breakout tiếp diễn xu hướng tăng.
        10. Cờ giảm (Bearish Flag)
        Sau impulse giảm mạnh, giá hồi nhẹ; breakdown tiếp diễn xu hướng giảm.
        11. Hộp giá (Rectangle)
        Giá dao động trong vùng ngang; breakout theo hướng nào thì đi theo hướng đó.
        12. Đảo chiều đảo (Island Reversal)
        Hai gap ngược chiều cô lập vùng giá; tín hiệu đảo chiều mạnh và nhanh.
        13. Đảo chiều chữ V (V-shaped Reversal)
        Giá đảo chiều cực nhanh không tích lũy; thường do panic/exhaustion và khó vào lệnh an toàn.
        14. Đỉnh/Đáy vòng cung (Rounded Top / Bottom)
        Chuyển pha chậm với hình vòm; thể hiện sự suy yếu/tích lũy trước khi đảo chiều.
        15. Tam giác mở rộng (Expanding Triangle)
        Biên độ dao động tăng dần; thị trường bất ổn, breakout khó đoán, rủi ro cao.
        16. Tam giác đối xứng (Symmetrical Triangle)
        Đỉnh thấp dần và đáy cao dần; breakout quyết định hướng tiếp theo, thường theo trend trước đó.
        """

    SYSTEM_PROMPT = (
        "Bạn là chuyên gia nhận dạng mô hình nến với 20 năm kinh nghiệm giao dịch. "
        "Nhiệm vụ: phân tích THUẦN TÚY từ hình ảnh biểu đồ để DỰ ĐOÁN hướng giá sắp tới. "
        "KHÔNG phân tích dài hạn — chỉ tập trung vào xác suất tăng/giảm trong tương lai gần.\n"
        "Quy tắc bắt buộc:\n"
        "1. Luôn đặt tên mô hình cụ thể. Nếu không rõ → ghi 'Tích lũy / Không rõ mô hình'.\n"
        "2. Luôn cam kết thiên lệch: Tăng, Giảm, hoặc Trung tính — KHÔNG được trả lời mơ hồ.\n"
        "3. Mô tả bằng chứng hình ảnh: hình dạng nến, bóng nến, thân nến, vị trí tương đối.\n"
        "4. Toàn bộ câu trả lời bằng tiếng Việt."
    )

    USER_PROMPT = (
        "Nhìn vào biểu đồ nến {time_frame} này và phân tích để DỰ ĐOÁN {h_desc}:\n\n"
        "1. **Mô hình tổng thể**: Xác định mô hình giá lớn nhất có thể nhìn thấy, tham chiếu từ các mô hình kinh điển {PATTERN_TEXT}"
        "2. **Nến đặc trưng**: Mô tả 3–5 nến gần nhất — kích thước thân, bóng nến trên/dưới, "
        "màu sắc và sự thay đổi so với nến trước.\n\n"
        "3. **Vùng giá quan trọng**: Nhận diện vùng hỗ trợ/kháng cự nào đang được kiểm tra "
        "dựa trên mật độ nến hoặc vùng giá tích lũy.\n\n"
        "4. **Tín hiệu bứt phá**: Có dấu hiệu breakout/breakdown không? "
        "Nến cuối cùng có xác nhận hướng không?\n\n"
        "Trả lời theo đúng format sau (tiếng Việt):\n\n"
        "**Mô hình:** <tên>\n\n"
        "**Độ tin cậy:** Cao | Trung bình | Thấp\n\n"
        "**Thiên lệch dự báo:** Tăng | Giảm | Trung tính\n\n"
        "**Bằng chứng hình ảnh:** <mô tả cụ thể những gì thấy trong biểu đồ>\n\n"
        "**Nến quan trọng:** <mô tả 3–5 nến gần nhất và ý nghĩa>\n\n"
        "**Hàm ý giao dịch:** <1 câu kỳ vọng cụ thể cho **{h_desc}** — tăng hay giảm>"
    )

    def pattern_agent_node(state):
        
        time_frame = state["time_frame"]
        kline_data = state["kline_data"]

        # ── Horizon động ──────────────────────────────────────────────────
        from static_util import get_forecast_horizon
        horizon = get_forecast_horizon(time_frame)
        h_desc  = horizon["horizon_desc"]

        # ── Bước 1: Lấy ảnh ──────────────────────────────────────────────
        pattern_image_b64 = state.get("pattern_image")

        if pattern_image_b64:
            print("[PatternAgent] Dùng ảnh từ state.")
        else:
            print("[PatternAgent] Tạo ảnh qua static_util...")
            try:
                result = static_util.generate_kline_image(kline_data)
                pattern_image_b64 = result.get("pattern_image")
            except Exception as e:
                print(f"[PatternAgent] Không tạo được ảnh: {e}")

        # ── Bước 2: Phân tích thị giác thuần ảnh ─────────────────────────
        report_content = None

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
                report_content = response.content
                print("[PatternAgent] Phân tích thị giác hoàn thành.")
            except Exception as e:
                # Thử lại không có SystemMessage (một số model không hỗ trợ)
                if any(k in str(e).lower() for k in ("at least one message", "system")):
                    try:
                        response = _invoke_with_retry(graph_llm.invoke, [human_msg])
                        report_content = response.content
                        print("[PatternAgent] Hoàn thành (không system message).")
                    except Exception as e2:
                        print(f"[PatternAgent] Thị giác thất bại: {e2}")
                else:
                    print(f"[PatternAgent] Lỗi model thị giác: {e}")

        # ── Bước 3: Fallback OHLCV nếu không có ảnh ─────────────────────
        if not report_content:
            reason = "không có ảnh" if not pattern_image_b64 else "model thị giác lỗi"
            print(f"[PatternAgent] Dùng fallback văn bản ({reason}).")
            try:
                report_content = _text_fallback_analysis(tool_llm, kline_data, time_frame)
            except Exception as e:
                print(f"[PatternAgent] Fallback cũng thất bại: {e}")
                report_content = (
                    "**Mô hình:** Không xác định được — cả thị giác lẫn văn bản đều thất bại.\n"
                    "**Thiên lệch:** Trung tính"
                )

        return {
            "messages":      state.get("messages", []),
            "pattern_report": report_content,
        }

    return pattern_agent_node