import math
import time

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage


# ── Retry wrapper ──────────────────────────────────────────────────────────────

def _invoke_with_retry(call_fn, *args, retries=3, wait_sec=5):
    last_err = None
    for attempt in range(retries):
        try:
            return call_fn(*args)
        except Exception as e:
            last_err = e
            print(f"[IndicatorAgent] Lỗi lần {attempt + 1}/{retries}: {e}")
            if attempt < retries - 1:
                time.sleep(wait_sec)
    raise RuntimeError(f"[IndicatorAgent] Thất bại sau {retries} lần thử. Lỗi: {last_err}")


# ── Tính toán chỉ báo ─────────────────────────────────────────────────────────

def _compute_all_indicators(kline_data: dict, toolkit) -> dict:
    results = {}
    for name, fn, kwargs in [
        ("macd",  toolkit.compute_macd,  {"kline_data": kline_data}),
        ("rsi",   toolkit.compute_rsi,   {"kline_data": kline_data}),
        ("roc",   toolkit.compute_roc,   {"kline_data": kline_data}),
        ("stoch", toolkit.compute_stoch, {"kline_data": kline_data}),
        ("willr", toolkit.compute_willr, {"kline_data": kline_data}),
    ]:
        try:
            results[name] = fn.invoke(kwargs)
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


# ── Helpers đọc list ──────────────────────────────────────────────────────────

def _ok(x) -> bool:
    """True nếu x là số thực hữu hạn (giữ cả 0.0)."""
    try:
        f = float(x)
        return not math.isnan(f) and not math.isinf(f)
    except (TypeError, ValueError):
        return False


def _clean(lst):
    """Lọc NaN/None, giữ 0.0, trả list float."""
    return [round(float(v), 4) for v in (lst or []) if _ok(v)]


def _last1(lst):
    c = _clean(lst)
    return c[-1] if c else None


def _lastn(lst, n=5):
    return _clean(lst)[-n:]


# ── Python classify tín hiệu — KHÔNG để LLM đếm ──────────────────────────────

def _classify_signals(indicators: dict, kline_data: dict) -> dict:
    """
    Python tự phân loại tín hiệu từng chỉ báo và đếm tổng hợp.
    Kết quả này được inject vào prompt như "ground truth" cứng —
    LLM chỉ được viết diễn giải, KHÔNG được tự đếm lại.

    Trả về dict gồm:
      - "macd", "rsi", "roc", "stoch", "willr": signal từng chỉ báo
      - "__summary__": tổng hợp đếm
    """
    signals = {}

    # ── MACD ──────────────────────────────────────────────────────────────────
    d = indicators.get("macd", {})
    if "error" not in d:
        ml = _last1(d.get("macd", []))
        sl = _last1(d.get("macd_signal", []))
        hl = _last1(d.get("macd_hist", []))
        m2 = _lastn(d.get("macd", []), 2)
        s2 = _lastn(d.get("macd_signal", []), 2)
        h5 = _lastn(d.get("macd_hist", []), 5)

        # Ưu tiên 1: giao cắt vừa xảy ra (tín hiệu mạnh nhất)
        if len(m2) == 2 and len(s2) == 2:
            if m2[0] < s2[0] and m2[1] >= s2[1]:
                sig = "TĂNG"   # Golden cross
            elif m2[0] > s2[0] and m2[1] <= s2[1]:
                sig = "GIẢM"   # Death cross
            # Ưu tiên 2: chiều histogram (hiện tại)
            elif hl is not None:
                if hl > 0:
                    # Histogram dương nhưng đang thu hẹp → sắp đảo chiều
                    sig = "TĂNG" if (len(h5) < 2 or h5[-1] >= h5[-2]) else "TRUNG_TÍNH"
                elif hl < 0:
                    sig = "GIẢM" if (len(h5) < 2 or h5[-1] <= h5[-2]) else "TRUNG_TÍNH"
                else:
                    sig = "TRUNG_TÍNH"
            else:
                sig = "TRUNG_TÍNH"
        elif hl is not None:
            sig = "TĂNG" if hl > 0 else "GIẢM" if hl < 0 else "TRUNG_TÍNH"
        else:
            sig = "TRUNG_TÍNH"

        signals["macd"] = {
            "signal":        sig,
            "macd_val":      ml,
            "signal_val":    sl,
            "hist_val":      hl,
            "hist_positive": (hl > 0) if hl is not None else None,
            # Flag rõ ràng để LLM không nhầm: histogram ≠ khoảng cách MACD-Signal
            "note": (
                f"Histogram={hl} (dương=MACD trên Signal, âm=MACD dưới Signal). "
                f"MACD Line={ml}, Signal Line={sl}. "
                "KHÔNG dùng giá trị này cho chỉ báo khác."
            ),
        }
    else:
        signals["macd"] = {"signal": "TRUNG_TÍNH", "error": d["error"]}

    # ── RSI ───────────────────────────────────────────────────────────────────
    d = indicators.get("rsi", {})
    if "error" not in d:
        rl = _last1(d.get("rsi", []))
        r5 = _lastn(d.get("rsi", []), 5)

        if rl is not None:
            if rl >= 70:
                sig = "GIẢM"       # Overbought — rủi ro đảo chiều
            elif rl <= 30:
                sig = "TĂNG"       # Oversold — khả năng bật tăng
            elif rl >= 55:
                sig = "TĂNG"       # Vùng tăng
            elif rl <= 45:
                sig = "GIẢM"       # Vùng giảm
            else:
                # Vùng 45-55: xét xu hướng RSI để quyết định
                if len(r5) >= 3:
                    sig = "TĂNG" if r5[-1] > r5[-3] else "GIẢM" if r5[-1] < r5[-3] else "TRUNG_TÍNH"
                else:
                    sig = "TRUNG_TÍNH"
        else:
            sig = "TRUNG_TÍNH"

        # Xu hướng RSI (tăng/giảm/đi ngang)
        if len(r5) >= 3:
            rsi_trend = "TĂNG" if r5[-1] > r5[-3] else "GIẢM" if r5[-1] < r5[-3] else "ĐI NGANG"
        else:
            rsi_trend = "Không đủ dữ liệu"

        signals["rsi"] = {
            "signal":    sig,
            "value":     rl,
            "trend":     rsi_trend,
            "note":      f"RSI={rl}. Chỉ số này KHÔNG liên quan đến Histogram MACD.",
        }
    else:
        signals["rsi"] = {"signal": "TRUNG_TÍNH", "error": d["error"]}

    # ── ROC ───────────────────────────────────────────────────────────────────
    d = indicators.get("roc", {})
    if "error" not in d:
        rc  = _last1(d.get("roc", []))
        rc5 = _lastn(d.get("roc", []), 5)

        if rc is not None:
            if rc > 0.5:
                sig = "TĂNG"
            elif rc < -0.5:
                sig = "GIẢM"
            else:
                sig = "TRUNG_TÍNH"   # ROC gần 0 = không có động lượng rõ
        else:
            sig = "TRUNG_TÍNH"

        # Gia tốc
        if len(rc5) >= 2:
            accel = "TĂNG TỐC" if abs(rc5[-1]) > abs(rc5[-2]) else "GIẢM TỐC"
        else:
            accel = "Không đủ dữ liệu"

        signals["roc"] = {
            "signal": sig,
            "value":  rc,
            "accel":  accel,
            "note":   f"ROC={rc}%. Đây là chỉ báo MOMENTUM, không phải dao động.",
        }
    else:
        signals["roc"] = {"signal": "TRUNG_TÍNH", "error": d["error"]}

    # ── Stochastic ────────────────────────────────────────────────────────────
    d = indicators.get("stoch", {})
    if "error" not in d:
        kl = _last1(d.get("stoch_k", []))
        dl = _last1(d.get("stoch_d", []))
        k2 = _lastn(d.get("stoch_k", []), 2)
        d2 = _lastn(d.get("stoch_d", []), 2)

        # Ưu tiên 1: giao cắt %K/%D vừa xảy ra
        if len(k2) == 2 and len(d2) == 2:
            if k2[0] < d2[0] and k2[1] >= d2[1]:
                sig = "TĂNG"   # %K cắt lên trên %D
            elif k2[0] > d2[0] and k2[1] <= d2[1]:
                sig = "GIẢM"   # %K cắt xuống dưới %D
            # Ưu tiên 2: vùng quá mua/quá bán
            elif kl is not None:
                if kl >= 80:
                    sig = "GIẢM"   # Overbought
                elif kl <= 20:
                    sig = "TĂNG"   # Oversold
                else:
                    sig = "TĂNG" if (kl and dl and kl > dl) else "GIẢM"
            else:
                sig = "TRUNG_TÍNH"
        elif kl is not None:
            if kl >= 80:   sig = "GIẢM"
            elif kl <= 20: sig = "TĂNG"
            else:          sig = "TRUNG_TÍNH"
        else:
            sig = "TRUNG_TÍNH"

        signals["stoch"] = {
            "signal": sig,
            "k":      kl,
            "d":      dl,
            # Cảnh báo rõ để LLM không nhầm giá trị với MACD
            "note": (
                f"%K={kl}, %D={dl}. "
                "Stochastic KHÔNG có Histogram. "
                "KHÔNG dùng giá trị MACD Histogram ở đây."
            ),
        }
    else:
        signals["stoch"] = {"signal": "TRUNG_TÍNH", "error": d["error"]}

    # ── Williams %R ───────────────────────────────────────────────────────────
    d = indicators.get("willr", {})
    if "error" not in d:
        wl = _last1(d.get("willr", []))
        w5 = _lastn(d.get("willr", []), 5)

        if wl is not None:
            if wl >= -20:
                sig = "GIẢM"   # Overbought (gần 0)
            elif wl <= -80:
                sig = "TĂNG"   # Oversold (gần -100)
            else:
                # Vùng trung tính: xét xu hướng %R
                if len(w5) >= 3:
                    # %R tiến về 0 = cải thiện = TĂNG; tiến về -100 = xấu = GIẢM
                    sig = "TĂNG" if w5[-1] > w5[-3] else "GIẢM" if w5[-1] < w5[-3] else "TRUNG_TÍNH"
                else:
                    sig = "TRUNG_TÍNH"
        else:
            sig = "TRUNG_TÍNH"

        # Xu hướng %R
        if len(w5) >= 2:
            w_trend = "CẢI THIỆN (tiến về 0)" if w5[-1] > w5[-2] else "XẤU ĐI (tiến về -100)"
        else:
            w_trend = "Không đủ dữ liệu"

        signals["willr"] = {
            "signal":  sig,
            "value":   wl,
            "trend":   w_trend,
            "note":    f"%R={wl}. Thang đo -100 đến 0: gần 0=quá mua, gần -100=quá bán.",
        }
    else:
        signals["willr"] = {"signal": "TRUNG_TÍNH", "error": d["error"]}

    # ── Tổng hợp: Python đếm, KHÔNG để LLM đếm ───────────────────────────────
    indicator_order = ["macd", "rsi", "roc", "stoch", "willr"]
    all_sigs = [signals[k]["signal"] for k in indicator_order if k in signals]

    n_tang   = all_sigs.count("TĂNG")
    n_giam   = all_sigs.count("GIẢM")
    n_trung  = all_sigs.count("TRUNG_TÍNH")
    total    = len(all_sigs)

    if n_tang > n_giam and n_tang >= 3:
        consensus   = "TĂNG"
        confidence  = "Cao" if n_tang >= 4 else "Trung bình"
    elif n_giam > n_tang and n_giam >= 3:
        consensus   = "GIẢM"
        confidence  = "Cao" if n_giam >= 4 else "Trung bình"
    elif n_tang > n_giam:
        consensus   = "TĂNG"
        confidence  = "Thấp"
    elif n_giam > n_tang:
        consensus   = "GIẢM"
        confidence  = "Thấp"
    else:
        consensus   = "HỖN HỢP"
        confidence  = "Thấp"

    signals["__summary__"] = {
        "n_tang":     n_tang,
        "n_giam":     n_giam,
        "n_trung":    n_trung,
        "total":      total,
        "consensus":  consensus,
        "confidence": confidence,
        # Breakdown rõ từng chỉ báo để LLM không nhầm
        "breakdown": {
            k: signals[k]["signal"]
            for k in indicator_order if k in signals
        },
    }

    return signals


# ── Render bảng số liệu bằng Python ──────────────────────────────────────────

def _render_indicator_table(indicators: dict, kline_data: dict) -> str:
    """
    Render toàn bộ 5 chỉ báo thành bảng số thực.
    Mỗi section được đóng gói rõ ràng, KHÔNG có số nào rò rỉ sang section khác.
    """
    sec = []

    # ── MACD ──────────────────────────────────────────────────────────────────
    d = indicators.get("macd", {})
    if "error" not in d:
        ml = _last1(d.get("macd", []))
        sl = _last1(d.get("macd_signal", []))
        hl = _last1(d.get("macd_hist", []))
        m5 = _lastn(d.get("macd", []),        5)
        s5 = _lastn(d.get("macd_signal", []), 5)
        h5 = _lastn(d.get("macd_hist", []),   5)
        m2 = _lastn(d.get("macd", []),        2)
        s2 = _lastn(d.get("macd_signal", []), 2)

        if len(m2) == 2 and len(s2) == 2:
            if m2[0] < s2[0] and m2[1] >= s2[1]:
                cross = "⚡ GOLDEN CROSS: MACD cắt lên trên Signal → tín hiệu MUA"
            elif m2[0] > s2[0] and m2[1] <= s2[1]:
                cross = "⚡ DEATH CROSS: MACD cắt xuống dưới Signal → tín hiệu BÁN"
            else:
                gap = round(ml - sl, 4) if (ml is not None and sl is not None) else "N/A"
                pos = "trên" if (isinstance(gap, float) and gap > 0) else "dưới"
                cross = f"MACD đang ở {pos} Signal (khoảng cách MACD−Signal = {gap})"
        else:
            cross = "Không đủ dữ liệu để xác định giao cắt"

        h_trend = (
            "MỞ RỘNG (động lượng tăng)" if len(h5) >= 2 and h5[-1] > h5[-2]
            else "THU HẸP (động lượng giảm)" if len(h5) >= 2
            else "Không xác định"
        )

        sec.append(
            "=== MACD (12,26,9) — CHỈ ĐỌC SỐ TRONG SECTION NÀY ===\n"
            f"| Chỉ số      | Giá trị mới nhất | Chuỗi 5 nến gần nhất |\n"
            f"|-------------|-----------------|----------------------|\n"
            f"| MACD Line   | **{ml}**        | {m5}                 |\n"
            f"| Signal Line | **{sl}**        | {s5}                 |\n"
            f"| Histogram   | **{hl}**        | {h5}                 |\n\n"
            f"- Giao cắt: {cross}\n"
            f"- Histogram xu hướng: {h_trend}\n"
            f"- MACD Line so với 0: {'Dương → vùng tăng' if ml is not None and ml > 0 else 'Âm → vùng giảm' if ml is not None else 'N/A'}\n"
            f"[END MACD SECTION — giá trị Histogram={hl} KHÔNG áp dụng cho chỉ báo khác]\n"
        )
    else:
        sec.append(f"=== MACD ===\nLỗi tính toán: {d['error']}\n[END MACD SECTION]\n")

    # ── RSI ───────────────────────────────────────────────────────────────────
    d = indicators.get("rsi", {})
    if "error" not in d:
        rl = _last1(d.get("rsi", []))
        r5 = _lastn(d.get("rsi", []), 5)

        if rl is not None:
            if rl >= 70:   zone = f"⚠️ QUÁ MUA ({rl}) → rủi ro đảo chiều giảm"
            elif rl >= 60: zone = f"Vùng tăng mạnh ({rl}) → xu hướng tăng duy trì"
            elif rl >= 55: zone = f"Vùng tăng ({rl}) → nghiêng về tăng"
            elif rl <= 30: zone = f"⚠️ QUÁ BÁN ({rl}) → khả năng bật tăng"
            elif rl <= 40: zone = f"Vùng giảm mạnh ({rl}) → xu hướng giảm duy trì"
            elif rl <= 45: zone = f"Vùng giảm ({rl}) → nghiêng về giảm"
            else:          zone = f"Trung tính ({rl}) → vùng 45-55, chưa xác định hướng"
        else:
            zone = "Không xác định"

        if len(r5) >= 3:
            r_trend = "TĂNG" if r5[-1] > r5[-3] else "GIẢM" if r5[-1] < r5[-3] else "ĐI NGANG"
        else:
            r_trend = "Không đủ dữ liệu"

        sec.append(
            "=== RSI (14) — CHỈ ĐỌC SỐ TRONG SECTION NÀY ===\n"
            f"- RSI mới nhất: **{rl}** → {zone}\n"
            f"- Chuỗi 5 nến: {r5}\n"
            f"- Xu hướng RSI: {r_trend}\n"
            f"- Ngưỡng theo dõi: "
            + (f"70 — RSI đang tiệm cận, nếu bẻ xuống = xác nhận bán" if rl is not None and rl >= 65
               else f"30 — RSI đang tiệm cận, nếu bẻ lên = xác nhận mua" if rl is not None and rl <= 35
               else "50 — ngưỡng phân chia tăng/giảm") + "\n"
            f"[END RSI SECTION — RSI={rl}, KHÔNG dùng số này cho MACD hay Stochastic]\n"
        )
    else:
        sec.append(f"=== RSI ===\nLỗi tính toán: {d['error']}\n[END RSI SECTION]\n")

    # ── ROC ───────────────────────────────────────────────────────────────────
    d = indicators.get("roc", {})
    if "error" not in d:
        rc  = _last1(d.get("roc", []))
        rc5 = _lastn(d.get("roc", []), 5)

        if rc is not None:
            if rc > 3:     roc_note = "Động lượng tăng RẤT MẠNH"
            elif rc > 0.5: roc_note = "Động lượng tăng nhẹ"
            elif rc > 0:   roc_note = "Động lượng tăng yếu (gần 0)"
            elif rc > -0.5:roc_note = "Động lượng giảm yếu (gần 0)"
            elif rc > -3:  roc_note = "Động lượng giảm nhẹ"
            else:          roc_note = "Động lượng giảm RẤT MẠNH"
        else:
            roc_note = "Không xác định"

        if len(rc5) >= 2:
            accel = "TĂNG TỐC" if abs(rc5[-1]) > abs(rc5[-2]) else "GIẢM TỐC"
        else:
            accel = "Không đủ dữ liệu"

        sec.append(
            "=== ROC — Rate of Change (10) — CHỈ ĐỌC SỐ TRONG SECTION NÀY ===\n"
            f"- ROC mới nhất: **{rc}%** → {roc_note}\n"
            f"- Chuỗi 5 nến: {rc5}\n"
            f"- Gia tốc động lượng: {accel}\n"
            f"[END ROC SECTION — ROC={rc}%, KHÔNG dùng số này cho chỉ báo khác]\n"
        )
    else:
        sec.append(f"=== ROC ===\nLỗi tính toán: {d['error']}\n[END ROC SECTION]\n")

    # ── Stochastic ────────────────────────────────────────────────────────────
    d = indicators.get("stoch", {})
    if "error" not in d:
        kl = _last1(d.get("stoch_k", []))
        dl = _last1(d.get("stoch_d", []))
        k5 = _lastn(d.get("stoch_k", []), 5)
        d5 = _lastn(d.get("stoch_d", []), 5)
        k2 = _lastn(d.get("stoch_k", []), 2)
        d2 = _lastn(d.get("stoch_d", []), 2)

        if kl is not None:
            if kl >= 80:   k_zone = f"⚠️ QUÁ MUA (%K={kl}) — rủi ro đảo chiều giảm"
            elif kl <= 20: k_zone = f"⚠️ QUÁ BÁN (%K={kl}) — khả năng bật tăng"
            else:          k_zone = f"Trung tính (%K={kl})"
        else:
            k_zone = "Không xác định"

        if len(k2) == 2 and len(d2) == 2:
            if k2[0] < d2[0] and k2[1] >= d2[1]:
                stoch_cross = "⚡ %K cắt lên trên %D → tín hiệu MUA"
            elif k2[0] > d2[0] and k2[1] <= d2[1]:
                stoch_cross = "⚡ %K cắt xuống dưới %D → tín hiệu BÁN"
            else:
                above = "%K trên %D" if (kl and dl and kl > dl) else "%K dưới %D"
                stoch_cross = f"Không có giao cắt mới ({above})"
        else:
            stoch_cross = "Không đủ dữ liệu"

        sec.append(
            "=== STOCHASTIC OSCILLATOR (14,3,3) — CHỈ ĐỌC SỐ TRONG SECTION NÀY ===\n"
            "⚠️ Lưu ý: Stochastic KHÔNG có Histogram. Chỉ có %K và %D.\n"
            f"| Chỉ số | Giá trị mới nhất | Chuỗi 5 nến gần nhất |\n"
            f"|--------|-----------------|----------------------|\n"
            f"| %K     | **{kl}**        | {k5}                 |\n"
            f"| %D     | **{dl}**        | {d5}                 |\n\n"
            f"- Vùng: {k_zone}\n"
            f"- Giao cắt %K/%D: {stoch_cross}\n"
            f"[END STOCHASTIC SECTION — %K={kl}, %D={dl}. KHÔNG nhầm với Histogram MACD={_last1(indicators.get('macd',{}).get('macd_hist',[]))}]\n"
        )
    else:
        sec.append(f"=== STOCHASTIC ===\nLỗi tính toán: {d['error']}\n[END STOCHASTIC SECTION]\n")

    # ── Williams %R ───────────────────────────────────────────────────────────
    d = indicators.get("willr", {})
    if "error" not in d:
        wl = _last1(d.get("willr", []))
        w5 = _lastn(d.get("willr", []), 5)

        if wl is not None:
            if wl >= -20:   w_zone = f"⚠️ QUÁ MUA ({wl}) — gần đỉnh chu kỳ"
            elif wl <= -80: w_zone = f"⚠️ QUÁ BÁN ({wl}) — gần đáy chu kỳ"
            elif wl >= -40: w_zone = f"Nghiêng về quá mua ({wl})"
            elif wl <= -60: w_zone = f"Nghiêng về quá bán ({wl})"
            else:           w_zone = f"Trung tính ({wl})"
        else:
            w_zone = "Không xác định"

        if len(w5) >= 2:
            w_trend = "CẢI THIỆN (tiến về 0)" if w5[-1] > w5[-2] else "XẤU ĐI (tiến về -100)"
        else:
            w_trend = "Không đủ dữ liệu"

        sec.append(
            "=== WILLIAMS %R (14) — CHỈ ĐỌC SỐ TRONG SECTION NÀY ===\n"
            "⚠️ Thang đo: 0 = quá mua, -100 = quá bán. Tiến về 0 = cải thiện.\n"
            f"- %R mới nhất: **{wl}** → {w_zone}\n"
            f"- Chuỗi 5 nến: {w5}\n"
            f"- Xu hướng %R: {w_trend}\n"
            f"[END WILLIAMS %R SECTION — %R={wl}]\n"
        )
    else:
        sec.append(f"=== WILLIAMS %R ===\nLỗi tính toán: {d['error']}\n[END WILLIAMS %R SECTION]\n")

    # ── Tóm tắt giá ───────────────────────────────────────────────────────────
    try:
        df      = pd.DataFrame(kline_data)
        closes  = df["Close"].tolist()
        c0      = round(closes[-1], 4)
        c1      = round(closes[-2], 4)
        chg     = round(c0 - c1, 4)
        chg_pct = round(chg / c1 * 100, 2) if c1 else 0
        c5      = [round(x, 4) for x in closes[-5:]]
        n       = len(closes)

        ma5  = round(sum(closes[-5:])  / 5,  2) if n >= 5  else None
        ma10 = round(sum(closes[-10:]) / 10, 2) if n >= 10 else None
        ma20 = round(sum(closes[-20:]) / 20, 2) if n >= 20 else None

        if ma5 and ma10 and ma20:
            if c0 > ma5 and c0 > ma10 and c0 > ma20:
                ma_pos = "Trên tất cả MA → xu hướng TĂNG"
            elif c0 < ma5 and c0 < ma10 and c0 < ma20:
                ma_pos = "Dưới tất cả MA → xu hướng GIẢM"
            elif c0 > ma20:
                ma_pos = "Trên MA20 nhưng dưới MA ngắn hạn → đang điều chỉnh"
            else:
                ma_pos = "Hỗn hợp → đang tích lũy"
        else:
            ma_pos = "Không đủ dữ liệu MA"

        sec.append(
            "=== TÓM TẮT GIÁ ===\n"
            f"- Giá đóng cửa mới nhất: **{c0}** ({'+' if chg >= 0 else ''}{chg}, {chg_pct}%)\n"
            f"- 5 phiên gần nhất: {c5}\n"
            f"- MA5={ma5}  MA10={ma10}  MA20={ma20}\n"
            f"- Vị trí giá: {ma_pos}\n"
            f"[END GIÁ SECTION]\n"
        )
    except Exception as e:
        sec.append(f"=== TÓM TẮT GIÁ ===\nLỗi: {e}\n[END GIÁ SECTION]\n")

    return "\n---\n".join(sec)


# ── Render block phân loại để inject vào prompt ───────────────────────────────

def _render_classification_block(classified: dict, summary: dict) -> str:
    """Tạo chuỗi text rõ ràng để inject vào prompt như ground truth."""
    label_map = {
        "macd":  "MACD (12,26,9)",
        "rsi":   "RSI (14)",
        "roc":   "ROC (10)",
        "stoch": "Stochastic (14,3,3)",
        "willr": "Williams %R (14)",
    }
    lines = []
    for key, label in label_map.items():
        info = classified.get(key, {})
        sig  = info.get("signal", "TRUNG_TÍNH")
        note = info.get("note", "")
        lines.append(f"  - {label}: **{sig}**  ← {note}")

    breakdown_str = "\n".join(lines)

    return (
        "## ⚠️ PHÂN LOẠI TÍN HIỆU — ĐÃ XÁC ĐỊNH BỞI HỆ THỐNG, KHÔNG THAY ĐỔI\n\n"
        f"{breakdown_str}\n\n"
        "## ⚠️ TỔNG HỢP — ĐÃ ĐẾM BỞI HỆ THỐNG, KHÔNG TỰ ĐẾM LẠI\n\n"
        f"  - Số chỉ báo đồng thuận TĂNG : **{summary['n_tang']}/{summary['total']}**\n"
        f"  - Số chỉ báo đồng thuận GIẢM : **{summary['n_giam']}/{summary['total']}**\n"
        f"  - Số chỉ báo TRUNG TÍNH       : **{summary['n_trung']}/{summary['total']}**\n"
        f"  - Đồng thuận chủ đạo          : **{summary['consensus']}** — độ tin cậy **{summary['confidence']}**\n\n"
        "Quy tắc bắt buộc:\n"
        "1. Sử dụng ĐÚNG tín hiệu từng chỉ báo ở trên khi viết diễn giải.\n"
        "2. KHÔNG tự đếm lại hay thay đổi số tổng hợp.\n"
        "3. KHÔNG dùng số liệu của chỉ báo này khi mô tả chỉ báo khác.\n"
        "4. Mỗi section [END ... SECTION] là ranh giới cứng — không cross-reference.\n"
    )


# ── Main agent factory ─────────────────────────────────────────────────────────

def create_indicator_agent(llm, toolkit):
    """
    Tác nhân chỉ báo kỹ thuật.
    """

    def indicator_agent_node(state):
        kline_data = state["kline_data"]
        time_frame = state["time_frame"]

        # ── Bước 1: Python tính toán và phân loại ─────────────────────────────
        print("[IndicatorAgent] Đang tính toán 5 chỉ báo...")
        indicators = _compute_all_indicators(kline_data, toolkit)

        print("[IndicatorAgent] Đang phân loại tín hiệu bằng Python...")
        classified = _classify_signals(indicators, kline_data)
        summary    = classified.pop("__summary__")   # tách ra để dùng riêng

        indicator_table      = _render_indicator_table(indicators, kline_data)
        classification_block = _render_classification_block(classified, summary)

        print(
            f"[IndicatorAgent] Python classify xong: "
            f"TĂNG={summary['n_tang']}, GIẢM={summary['n_giam']}, "
            f"TRUNG_TÍNH={summary['n_trung']}, "
            f"Đồng thuận={summary['consensus']} ({summary['confidence']}). "
            f"Gọi LLM diễn giải..."
        )

        # ── Bước 2: LLM chỉ viết diễn giải ngôn ngữ ──────────────────────────
        # ── Horizon động ──────────────────────────────────────────────────
        from static_util import get_forecast_horizon
        horizon = get_forecast_horizon(time_frame)
        h_desc  = horizon["horizon_desc"]
        h_short = horizon["horizon_short"]

        system_prompt = (
            "Bạn là chuyên gia phân tích kỹ thuật HFT Việt Nam.\n\n"
            f"MỤC TIÊU DUY NHẤT: Dự đoán hướng giá cho **{h_desc}** — "
            "KHÔNG phân tích dài hạn.\n\n"
            "QUY TẮC QUAN TRỌNG NHẤT:\n"
            "1. Phần PHÂN LOẠI TÍN HIỆU và TỔNG HỢP đã được xác định bởi hệ thống Python — "
            "bạn phải sử dụng ĐÚNG các con số đó, KHÔNG tự đếm lại hay thay đổi.\n"
            "2. Mỗi chỉ báo có ranh giới [END ... SECTION] — KHÔNG dùng số của section này "
            "khi viết về section khác. Stochastic KHÔNG có Histogram.\n"
            f"3. Nhiệm vụ duy nhất của bạn: viết diễn giải ngôn ngữ rõ ràng, có tính ứng dụng cho {h_short}.\n"
            "4. KHÔNG bịa số. KHÔNG nói 'thiếu thông tin'."
        )

        user_prompt = (
            f"## Bảng số liệu đã tính toán — {time_frame} | Mục tiêu dự đoán: {h_short}\n\n"
            f"{indicator_table}\n\n"
            "---\n\n"
            f"{classification_block}\n\n"
            "---\n\n"
            f"## Yêu cầu: Viết báo cáo diễn giải hướng tới dự đoán {h_short}\n\n"
            "Với MỖI chỉ báo, viết theo đúng template sau "
            "(dùng ĐÚNG tín hiệu đã phân loại ở trên):\n\n"
            "**[Tên chỉ báo]**\n"
            f"- Tín hiệu {h_short}: [ĐÚNG như phân loại hệ thống]\n"
            "- Điểm giao cắt / ngưỡng quan trọng: [mô tả cụ thể có số từ section đúng]\n"
            "- Động lượng: [tăng tốc / giảm tốc / ổn định] — giải thích ngắn\n\n"
            "Sau 5 chỉ báo, viết phần tổng hợp "
            "(COPY ĐÚNG số từ phần TỔNG HỢP ĐÃ XÁC ĐỊNH BỞI HỆ THỐNG ở trên):\n\n"
            f"**Tổng hợp hội tụ tín hiệu — Dự đoán {h_short}**\n"
            f"- Số chỉ báo đồng thuận tăng: **{summary['n_tang']}/{summary['total']}**\n"
            f"- Số chỉ báo đồng thuận giảm: **{summary['n_giam']}/{summary['total']}**\n"
            f"- Xu hướng chủ đạo: **{summary['consensus']}** — mức độ tin cậy **{summary['confidence']}**\n"
            "- Nhận xét: [1-2 câu tóm tắt khả năng tăng/giảm dựa trên các chỉ báo]\n"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            response = _invoke_with_retry(llm.invoke, messages)
        except Exception as e:
            if "system" in str(e).lower() or "at least one message" in str(e).lower():
                print("[IndicatorAgent] Thử lại không có SystemMessage...")
                response = _invoke_with_retry(
                    llm.invoke,
                    [HumanMessage(content=system_prompt + "\n\n" + user_prompt)],
                )
            else:
                raise

        report = response.content

        # Fallback: nếu LLM trả rỗng, dùng bảng Python đã render + summary
        if not report or not str(report).strip():
            print("[IndicatorAgent] LLM trả rỗng → dùng bảng Python + classification.")
            report = (
                indicator_table
                + "\n\n---\n\n"
                + classification_block
            )

        print(f"[IndicatorAgent] Hoàn thành ({len(str(report))} ký tự).")

        return {
            "messages":        state.get("messages", []) + [response],
            "indicator_report": report,
        }

    return indicator_agent_node