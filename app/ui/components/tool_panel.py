from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout

from ..panels import AcrylicPanel
from ..design import BRAND_SOFT


def _icon_badge(icon_name: str) -> QLabel:
    lbl = QLabel()
    path = Path(__file__).resolve().parents[3] / "resources" / "icons" / f"{icon_name}.svg"
    lbl.setFixedSize(30, 30)
    lbl.setAlignment(Qt.AlignCenter)
    if path.exists():
        pix = QPixmap(str(path))
        if not pix.isNull():
            lbl.setPixmap(pix.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    lbl.setStyleSheet(f"background: {BRAND_SOFT}; border-radius: 9px;")
    return lbl


class ToolPanel(QWidget):
    """工具卡片：左对齐标题 + 常规/性能内容容器。"""

    def __init__(self, main_window, wallpaper):
        super().__init__()
        self._main_window = main_window
        self._wallpaper = wallpaper

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        acrylic = AcrylicPanel(self._wallpaper, blur_strength=10, white_alpha=0, corner_radius=14)
        layout.addWidget(acrylic)

        box = QVBoxLayout(acrylic)
        box.setContentsMargins(18, 16, 18, 16)
        box.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_icon = _icon_badge("tools")
        tool_title = QLabel("工具")
        tool_title.setObjectName("cardTitle")
        tool_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title_row.addWidget(title_icon)
        title_row.addWidget(tool_title)
        title_row.addStretch(1)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        box.addLayout(title_row)
        box.addWidget(content, 1)

        main_window.tool_panel = acrylic
        main_window.tool_title = tool_title
        main_window.tool_content = content
        main_window.tool_title_icon = title_icon

        self.acrylic = acrylic
        self.content = content
        self.content_layout = content_layout
