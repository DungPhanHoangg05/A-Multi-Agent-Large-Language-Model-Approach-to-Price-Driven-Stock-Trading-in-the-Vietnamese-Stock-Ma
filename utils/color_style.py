import mplfinance as mpf

font = {
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    "font.weight": "normal",
    "font.size": 15,
}

my_color_style = mpf.make_mpf_style(
    marketcolors=mpf.make_marketcolors(
        down="#A02128",  # Nến có Close < Open dùng thân đỏ.
        up="#006340",  # Nến có Close > Open dùng thân xanh lá.
        edge="none",  # Không vẽ viền thân nến.
        wick="black",  # Bóng nến màu đen.
        volume="in",  # Volume kế thừa màu nến của thư viện.
    ),
    gridstyle="-",
    facecolor="white",  # Nền biểu đồ màu trắng.
    rc=font,
)
