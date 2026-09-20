import re
import time
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pandas as pd
import requests

# ── Constants ─────────────────────────────────────────────────────────────────
REQUIRED_COLS = ["Datetime", "Open", "High", "Low", "Close"]

INTERVAL_MAP = {
    "1m":  "1",
    "5m":  "5",
    "15m": "15",
    "30m": "30",
    "1h":  "60",
    "1H":  "60",
    "1d":  "1D",
    "1w":  "1W",
    "1mo": "1M",
}

# Which intervals need intraday routing (not served by VCI daily API)
INTRADAY_INTERVALS: set = {"5m", "15m", "30m", "1h", "1H"}

# entrade resolution strings  (used by the MSN backend and direct REST fallback)
ENTRADE_RES_MAP = {
    "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "1H": "60",
    "1d": "D",  "1w": "W",  "1mo": "M",
}

# Per-timeframe configuration
TIMEFRAME_CONFIG: dict = {
    "5m":  {"lookback_days": 7,    "tail": 250, "candles": 78,  "display": "5 Phút",  "date_fmt": "%d/%m %H:%M", "tick_every": 8,  "group": "intraday"},
    "15m": {"lookback_days": 15,   "tail": 200, "candles": 60,  "display": "15 Phút", "date_fmt": "%d/%m %H:%M", "tick_every": 6,  "group": "intraday"},
    "30m": {"lookback_days": 30,   "tail": 200, "candles": 50,  "display": "30 Phút", "date_fmt": "%d/%m %H:%M", "tick_every": 5,  "group": "intraday"},
    "1h":  {"lookback_days": 90,   "tail": 200, "candles": 45,  "display": "1 Giờ",   "date_fmt": "%d/%m %H:%M", "tick_every": 5,  "group": "intraday"},
    "1H":  {"lookback_days": 90,   "tail": 200, "candles": 45,  "display": "1 Giờ",   "date_fmt": "%d/%m %H:%M", "tick_every": 5,  "group": "intraday"},
    "1d":  {"lookback_days": 400,  "tail": 200, "candles": 45,  "display": "1 Ngày",  "date_fmt": "%Y-%m-%d",    "tick_every": 5,  "group": "swing"},
    "1w":  {"lookback_days": 900,  "tail": 120, "candles": 52,  "display": "1 Tuần",  "date_fmt": "%Y-%m-%d",    "tick_every": 5,  "group": "swing"},
    "1mo": {"lookback_days": 2200, "tail": 60,  "candles": 36,  "display": "1 Tháng", "date_fmt": "%Y-%m",       "tick_every": 4,  "group": "longterm"},
}

def get_timeframe_cfg(interval: str) -> dict:
    """Return TIMEFRAME_CONFIG entry, falling back to 1d defaults."""
    return TIMEFRAME_CONFIG.get(interval, TIMEFRAME_CONFIG["1d"])

DATA_SOURCES = ["KBS", "FMP", "VCI"]
# Preferred source order for intraday (avoid VCI which only serves daily)
INTRADAY_SOURCES = ["MSN", "KBS", "VCI"]

_cache: dict = {}
CACHE_TTL_SECONDS = 300          # 5 minutes

_vnstock_ok: Optional[bool] = None
_symbol_cache: Optional[List[dict]] = None
_symbol_cache_ts: float = 0.0
SYMBOL_CACHE_TTL = 3600          # 1 hour

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
}

# ── Stock code filter ─────────────────────────────────────────────────────────
_STOCK_CODE_RE = re.compile(
    r'^[A-Z]{2,5}[0-9]?$'
    r'|^E1VF[A-Z0-9]{2,6}$'
)
_DERIVATIVE_RE = re.compile(
    r'^C[A-Z]{2,4}\d{4}$'
    r'|^VN30F\d{4}$'
    r'|^[A-Z]{2,5}\d{4,}$'
)


def _is_pure_stock(code: str, name: str = "") -> bool:
    if not code:
        return False
    if _DERIVATIVE_RE.match(code):
        return False
    name_lower = name.lower()
    for kw in ("chứng quyền", "warrant", "futures", "hợp đồng tương lai",
               "trái phiếu", "bond", "vn30f"):
        if kw in name_lower:
            return False
    return bool(_STOCK_CODE_RE.match(code))


# ── Availability check ────────────────────────────────────────────────────────

def check_vnstock_available() -> bool:
    global _vnstock_ok
    if _vnstock_ok is not None:
        return _vnstock_ok
    try:
        import vnstock  # noqa: F401
        _vnstock_ok = True
        print("[RealtimeLoader] vnstock ✓")
    except ImportError:
        _vnstock_ok = False
        print("[RealtimeLoader] vnstock chưa cài — pip install vnstock")
    return _vnstock_ok


# ── PRIMARY: Public REST APIs ─────────────────────────────────────────────────

def _fetch_vndirect(exchange: str, timeout: int = 12) -> List[dict]:
    """VNDirect finfo API — nguồn ổn định nhất, trả ~400/350/1100 mã."""
    try:
        url = (
            f"https://api-finfo.vndirect.com.vn/v4/stocks"
            f"?q=floor:{exchange.upper()}&size=2000&fields=code,companyName,floor"
        )
        r = requests.get(url, headers=_HEADERS, timeout=timeout)
        if r.status_code != 200:
            return []
        result = []
        for item in r.json().get("data", []):
            code = (item.get("code") or "").strip().upper()
            name = (item.get("companyName") or "").strip()
            if code and _is_pure_stock(code, name):
                result.append({
                    "code":     code,
                    "name":     name,
                    "exchange": (item.get("floor") or exchange).upper(),
                })
        if result:
            print(f"[VNDirect] {exchange.upper()}: {len(result)} mã")
        return result
    except Exception as e:
        print(f"[VNDirect] {exchange}: lỗi - {e}")
        return []


def _fetch_ssi(exchange: str, timeout: int = 12) -> List[dict]:
    """SSI iBoard API."""
    try:
        url = "https://iboard-query.ssi.com.vn/v2/stock/company/listed-companies"
        r = requests.get(
            url,
            params={"exchange": exchange.upper(), "size": 2000, "page": 0},
            headers=_HEADERS,
            timeout=timeout,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        items = data.get("data", data.get("items", []))
        result = []
        for item in items:
            code = (
                item.get("symbol") or item.get("code") or item.get("stockCode") or ""
            ).strip().upper()
            name = (
                item.get("organName") or item.get("companyName") or item.get("name") or ""
            ).strip()
            if code and _is_pure_stock(code, name):
                result.append({"code": code, "name": name, "exchange": exchange.upper()})
        if result:
            print(f"[SSI iBoard] {exchange.upper()}: {len(result)} mã")
        return result
    except Exception:
        return []


def _fetch_tcbs_listing(exchange: str, timeout: int = 12) -> List[dict]:
    """TCBS listing API."""
    try:
        url = (
            f"https://apipubaws.tcbs.com.vn/stock-insight/v2/stock/ticker-list"
            f"?exchange={exchange.upper()}"
        )
        r = requests.get(url, headers=_HEADERS, timeout=timeout)
        if r.status_code != 200:
            return []
        result = []
        for item in r.json().get("data", []):
            code = (item.get("ticker") or item.get("symbol") or "").strip().upper()
            name = (item.get("organName") or "").strip()
            if code and _is_pure_stock(code, name):
                result.append({"code": code, "name": name, "exchange": exchange.upper()})
        if result:
            print(f"[TCBS] {exchange.upper()}: {len(result)} mã")
        return result
    except Exception:
        return []


def _fetch_exchange_symbols(exchange: str) -> List[dict]:
    """Thử từng REST API theo thứ tự ưu tiên."""
    for fn in (_fetch_vndirect, _fetch_ssi, _fetch_tcbs_listing):
        result = fn(exchange)
        if result:
            return result
    return []


# ── SECONDARY: vnstock listing (thử im lặng nhiều phiên bản) ─────────────────

def _try_vnstock_listing_silent() -> List[dict]:
    """
    Thử tất cả cách gọi vnstock listing một cách im lặng.
    Không in lỗi ra ngoài — nếu thất bại thì trả list rỗng.
    Tương thích vnstock 2.x, 3.0.x, 3.1.x+.
    """
    if not check_vnstock_available():
        return []

    result: List[dict] = []
    seen: set = set()

    def _add(code, name, exch):
        code = str(code or "").strip().upper()
        name = str(name or "").strip()
        exch = str(exch or "").strip().upper()
        if code and code not in seen and _is_pure_stock(code, name):
            seen.add(code)
            result.append({"code": code, "name": name, "exchange": exch})

    def _normalise_df(df):
        if df is None or df.empty:
            return None
        col_map = {}
        for col in df.columns:
            lc = col.lower().replace("_", "").replace(" ", "")
            if lc in ("ticker", "symbol", "code", "stockcode"):
                col_map[col] = "code"
            elif lc in ("organname", "companyname", "name", "fullname"):
                col_map[col] = "name"
            elif lc in ("exchange", "comgroupcode", "floor", "market"):
                col_map[col] = "exchange"
        return df.rename(columns=col_map)

    try:
        from vnstock import Vnstock  # type: ignore

        # ── Pattern A: vnstock >= 3.1 — listing via stock object ─────────
        for src in ("KBS", "FMP", "VCI", "TCBS"):
            try:
                stock = Vnstock().stock(symbol="ACB", source=src)
                if hasattr(stock, "listing"):
                    try:
                        df = stock.listing.all_symbols(show=False)
                    except TypeError:
                        df = stock.listing.all_symbols()
                    df = _normalise_df(df)
                    if df is not None:
                        for _, row in df.iterrows():
                            _add(row.get("code"), row.get("name"), row.get("exchange", ""))
                        if result:
                            print(f"[vnstock listing] stock.listing.all_symbols ({src}): {len(result)} mã ✓")
                            return result
            except Exception:
                pass

        # ── Pattern B: vnstock 3.0.x — Vnstock().listing() ────────────────
        try:
            obj = Vnstock()
            if hasattr(obj, "listing"):
                listing = obj.listing()
                # all_symbols
                for method_name in ("all_symbols", "symbols_by_exchange", "all_listings"):
                    if hasattr(listing, method_name):
                        try:
                            if method_name == "symbols_by_exchange":
                                for exch in ("HOSE", "HNX", "UPCOM"):
                                    try:
                                        df = _normalise_df(listing.symbols_by_exchange(exchange=exch, show=False))
                                    except TypeError:
                                        df = _normalise_df(listing.symbols_by_exchange(exchange=exch))
                                    if df is not None:
                                        for _, row in df.iterrows():
                                            _add(row.get("code"), row.get("name"), exch)
                            else:
                                try:
                                    df = _normalise_df(getattr(listing, method_name)(show=False))
                                except TypeError:
                                    df = _normalise_df(getattr(listing, method_name)())
                                if df is not None:
                                    for _, row in df.iterrows():
                                        _add(row.get("code"), row.get("name"), row.get("exchange", ""))
                            if result:
                                print(f"[vnstock listing] {method_name}: {len(result)} mã ✓")
                                return result
                        except Exception:
                            pass
        except Exception:
            pass

        # ── Pattern C: vnstock 2.x — direct module functions ──────────────
        try:
            import vnstock as vns  # type: ignore
            for fn_name in ("listing_companies", "all_tickers", "get_all_tickers"):
                fn = getattr(vns, fn_name, None)
                if fn:
                    try:
                        df = _normalise_df(fn())
                        if df is not None:
                            for _, row in df.iterrows():
                                _add(row.get("code"), row.get("name"), row.get("exchange", ""))
                            if result:
                                print(f"[vnstock listing] {fn_name}: {len(result)} mã ✓")
                                return result
                    except Exception:
                        pass
        except Exception:
            pass

    except Exception:
        pass

    return result  # [] nếu mọi cách đều thất bại


# ── TERTIARY: Comprehensive hardcoded fallback (300+ mã) ─────────────────────

def _get_fallback_symbols() -> List[dict]:
    """
    Danh sách dự phòng — VN30, VN100, và các mã phổ biến.
    Chỉ dùng khi mọi API đều thất bại.
    """
    data = [
        # VN30 — HOSE
        ("ACB","Ngân hàng TMCP Á Châu","HOSE"),
        ("BCM","Tổng Công ty Đầu tư và Phát triển Công nghiệp","HOSE"),
        ("BID","Ngân hàng TMCP Đầu tư và Phát triển Việt Nam","HOSE"),
        ("BVH","Tập đoàn Bảo Việt","HOSE"),
        ("CTG","Ngân hàng TMCP Công thương Việt Nam","HOSE"),
        ("FPT","Công ty Cổ phần FPT","HOSE"),
        ("GAS","Tổng Công ty Khí Việt Nam","HOSE"),
        ("GVR","Tập đoàn Công nghiệp Cao su Việt Nam","HOSE"),
        ("HDB","Ngân hàng TMCP Phát triển TP.HCM","HOSE"),
        ("HPG","Công ty Cổ phần Tập đoàn Hòa Phát","HOSE"),
        ("MBB","Ngân hàng TMCP Quân đội","HOSE"),
        ("MSN","Công ty Cổ phần Tập đoàn Masan","HOSE"),
        ("MWG","Công ty Cổ phần Đầu tư Thế Giới Di Động","HOSE"),
        ("NVL","Công ty Cổ phần Tập đoàn No Va","HOSE"),
        ("PDR","Công ty Cổ phần Phát triển BĐS Phát Đạt","HOSE"),
        ("PLX","Tập đoàn Xăng dầu Việt Nam","HOSE"),
        ("POW","Tổng Công ty Điện lực Dầu khí Việt Nam","HOSE"),
        ("SAB","Tổng Công ty Bia Rượu Nước Giải Khát Sài Gòn","HOSE"),
        ("SSI","Công ty Cổ phần Chứng khoán SSI","HOSE"),
        ("STB","Ngân hàng TMCP Sài Gòn Thương Tín","HOSE"),
        ("TCB","Ngân hàng TMCP Kỹ thương Việt Nam","HOSE"),
        ("TPB","Ngân hàng TMCP Tiên Phong","HOSE"),
        ("VCB","Ngân hàng TMCP Ngoại thương Việt Nam","HOSE"),
        ("VHM","Công ty Cổ phần Vinhomes","HOSE"),
        ("VIB","Ngân hàng TMCP Quốc tế Việt Nam","HOSE"),
        ("VIC","Tập đoàn Vingroup","HOSE"),
        ("VJC","Công ty Cổ phần Hàng không VietJet","HOSE"),
        ("VNM","Công ty Cổ phần Sữa Việt Nam","HOSE"),
        ("VPB","Ngân hàng TMCP Việt Nam Thịnh Vượng","HOSE"),
        ("VRE","Công ty Cổ phần Vincom Retail","HOSE"),
        # HOSE khác
        ("AGG","Công ty Cổ phần Đầu tư IDJ Việt Nam","HOSE"),
        ("AGR","Công ty Cổ phần Chứng khoán Agribank","HOSE"),
        ("ANV","Công ty Cổ phần Nam Việt","HOSE"),
        ("BWE","Công ty Cổ phần Cấp Thoát nước Bình Dương","HOSE"),
        ("CII","Công ty Cổ phần Đầu tư Hạ tầng Kỹ thuật TP.HCM","HOSE"),
        ("CTD","Công ty Cổ phần Xây dựng Coteccons","HOSE"),
        ("DCM","Công ty Cổ phần Phân bón Dầu khí Cà Mau","HOSE"),
        ("DGC","Công ty Cổ phần Tập đoàn Hóa chất Đức Giang","HOSE"),
        ("DGW","Công ty Cổ phần Thế Giới Số","HOSE"),
        ("DPM","Tổng Công ty Phân bón và Hóa chất Dầu khí","HOSE"),
        ("DXG","Công ty Cổ phần Tập đoàn Đất Xanh","HOSE"),
        ("EIB","Ngân hàng TMCP Xuất Nhập khẩu Việt Nam","HOSE"),
        ("GEX","Công ty Cổ phần Tập đoàn GELEX","HOSE"),
        ("GMD","Công ty Cổ phần Gemadept","HOSE"),
        ("HAG","Công ty Cổ phần Hoàng Anh Gia Lai","HOSE"),
        ("HAH","Công ty Cổ phần Vận tải và Xếp dỡ Hải An","HOSE"),
        ("HBC","Công ty Cổ phần Xây dựng và Kinh doanh Địa ốc Hòa Bình","HOSE"),
        ("HCM","Công ty Cổ phần Chứng khoán TP.HCM","HOSE"),
        ("HDG","Công ty Cổ phần Tập đoàn Hà Đô","HOSE"),
        ("HSG","Công ty Cổ phần Tập đoàn Hoa Sen","HOSE"),
        ("HVN","Tổng Công ty Hàng không Việt Nam","HOSE"),
        ("IDC","Tổng Công ty IDICO","HOSE"),
        ("IMP","Công ty Cổ phần Dược phẩm Imexpharm","HOSE"),
        ("KBC","Tổng Công ty Phát triển Đô thị Kinh Bắc","HOSE"),
        ("KDC","Công ty Cổ phần Tập đoàn KIDO","HOSE"),
        ("KDH","Công ty Cổ phần Đầu tư và Kinh doanh Nhà Khang Điền","HOSE"),
        ("LPB","Ngân hàng TMCP Bưu điện Liên Việt","HOSE"),
        ("MSB","Ngân hàng TMCP Hàng Hải Việt Nam","HOSE"),
        ("NAB","Ngân hàng TMCP Nam Á","HOSE"),
        ("NKG","Công ty Cổ phần Thép Nam Kim","HOSE"),
        ("NLG","Công ty Cổ phần Đầu tư Nam Long","HOSE"),
        ("NT2","Công ty Cổ phần Điện lực Dầu khí Nhơn Trạch 2","HOSE"),
        ("OCB","Ngân hàng TMCP Phương Đông","HOSE"),
        ("PAN","Công ty Cổ phần Tập đoàn PAN","HOSE"),
        ("PC1","Công ty Cổ phần Xây lắp Điện 1","HOSE"),
        ("PHR","Công ty Cổ phần Cao su Phước Hòa","HOSE"),
        ("PNJ","Công ty Cổ phần Vàng bạc Đá quý Phú Nhuận","HOSE"),
        ("PVD","Tổng Công ty Cổ phần Khoan và Dịch vụ Khoan Dầu khí","HOSE"),
        ("PVT","Tổng Công ty Cổ phần Vận tải Dầu khí","HOSE"),
        ("QNS","Công ty Cổ phần Đường Quảng Ngãi","HOSE"),
        ("REE","Công ty Cổ phần Cơ Điện Lạnh","HOSE"),
        ("SBT","Công ty Cổ phần Thành Thành Công - Biên Hòa","HOSE"),
        ("SHB","Ngân hàng TMCP Sài Gòn Hà Nội","HOSE"),
        ("SHS","Công ty Cổ phần Chứng khoán Sài Gòn Hà Nội","HOSE"),
        ("TCH","Công ty Cổ phần Đầu tư Dịch vụ Tài chính Hoàng Huy","HOSE"),
        ("TCM","Công ty Cổ phần Dệt may - Đầu tư - Thương mại Thành Công","HOSE"),
        ("TLG","Công ty Cổ phần Tập đoàn Thiên Long","HOSE"),
        ("TRA","Công ty Cổ phần Traphaco","HOSE"),
        ("VCI","Công ty Cổ phần Chứng khoán Bản Việt","HOSE"),
        ("VGC","Tổng Công ty Viglacera","HOSE"),
        ("VHC","Công ty Cổ phần Vĩnh Hoàn","HOSE"),
        ("VIX","Công ty Cổ phần Chứng khoán IIX","HOSE"),
        ("VND","Công ty Cổ phần Chứng khoán VNDIRECT","HOSE"),
        ("VTP","Công ty Cổ phần Bưu chính Viettel","HOSE"),
        # HNX
        ("BCC","Công ty Cổ phần Xi măng Bỉm Sơn","HNX"),
        ("BHN","Tổng Công ty CP Bia - Rượu - NGK Hà Nội","HNX"),
        ("CEO","Công ty Cổ phần Tập đoàn C.E.O","HNX"),
        ("DHT","Công ty Cổ phần Dược phẩm Hà Tây","HNX"),
        ("HUT","Công ty Cổ phần Tasco","HNX"),
        ("NTP","Công ty Cổ phần Nhựa Thiếu niên Tiền Phong","HNX"),
        ("NVB","Ngân hàng TMCP Quốc Dân","HNX"),
        ("OIL","Tổng Công ty Dầu Việt Nam","HNX"),
        ("PLC","Tổng Công ty Hoá dầu Petrolimex","HNX"),
        ("PVS","Tổng Công ty Cổ phần Dịch vụ Kỹ thuật Dầu khí Việt Nam","HNX"),
        ("SLS","Công ty Cổ phần Mía đường Sơn La","HNX"),
        ("SSB","Ngân hàng TMCP Đông Nam Á","HNX"),
        ("TNG","Công ty Cổ phần Đầu tư và Thương mại TNG","HNX"),
        ("TMS","Công ty Cổ phần Transimex","HNX"),
        ("VCS","Công ty Cổ phần Vicostone","HNX"),
        ("VNR","Tổng Công ty Cổ phần Tái bảo hiểm Quốc gia Việt Nam","HNX"),
        # UPCOM
        ("ACV","Tổng Công ty Cảng hàng không Việt Nam","UPCOM"),
        ("BAB","Ngân hàng TMCP Bắc Á","UPCOM"),
        ("BAF","Công ty Cổ phần Nông nghiệp BaF Việt Nam","UPCOM"),
        ("BSR","Công ty Cổ phần Lọc hóa dầu Bình Sơn","UPCOM"),
        ("CMC","Công ty Cổ phần Tập đoàn CMC","UPCOM"),
        ("GSM","Công ty Cổ phần Di chuyển Xanh và Thông minh","UPCOM"),
        ("MCH","Công ty Cổ phần Hàng tiêu dùng Masan","UPCOM"),
        ("MMS","Công ty Cổ phần Masan MEATLife","UPCOM"),
        ("MSR","Công ty Cổ phần Masan High-Tech Materials","UPCOM"),
        ("NCB","Ngân hàng TMCP Quốc dân","UPCOM"),
        ("PAB","Ngân hàng TMCP Dầu khí Toàn cầu","UPCOM"),
        ("PME","Công ty Cổ phần Dược phẩm Pymepharco","UPCOM"),
        ("PSI","Công ty Cổ phần Chứng khoán Dầu khí","UPCOM"),
        ("RAL","Công ty Cổ phần Bóng đèn Phích nước Rạng Đông","UPCOM"),
        ("SAM","Công ty Cổ phần SAM Holdings","UPCOM"),
        ("SGN","Công ty Cổ phần Phục vụ Mặt đất Sài Gòn","UPCOM"),
        ("THD","Công ty Cổ phần Thaiholdings","UPCOM"),
        ("VEA","Tổng Công ty Máy động lực và Máy nông nghiệp Việt Nam","UPCOM"),
        ("VGI","Tổng Công ty Cổ phần Đầu tư Quốc tế Viettel","UPCOM"),
    ]
    return [{"code": c, "name": n, "exchange": e} for c, n, e in data]


# ── Master symbol fetcher ─────────────────────────────────────────────────────

def fetch_dstock_all_symbols(force_refresh: bool = False) -> List[dict]:
    """
    Lấy tất cả mã cổ phiếu.
    Ưu tiên: REST APIs công khai → vnstock listing → fallback hardcoded.
    Kết quả cache RAM 1 giờ.
    """
    global _symbol_cache, _symbol_cache_ts

    now = time.time()
    if (
        not force_refresh
        and _symbol_cache is not None
        and (now - _symbol_cache_ts) < SYMBOL_CACHE_TTL
    ):
        return _symbol_cache

    print("[RealtimeLoader] Đang tải danh sách mã cổ phiếu...")
    all_symbols: List[dict] = []
    seen: set = set()

    def _merge(items):
        added = 0
        for item in items:
            code = item.get("code", "")
            if code and code not in seen:
                seen.add(code)
                all_symbols.append(item)
                added += 1
        return added

    # ── Bước 1: REST APIs công khai (ổn định, không cần thư viện) ────────────
    for exchange in ("HOSE", "HNX", "UPCOM"):
        symbols = _fetch_exchange_symbols(exchange)
        n = _merge(symbols)
        if n:
            print(f"[RealtimeLoader] REST API {exchange}: +{n} mã")

    # ── Bước 2: vnstock listing (bổ sung thêm nếu REST thiếu) ────────────────
    if len(all_symbols) < 1500:
        vnstock_symbols = _try_vnstock_listing_silent()
        if vnstock_symbols:
            n = _merge(vnstock_symbols)
            if n:
                print(f"[RealtimeLoader] vnstock listing: +{n} mã bổ sung")

    # ── Bước 3: Fallback hardcoded nếu vẫn thiếu ─────────────────────────────
    if len(all_symbols) < 50:
        print("[RealtimeLoader] Tất cả API thất bại — dùng fallback hardcoded")
        n = _merge(_get_fallback_symbols())
        print(f"[RealtimeLoader] Fallback: {n} mã")
    else:
        # Merge fallback để không bỏ sót mã quan trọng
        n = _merge(_get_fallback_symbols())
        if n:
            print(f"[RealtimeLoader] Merge fallback: +{n} mã bổ sung")

    all_symbols.sort(key=lambda x: x["code"])
    _symbol_cache    = all_symbols
    _symbol_cache_ts = now
    print(f"[RealtimeLoader] ✓ Tổng {len(all_symbols)} mã sẵn sàng")
    return all_symbols


# ── Public symbol API ─────────────────────────────────────────────────────────

def get_all_symbols_realtime() -> List[dict]:
    try:
        return fetch_dstock_all_symbols()
    except Exception as exc:
        print(f"[RealtimeLoader] Lỗi tải danh sách: {exc}")
        return _get_fallback_symbols()


# ── Cache management ──────────────────────────────────────────────────────────

def clear_cache(symbol: Optional[str] = None, interval: Optional[str] = None) -> None:
    if symbol and interval:
        _cache.pop((symbol.upper(), interval), None)
    else:
        _cache.clear()
    print("[RealtimeLoader] Cache đã xóa.")


def get_cache_info() -> dict:
    now = time.time()
    return {
        "ttl_seconds": CACHE_TTL_SECONDS,
        "entries": [
            {
                "symbol":   sym,
                "interval": ivl,
                "rows":     len(df),
                "age_sec":  int(now - ts),
                "expired":  (now - ts) >= CACHE_TTL_SECONDS,
            }
            for (sym, ivl), (ts, df) in _cache.items()
        ],
    }


# ── Realtime status ───────────────────────────────────────────────────────────

def get_realtime_status() -> dict:
    available = check_vnstock_available()
    status = {
        "available":    available,
        "library":      "vnstock",
        "sources":      DATA_SOURCES,
        "cache_ttl":    CACHE_TTL_SECONDS,
        "cached_items": len(_cache),
    }
    if not available:
        status["install_cmd"] = "pip install vnstock"
        return status

    try:
        from vnstock import Vnstock  # type: ignore

        test_end   = datetime.now().strftime("%Y-%m-%d")
        test_start = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        connected = False
        test_rows = 0
        for src in DATA_SOURCES:
            try:
                stock   = Vnstock().stock(symbol="VNM", source=src)
                test_df = stock.quote.history(start=test_start, end=test_end, interval="1D")
                if test_df is not None and not test_df.empty:
                    connected = True
                    test_rows = len(test_df)
                    status["connected_via"] = src
                    break
            except Exception:
                continue

        status["connected"]   = connected
        status["test_symbol"] = "VNM"
        status["test_rows"]   = test_rows
        if not connected:
            status["error"] = f"Tất cả nguồn dữ liệu thất bại: {DATA_SOURCES}"

    except Exception as exc:
        status["connected"] = False
        status["error"]     = str(exc)

    return status


# ── Column normaliser ─────────────────────────────────────────────────────────

def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename: dict = {}
    for col in df.columns:
        lc = col.strip().lower()
        if lc in ("time", "date", "datetime", "tradingdate", "trading_date"):
            rename[col] = "Datetime"
        elif lc == "open":
            rename[col] = "Open"
        elif lc == "high":
            rename[col] = "High"
        elif lc == "low":
            rename[col] = "Low"
        elif lc == "close":
            rename[col] = "Close"
    return df.rename(columns=rename)


# ── OHLCV fallback: TCBS REST API ─────────────────────────────────────────────

def _fetch_ohlcv_tcbs(symbol: str, from_ts: int, to_ts: int, resolution: str = "D") -> pd.DataFrame:
    """Lấy OHLCV từ TCBS REST API khi vnstock không khả dụng."""
    try:
        url = (
            f"https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term"
            f"?ticker={symbol}&type=stock&resolution={resolution}"
            f"&from={from_ts}&to={to_ts}"
        )
        r = requests.get(url, headers=_HEADERS, timeout=15)
        if r.status_code != 200:
            return pd.DataFrame()
        data = r.json().get("data", [])
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        # TCBS columns: tradingDate, open, high, low, close, volume
        col_map = {
            "tradingDate": "Datetime",
            "open":        "Open",
            "high":        "High",
            "low":         "Low",
            "close":       "Close",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        if "Datetime" not in df.columns and "t" in df.columns:
            df["Datetime"] = pd.to_datetime(df["t"], unit="s")
        return df
    except Exception:
        return pd.DataFrame()


def _fetch_ohlcv_ssi(symbol: str, from_date: str, to_date: str) -> pd.DataFrame:
    """Lấy OHLCV từ SSI iBoard khi vnstock không khả dụng."""
    try:
        url = "https://iboard-query.ssi.com.vn/v2/stock/historical"
        params = {
            "symbol":    symbol.upper(),
            "startDate": from_date,
            "endDate":   to_date,
            "offset":    0,
            "limit":     500,
        }
        r = requests.get(url, params=params, headers=_HEADERS, timeout=15)
        if r.status_code != 200:
            return pd.DataFrame()
        items = r.json().get("data", [])
        if not items:
            return pd.DataFrame()
        df = pd.DataFrame(items)
        col_map = {
            "tradingDate": "Datetime", "openPrice": "Open",
            "highPrice": "High", "lowPrice": "Low", "closePrice": "Close",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        return df
    except Exception:
        return pd.DataFrame()


# ── Core OHLCV fetcher ────────────────────────────────────────────────────────

def _fetch_from_vnstock(
    symbol: str,
    start: str,
    end: str,
    interval_str: str,
    source: str,
) -> pd.DataFrame:
    from vnstock import Vnstock  # type: ignore
    stock = Vnstock().stock(symbol=symbol.upper(), source=source)
    df = stock.quote.history(start=start, end=end, interval=interval_str)
    if df is None or df.empty:
        raise ValueError(f"Empty response from {source} for {symbol}")
    return df


# ── Intraday fetch via entrade REST (MSN backend) ─────────────────────────────

def _fetch_entrade_ohlcv(
    symbol: str, from_ts: int, to_ts: int, resolution: str
) -> pd.DataFrame:
    """
    Direct call to services.entrade.com.vn — the backend vnstock's MSN source
    uses internally.  Supports intraday resolutions: 1, 5, 15, 30, 60, D, W, M.
    Response shape: {"t":[unix], "o":[...], "h":[...], "l":[...], "c":[...], "v":[...]}
    """
    url = (
        "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
        f"?from={from_ts}&to={to_ts}&symbol={symbol.upper()}&resolution={resolution}"
    )
    try:
        r = requests.get(url, headers=_HEADERS, timeout=15)
        if r.status_code != 200:
            return pd.DataFrame()
        data = r.json()
        t_arr = data.get("t", [])
        if not t_arr:
            return pd.DataFrame()
        import pytz
        tz_vn = pytz.timezone("Asia/Ho_Chi_Minh")
        datetimes = (
            pd.to_datetime(t_arr, unit="s", utc=True)
              .tz_convert(tz_vn)
              .tz_localize(None)
        )
        df = pd.DataFrame({
            "Datetime": datetimes,
            "Open":     [float(v) for v in data.get("o", [])],
            "High":     [float(v) for v in data.get("h", [])],
            "Low":      [float(v) for v in data.get("l", [])],
            "Close":    [float(v) for v in data.get("c", [])],
        })
        return df.dropna(subset=["Datetime"]).reset_index(drop=True)
    except Exception as e:
        print(f"[entrade] {symbol} res={resolution}: {e}")
        return pd.DataFrame()


def _fetch_intraday(
    symbol: str, interval: str, start_dt, end_dt
) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Fetch intraday OHLCV for intervals in INTRADAY_INTERVALS.
    Strategy (in order):
      1. vnstock with MSN/KBS source (MSN maps to entrade internally)
      2. Direct entrade REST API (reliable, no auth required)
      3. vnstock VCI as last resort (may raise KeyError:'data' for intraday)
    """
    interval_str = INTERVAL_MAP.get(interval, "60")
    entrade_res  = ENTRADE_RES_MAP.get(interval, "60")
    start_str    = start_dt.strftime("%Y-%m-%d")
    end_str      = end_dt.strftime("%Y-%m-%d")
    last_err     = ""

    # ── 1. vnstock (MSN then KBS — avoid VCI for intraday) ───────────────────
    if check_vnstock_available():
        for src in INTRADAY_SOURCES:
            try:
                print(f"[RealtimeLoader] {symbol} intraday ← vnstock/{src} ({interval_str})")
                df = _fetch_from_vnstock(symbol, start_str, end_str, interval_str, src)
                if df is not None and not df.empty:
                    print(f"[RealtimeLoader] vnstock/{src} ✓ — {len(df)} rows")
                    return df, ""
            except KeyError as exc:
                # VCI throws KeyError:'data' for intraday — skip silently
                last_err = f"vnstock/{src}: unsupported interval (KeyError:{exc})"
                print(f"[RealtimeLoader] {last_err}")
            except Exception as exc:
                last_err = f"vnstock/{src}: {exc}"
                print(f"[RealtimeLoader] vnstock/{src} ✗ — {exc}")

    # ── 2. Direct entrade REST (MSN backend) ─────────────────────────────────
    from_ts = int(start_dt.timestamp())
    to_ts   = int(end_dt.timestamp())
    print(f"[RealtimeLoader] {symbol} intraday ← entrade REST ({entrade_res})")
    df_ent = _fetch_entrade_ohlcv(symbol, from_ts, to_ts, entrade_res)
    if not df_ent.empty:
        print(f"[RealtimeLoader] entrade ✓ — {len(df_ent)} rows")
        return df_ent, ""
    last_err += " | entrade: empty response"

    return None, last_err


def fetch_realtime_ohlcv(
    symbol: str,
    interval: str = "1d",
    lookback_days: int = None,   # None → auto from TIMEFRAME_CONFIG
    tail: int = None,            # None → auto from TIMEFRAME_CONFIG
    use_cache: bool = True,
) -> Tuple[pd.DataFrame, str]:
    """
    Lấy dữ liệu OHLCV theo thứ tự:
      Intraday  → vnstock MSN/KBS → entrade REST → error
      Daily+    → vnstock (KBS/FMP/VCI) → TCBS REST → SSI REST → error
    """
    cfg = get_timeframe_cfg(interval)
    if lookback_days is None:
        lookback_days = cfg["lookback_days"]
    if tail is None:
        tail = cfg["tail"]

    cache_key = (symbol.upper(), interval)
    if use_cache and cache_key in _cache:
        ts, cached_df = _cache[cache_key]
        if time.time() - ts < CACHE_TTL_SECONDS:
            print(f"[RealtimeLoader] Cache hit: {symbol} ({interval})")
            return cached_df.tail(tail).reset_index(drop=True), ""

    end_dt   = datetime.now()
    start_dt = end_dt - timedelta(days=lookback_days)
    end_str  = end_dt.strftime("%Y-%m-%d")
    start_str = start_dt.strftime("%Y-%m-%d")
    interval_str = INTERVAL_MAP.get(interval, "1D")

    df_raw: Optional[pd.DataFrame] = None
    last_err = ""

    # ── Route intraday separately ─────────────────────────────────────────────
    if interval in INTRADAY_INTERVALS:
        df_raw, last_err = _fetch_intraday(symbol, interval, start_dt, end_dt)
        if df_raw is None or df_raw.empty:
            return pd.DataFrame(), (
                f"Không lấy được dữ liệu intraday {interval} cho {symbol}. "
                f"Lỗi: {last_err}"
            )
        # normalise & cache then return
        df_raw = _normalise_columns(df_raw)
        missing = [c for c in REQUIRED_COLS if c not in df_raw.columns]
        if missing:
            return pd.DataFrame(), f"Thiếu cột: {missing}"
        df_raw["Datetime"] = pd.to_datetime(df_raw["Datetime"], errors="coerce")
        df_raw = (
            df_raw.dropna(subset=["Datetime"])
                  .sort_values("Datetime")
                  .reset_index(drop=True)
        )
        df_clean = df_raw[REQUIRED_COLS].copy()
        _cache[cache_key] = (time.time(), df_clean)
        return df_clean.tail(tail).reset_index(drop=True), ""

    # ── Daily / weekly / monthly: original multi-source logic ─────────────────
    if check_vnstock_available():
        for source in DATA_SOURCES:
            try:
                print(f"[RealtimeLoader] {symbol} ← vnstock/{source} ({interval_str})")
                df_raw = _fetch_from_vnstock(symbol, start_str, end_str, interval_str, source)
                print(f"[RealtimeLoader] vnstock/{source} ✓ — {len(df_raw)} rows")
                break
            except Exception as exc:
                last_err = f"vnstock/{source}: {exc}"
                print(f"[RealtimeLoader] vnstock/{source} ✗ — {exc}")

    # ── Nguồn 2: TCBS REST API ────────────────────────────────────────────────
    if df_raw is None or df_raw.empty:
        try:
            from_ts = int(start_dt.timestamp())
            to_ts   = int(end_dt.timestamp())
            print(f"[RealtimeLoader] {symbol} ← TCBS REST API")
            df_tcbs = _fetch_ohlcv_tcbs(symbol, from_ts, to_ts)
            if not df_tcbs.empty:
                df_raw = df_tcbs
                print(f"[RealtimeLoader] TCBS ✓ — {len(df_raw)} rows")
        except Exception as exc:
            last_err += f" | TCBS: {exc}"

    # ── Nguồn 3: SSI REST API ─────────────────────────────────────────────────
    if df_raw is None or df_raw.empty:
        try:
            print(f"[RealtimeLoader] {symbol} ← SSI REST API")
            df_ssi = _fetch_ohlcv_ssi(symbol, start_str, end_str)
            if not df_ssi.empty:
                df_raw = df_ssi
                print(f"[RealtimeLoader] SSI ✓ — {len(df_raw)} rows")
        except Exception as exc:
            last_err += f" | SSI: {exc}"

    if df_raw is None or df_raw.empty:
        return pd.DataFrame(), (
            f"Không lấy được dữ liệu cho {symbol}. Lỗi: {last_err}"
        )

    df_raw   = _normalise_columns(df_raw)
    missing  = [c for c in REQUIRED_COLS if c not in df_raw.columns]
    if missing:
        return pd.DataFrame(), (
            f"Thiếu cột: {missing}. Cột hiện có: {list(df_raw.columns)}"
        )

    df_raw["Datetime"] = pd.to_datetime(df_raw["Datetime"], errors="coerce")
    df_raw = (
        df_raw.dropna(subset=["Datetime"])
              .sort_values("Datetime")
              .reset_index(drop=True)
    )
    df_clean = df_raw[REQUIRED_COLS].copy()

    _cache[cache_key] = (time.time(), df_clean)
    return df_clean.tail(tail).reset_index(drop=True), ""


# ── Stock info (realtime) ─────────────────────────────────────────────────────

def get_stock_info_realtime(code: str) -> dict:
    code = code.strip().upper()
    base = {"code": code, "source": "realtime", "exists": False}

    cached = fetch_dstock_all_symbols()
    match  = next((s for s in cached if s.get("code") == code), None)
    if match:
        base.update({
            "exists":   True,
            "name":     match.get("name", ""),
            "exchange": match.get("exchange", ""),
        })

    if check_vnstock_available():
        try:
            from vnstock import Vnstock  # type: ignore
            for src in DATA_SOURCES:
                try:
                    stock   = Vnstock().stock(symbol=code, source=src)
                    profile = stock.company.profile()
                    if profile is not None and not profile.empty:
                        row = profile.iloc[0]
                        base.update({
                            "exists":        True,
                            "organ_name":    str(row.get("companyName",   "") or row.get("organ_name",   "") or ""),
                            "en_organ_name": str(row.get("companyNameEn", "") or row.get("en_organ_name", "") or ""),
                            "exchange":      str(row.get("exchange",      base.get("exchange", "")) or ""),
                            "industry":      str(row.get("industryName",  "") or ""),
                            "website":       str(row.get("website",       "") or ""),
                        })
                        break
                except Exception:
                    continue
        except Exception as e:
            base["profile_error"] = str(e)

    return base