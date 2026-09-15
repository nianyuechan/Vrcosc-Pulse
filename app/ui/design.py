"""VRCOSC Pulse 品牌设计令牌（粉色强调体系，不随系统强调色漂移）。"""

from PySide6.QtGui import QColor

# 主强调
BRAND = "#F45B8A"
BRAND_HOVER = "#FF709B"
BRAND_PRESSED = "#DE4677"
BRAND_SOFT = "#FFF1F5"
BRAND_SOFT_2 = "#FFE4EC"

# 文字
TEXT = "#172033"
TEXT_SECONDARY = "#758095"
TEXT_MUTED = "#A7AFBD"

# 表面
CARD = "#FFFFFF"
BORDER = "#E7EAF0"
TRACK = "#E8EBEF"
PILL_BG = "#F3F5F8"

# 状态
SUCCESS = "#34B66A"
SUCCESS_SOFT = "#E8F8EF"
WARN = "#F03E75"
WARN_SOFT = "#FDE8F0"

# 深色模式对应
DARK_TEXT = "#F2F4F8"
DARK_SECONDARY = "#A8B0C0"
DARK_CARD = "rgba(255,255,255,0.06)"
DARK_BORDER = "rgba(255,255,255,0.12)"
DARK_PILL = "rgba(255,255,255,0.10)"


def brand_qcolor() -> QColor:
    return QColor(BRAND)


def rgba(hex_color: str, alpha: float) -> str:
    """#RRGGBB + 0~1 → rgba(...)"""
    c = QColor(hex_color)
    a = max(0, min(255, int(round(alpha * 255))))
    return f"rgba({c.red()},{c.green()},{c.blue()},{a})"
