from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QHBoxLayout, QPushButton, QSizePolicy,
)

from ..panels import AcrylicPanel
from ..design import BRAND_SOFT


def _icon_badge(icon_name: str) -> QLabel:
    """浅粉圆角图标底 + SVG。"""
    lbl = QLabel()
    path = Path(__file__).resolve().parents[3] / "resources" / "icons" / f"{icon_name}.svg"
    lbl.setFixedSize(30, 30)
    lbl.setAlignment(Qt.AlignCenter)
    if path.exists():
        lbl.setPixmap(_load_pixmap(str(path), 16))
    lbl.setStyleSheet(
        f"background: {BRAND_SOFT}; border-radius: 9px;"
    )
    return lbl


def _load_pixmap(path: str, size: int):
    from PySide6.QtGui import QPixmap
    pix = QPixmap(path)
    if pix.isNull():
        return QPixmap()
    return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class InputPanel(QWidget):
    """输入卡片：标题行 + 输入框 + 字数/清空 + 主发送按钮。"""

    def __init__(self, main_window, wallpaper):
        super().__init__()
        self._main_window = main_window
        self._wallpaper = wallpaper

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        acrylic = AcrylicPanel(self._wallpaper, blur_strength=14, white_alpha=0, corner_radius=14)
        layout.addWidget(acrylic)

        box = QVBoxLayout(acrylic)
        box.setContentsMargins(18, 16, 18, 16)
        box.setSpacing(10)

        # 标题行：图标 + 输入
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_icon = _icon_badge("input")
        in_title = QLabel("输入")
        in_title.setObjectName("cardTitle")
        in_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title_row.addWidget(title_icon)
        title_row.addWidget(in_title)
        title_row.addStretch(1)

        input_edit = QTextEdit()
        input_edit.setPlaceholderText("请输入要发送的消息…")
        input_edit.setObjectName("messageInput")
        input_edit.setMinimumHeight(120)

        char_count = QLabel("0 字")
        clear_input_btn = QPushButton("清空")
        clear_input_btn.setObjectName("ghostBtn")
        clear_input_btn.setCursor(Qt.PointingHandCursor)
        clear_input_btn.setFixedHeight(28)
        trash_icon = Path(__file__).resolve().parents[3] / "resources" / "icons" / "trash.svg"
        if trash_icon.exists():
            clear_input_btn.setIcon(QIcon(str(trash_icon)))
            clear_input_btn.setIconSize(QSize(14, 14))

        control_row = QHBoxLayout()
        control_row.setSpacing(8)
        control_row.addWidget(char_count)
        control_row.addStretch(1)
        control_row.addWidget(clear_input_btn)

        start_btn = QPushButton("开始发送")
        start_btn.setObjectName("primaryBtn")
        start_btn.setMinimumHeight(54)
        start_btn.setCursor(Qt.PointingHandCursor)
        start_btn.setEnabled(False)
        send_icon = Path(__file__).resolve().parents[3] / "resources" / "icons" / "send.svg"
        if send_icon.exists():
            start_btn.setIcon(QIcon(str(send_icon)))
            start_btn.setIconSize(QSize(18, 18))

        box.addLayout(title_row)
        box.addWidget(input_edit, 1)
        box.addLayout(control_row)
        box.addWidget(start_btn)

        main_window.input_panel = acrylic
        main_window.in_title = in_title
        main_window.input_edit = input_edit
        main_window.char_count = char_count
        main_window.start_btn = start_btn
        main_window.clear_input_btn = clear_input_btn
        main_window.input_title_icon = title_icon

        try:
            clear_input_btn.clicked.connect(self._on_clear)
        except Exception:
            pass
        try:
            input_edit.textChanged.connect(self._sync_send_enabled)
        except Exception:
            pass

        self.acrylic = acrylic

    def _on_clear(self):
        try:
            self._main_window.input_edit.clear()
        except Exception:
            pass

    def _sync_send_enabled(self):
        """空输入禁用发送按钮（不打断进行中的发送逻辑开关）。"""
        try:
            mw = self._main_window
            btn = mw.start_btn
            has_text = bool(mw.input_edit.toPlainText().strip())
            sending = bool(getattr(mw, "is_sending", False))
            btn.setEnabled(has_text or sending)
        except Exception:
            pass
