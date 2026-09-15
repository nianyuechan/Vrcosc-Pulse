from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QHBoxLayout, QPushButton, QStackedWidget,
)

from ..panels import AcrylicPanel
from ..design import BRAND_SOFT, TEXT_MUTED, TEXT_SECONDARY


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


class HistoryPanel(QWidget):
    """已发送卡片：标题行 + 清空记录 + 列表/空状态。"""

    def __init__(self, main_window, wallpaper):
        super().__init__()
        self._main_window = main_window
        self._wallpaper = wallpaper

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        acrylic = AcrylicPanel(self._wallpaper, blur_strength=12, white_alpha=0, corner_radius=14)
        layout.addWidget(acrylic)

        box = QVBoxLayout(acrylic)
        box.setContentsMargins(18, 16, 18, 16)
        box.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_icon = _icon_badge("history")
        hist_title = QLabel("OSC 实时预览")
        hist_title.setObjectName("cardTitle")
        hist_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        clear_history_btn = QPushButton("清空记录")
        clear_history_btn.setObjectName("ghostBtn")
        clear_history_btn.setCursor(Qt.PointingHandCursor)
        clear_history_btn.setFixedHeight(28)
        # 预览模式不再需要清空历史；保留对象避免其它引用失效
        clear_history_btn.hide()
        trash_icon = Path(__file__).resolve().parents[3] / "resources" / "icons" / "trash.svg"
        if trash_icon.exists():
            clear_history_btn.setIcon(QIcon(str(trash_icon)))
            clear_history_btn.setIconSize(QSize(14, 14))
        title_row.addWidget(title_icon)
        title_row.addWidget(hist_title)
        title_row.addStretch(1)
        title_row.addWidget(clear_history_btn)

        # 空状态：几何居中，避免图标/标题/提示视觉重心偏左
        empty_wrap = QWidget()
        empty_lay = QVBoxLayout(empty_wrap)
        empty_lay.setContentsMargins(24, 32, 24, 32)
        empty_lay.setSpacing(5)
        empty_lay.setAlignment(Qt.AlignCenter)

        empty_icon = QLabel()
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_icon.setFixedSize(52, 52)
        empty_icon_path = Path(__file__).resolve().parents[3] / "resources" / "icons" / "empty_history.svg"
        if empty_icon_path.exists():
            pix = QPixmap(str(empty_icon_path))
            if not pix.isNull():
                empty_icon.setPixmap(
                    pix.scaled(46, 46, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

        empty_title = QLabel("暂无 OSC 预览")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_title.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 15px; font-weight: 600;"
        )
        empty_hint = QLabel("输入消息后将在这里显示最终发送效果")
        empty_hint.setAlignment(Qt.AlignCenter)
        empty_hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 13px;"
        )

        empty_lay.addStretch(1)
        empty_lay.addWidget(empty_icon, 0, Qt.AlignHCenter)
        empty_lay.addWidget(empty_title, 0, Qt.AlignHCenter)
        empty_lay.addWidget(empty_hint, 0, Qt.AlignHCenter)
        empty_lay.addStretch(1)

        history_edit = QTextEdit()
        history_edit.setReadOnly(True)
        history_edit.setAcceptRichText(False)
        history_edit.setAlignment(Qt.AlignHCenter)
        history_edit.setFocusPolicy(Qt.NoFocus)
        history_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        history_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        history_edit.setObjectName("historyList")
        history_edit.setPlaceholderText("")

        stack = QStackedWidget()
        stack.addWidget(empty_wrap)   # 0 empty
        stack.addWidget(history_edit) # 1 list
        stack.setCurrentIndex(0)

        box.addLayout(title_row)
        box.addWidget(stack, 1)

        main_window.history_panel = acrylic
        main_window.hist_title = hist_title
        main_window.history_edit = history_edit
        main_window.history_stack = stack
        main_window.clear_history_btn = clear_history_btn
        main_window.history_empty = empty_wrap
        main_window.history_empty_icon = empty_icon
        main_window.history_empty_title = empty_title
        main_window.history_empty_hint = empty_hint
        main_window.history_title_icon = title_icon

        try:
            clear_history_btn.clicked.connect(self._on_clear)
        except Exception:
            pass

        self.acrylic = acrylic
        self.stack = stack

    def _on_clear(self):
        try:
            self._main_window.history_edit.clear()
            self._main_window.history_stack.setCurrentIndex(0)
        except Exception:
            pass

    def show_list_if_needed(self):
        try:
            if self.stack.currentIndex() != 1:
                self.stack.setCurrentIndex(1)
        except Exception:
            pass
