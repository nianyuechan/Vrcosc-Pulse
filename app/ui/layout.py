"""
UI布局管理器
负责创建和管理主窗口的所有UI组件布局
"""

import logging
from pathlib import Path
from typing import Dict, Any

from PySide6.QtCore import Qt, QSize, QPropertyAnimation
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QToolBox, QCheckBox, QSpinBox, QFrame,
    QLineEdit, QBoxLayout, QSizePolicy, QProgressBar,
)
from PySide6.QtGui import QFont, QPixmap, QIcon, QPainter, QPen, QColor

from ..ui.panels import AcrylicPanel
from ..ui.design import (
    BRAND, BRAND_SOFT, BRAND_SOFT_2, TEXT, TEXT_SECONDARY, TEXT_MUTED,
    PILL_BG, SUCCESS, SUCCESS_SOFT, WARN, BORDER, TRACK, rgba,
)
from .components import InputPanel, HistoryPanel, ToolPanel

logger = logging.getLogger(__name__)


def _icon_badge(icon_name: str) -> QLabel:
    """卡片标题图标：浅粉圆角底 + 品牌 SVG。"""
    lbl = QLabel()
    path = Path(__file__).resolve().parents[2] / "resources" / "icons" / f"{icon_name}.svg"
    lbl.setObjectName("titleIconBadge")
    lbl.setFixedSize(30, 30)
    lbl.setAlignment(Qt.AlignCenter)
    if path.exists():
        pix = QPixmap(str(path))
        if not pix.isNull():
            lbl.setPixmap(pix.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    lbl.setStyleSheet(f"background: {BRAND_SOFT}; border-radius: 9px;")
    return lbl


def _section_header(title: str, icon_name: str = "status", height: int = 38, radius: int = 9, object_name: str = "sectionHeader") -> QWidget:
    """带本地 SVG 的浅粉分组标题条，整行拉伸填满父布局宽度。"""
    box = QWidget()
    box.setObjectName(object_name)
    box.setFixedHeight(height)
    box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    lay = QHBoxLayout(box)
    lay.setContentsMargins(12, 0, 12, 0)
    lay.setSpacing(8)

    icon = QLabel()
    icon.setFixedSize(16, 16)
    icon.setAlignment(Qt.AlignCenter)
    icon.setStyleSheet("background: transparent;")
    path = Path(__file__).resolve().parents[2] / "resources" / "icons" / f"{icon_name}.svg"
    if path.exists():
        pix = QPixmap(str(path))
        if not pix.isNull():
            icon.setPixmap(pix.scaled(14, 14, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    text = QLabel(title)
    text.setObjectName("toolGroupTitleText" if object_name == "toolGroupTitle" else "sectionHeaderText")
    text.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    text.setStyleSheet("background: transparent;")
    lay.addWidget(icon, 0, Qt.AlignVCenter)
    lay.addWidget(text, 0, Qt.AlignVCenter)
    lay.addStretch(1)

    box._section_text_label = text
    box._section_icon_label = icon
    box._section_radius = radius
    # 初始样式；theme.apply_theme 会按 objectName 再覆盖一次
    if object_name == "toolGroupTitle":
        box.setStyleSheet(
            f"QWidget#toolGroupTitle {{ background-color: {BRAND_SOFT}; border: none; border-radius: {radius}px; }}"
            f"QLabel#toolGroupTitleText {{ color: {BRAND}; font-size: 13px; font-weight: 600; background: transparent; }}"
        )
    else:
        box.setStyleSheet(
            f"QWidget#{object_name} {{ background: {BRAND_SOFT}; border-radius: {radius}px; }}"
            f"QLabel#sectionHeaderText {{ color: {BRAND}; font-size: 14px; font-weight: 600; background: transparent; }}"
        )
    return box


def _status_pill(text: str = "", color: str | None = None) -> QLabel:
    """右侧调试值的状态胶囊。"""
    from ..ui.design import TEXT_SECONDARY as _sec
    pill = QLabel(text)
    pill.setObjectName("statusPill")
    pill.setAlignment(Qt.AlignCenter)
    pill.setMinimumHeight(28)
    pill.setMinimumWidth(68)
    pill.setMaximumWidth(220)
    pill.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    fg = color or _sec
    pill.setStyleSheet(
        f"background: {PILL_BG}; color: {fg}; border-radius: 8px; "
        f"padding: 1px 9px; font-size: 13px;"
    )
    return pill


def _set_pill_text(label: QLabel, text: str, color: str | None = None) -> None:
    """更新胶囊文本，并保留胶囊外观。"""
    from ..ui.design import TEXT_SECONDARY as _sec
    try:
        label.setText(text)
        fg = color or _sec
        label.setStyleSheet(
            f"background: {PILL_BG}; color: {fg}; border-radius: 8px; "
            f"padding: 2px 10px; font-size: 13px;"
        )
    except Exception:
        pass


class _TreeGuide(QWidget):
    """轻量树状引导线：明确展示父子设置层级。"""

    def __init__(self, last: bool = False, parent=None):
        super().__init__(parent)
        self._last = bool(last)
        self.setFixedWidth(22)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        pen = QPen(QColor(156, 166, 184, 120))
        pen.setWidth(1)
        pen.setStyle(Qt.DotLine)
        painter.setPen(pen)
        x = 7
        cy = self.height() // 2
        painter.drawLine(x, 0, x, cy if self._last else self.height())
        painter.drawLine(x, cy, 20, cy)


def _indent_widget(w: QWidget, px: int = 18, guide: bool = False, last: bool = False) -> QWidget:
    wrap = QWidget()
    lay = QHBoxLayout(wrap)
    lay.setContentsMargins(px, 0, 0, 0)
    lay.setSpacing(4 if guide else 0)
    if guide:
        lay.addWidget(_TreeGuide(last=last), 0)
    lay.addWidget(w)
    lay.addStretch(1)
    return wrap


class UILayoutManager:
    """UI布局管理器"""
    
    def __init__(self, main_window):
        """
        初始化布局管理器
        
        Args:
            main_window: 主窗口实例，用于访问壁纸和其他属性
        """
        self.main_window = main_window
        self.wallpaper = main_window.wallpaper
        
        # UI组件引用
        self.input_panel = None
        self.history_panel = None
        self.tool_panel = None
        self.debug_panel = None
        self.toolbox = None
        self.debug_labels = {}
        
    def create_input_panel(self) -> QWidget:
        """创建输入面板（组件化）"""
        comp = InputPanel(self.main_window, self.wallpaper)
        # 保存引用（AcrylicPanel 实例在 main_window.input_panel）
        self.input_panel = getattr(self.main_window, 'input_panel', None)
        return comp
    
    def create_history_panel(self) -> QWidget:
        """创建历史记录面板（组件化）"""
        comp = HistoryPanel(self.main_window, self.wallpaper)
        self.history_panel = getattr(self.main_window, 'history_panel', None)
        return comp
    
    def create_tool_panel(self) -> QWidget:
        """创建工具与设置面板（组件化），常规/性能两组上下平铺填充"""
        comp = ToolPanel(self.main_window, self.wallpaper)
        content = getattr(self.main_window, 'tool_content', None)
        if content is not None:
            self._create_general_group(content)

            # 常规 / 性能之间使用一条非常轻的分隔线。参考图里两组并不是
            # 直接相贴，分隔线能在不增加大块留白的情况下稳定层级。
            divider = QFrame()
            divider.setObjectName("toolGroupDivider")
            divider.setFrameShape(QFrame.HLine)
            divider.setFixedHeight(1)
            divider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            content.layout().addWidget(divider)
            self.main_window.tool_group_divider = divider

            self._create_performance_group(content)
        # 间隔/OSC/状态/倒计时已移入设置对话框，主窗口保留隐藏控件供逻辑使用
        self._create_hidden_status_widgets()
        self.tool_panel = getattr(self.main_window, 'tool_panel', None)
        return comp

    def _collect_group_title(self, title: QLabel) -> None:
        """收集工具面板组标题，供主题统一样式。"""
        titles = getattr(self.main_window, 'tool_group_titles', None)
        if titles is None:
            titles = []
            self.main_window.tool_group_titles = titles
        titles.append(title)
    
    def _create_general_group(self, parent: QWidget) -> None:
        """常规设置：粉色分组头 + 选项；选择设备挂在心率下。"""
        group = QWidget()
        gl = QVBoxLayout(group)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(3)

        group_title = _section_header("常规", "status", height=40, object_name="toolGroupTitle")
        self._collect_group_title(group_title)
        gl.addWidget(group_title, 0)
        gl.addSpacing(6)

        auto_wrap = QCheckBox("换行拼接附加信息")
        auto_time = QCheckBox("附加当前时间")
        auto_window = QCheckBox("附加当前窗口标题")
        auto_music = QCheckBox("附加正在播放音乐信息")
        auto_idle = QCheckBox("挂机检测（≥60秒追加提示）")
        auto_hr = QCheckBox("心率状态")
        console_toggle = QCheckBox("显示控制台")
        for cb in (auto_wrap, auto_time, auto_window, auto_music, auto_idle, auto_hr, console_toggle):
            cb.setChecked(False)
            cb.setMinimumHeight(38)

        # 选择设备：心率子控件（缩进）
        choose_hr_btn = QPushButton("选择设备")
        choose_hr_btn.setObjectName("secondaryBtn")
        choose_hr_btn.setCursor(Qt.PointingHandCursor)
        choose_hr_btn.setFixedSize(138, 32)
        choose_hr_btn.setEnabled(False)
        device_icon = Path(__file__).resolve().parents[2] / "resources" / "icons" / "device.svg"
        if device_icon.exists():
            choose_hr_btn.setIcon(QIcon(str(device_icon)))
            choose_hr_btn.setIconSize(QSize(15, 15))
        choose_hr_wrap = _indent_widget(choose_hr_btn, 18, guide=True, last=True)

        gl.addWidget(auto_wrap)
        gl.addWidget(auto_time)
        gl.addWidget(auto_window)
        gl.addWidget(auto_music)
        gl.addWidget(auto_idle)
        gl.addWidget(auto_hr)
        gl.addWidget(choose_hr_wrap)
        gl.addWidget(console_toggle)
        gl.addStretch(1)

        self.main_window.auto_wrap = auto_wrap
        self.main_window.auto_time = auto_time
        self.main_window.auto_window = auto_window
        self.main_window.auto_music = auto_music
        self.main_window.auto_idle = auto_idle
        self.main_window.auto_hr = auto_hr
        self.main_window.choose_hr_btn = choose_hr_btn
        self.main_window.console_toggle = console_toggle

        try:
            console_toggle.toggled.connect(self.main_window.on_toggle_console)
        except Exception:
            pass
        try:
            auto_hr.toggled.connect(self.main_window.on_toggle_hr)
            # 心率勾选才允许选择设备
            auto_hr.toggled.connect(choose_hr_btn.setEnabled)
        except Exception:
            pass
        try:
            choose_hr_btn.clicked.connect(self.main_window.on_choose_device)
        except Exception:
            pass

        if parent is not None:
            parent.layout().addWidget(group)

    def _create_performance_group(self, parent: QWidget) -> None:
        """性能设置：总开关 + 缩进子项（父子层级）。"""
        group = QWidget()
        pl = QVBoxLayout(group)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(3)

        group_title = _section_header("性能", "performance", height=40, object_name="toolGroupTitle")
        self._collect_group_title(group_title)
        pl.addWidget(group_title, 0)
        pl.addSpacing(6)

        auto_hardware = QCheckBox("附加硬件性能信息（CPU/RAM/GPU）")
        auto_hardware.setChecked(False)
        auto_hardware.setMinimumHeight(38)

        auto_cpu = QCheckBox("CPU 使用率")
        auto_ram = QCheckBox("RAM 使用率")
        auto_gpu = QCheckBox("GPU 使用率")
        auto_temp = QCheckBox("温度")
        for cb in (auto_cpu, auto_ram, auto_gpu, auto_temp):
            cb.setChecked(False)
            cb.setMinimumHeight(36)
            cb.setEnabled(False)

        pl.addWidget(auto_hardware)
        pl.addWidget(_indent_widget(auto_cpu, 18, guide=True))
        pl.addWidget(_indent_widget(auto_ram, 18, guide=True))
        pl.addWidget(_indent_widget(auto_gpu, 18, guide=True))
        pl.addWidget(_indent_widget(auto_temp, 18, guide=True, last=True))
        pl.addStretch(1)

        self.main_window.auto_hardware = auto_hardware
        self.main_window.auto_cpu = auto_cpu
        self.main_window.auto_ram = auto_ram
        self.main_window.auto_gpu = auto_gpu
        self.main_window.auto_temp = auto_temp

        def _sync_hw(enabled: bool):
            for cb in (auto_cpu, auto_ram, auto_gpu, auto_temp):
                cb.setEnabled(bool(enabled))

        try:
            auto_hardware.toggled.connect(_sync_hw)
        except Exception:
            pass

        if parent is not None:
            parent.layout().addWidget(group)
    
    def _create_hidden_status_widgets(self) -> None:
        """创建主窗口逻辑依赖、但界面不再显示的状态控件（隐藏保留）。

        “间隔/OSC/状态/倒计时”已移入设置对话框的“间隔”分区，
        主窗口各 mixin 仍引用这些属性，故保留隐藏实例避免 AttributeError。
        """
        spin_interval = QSpinBox()
        spin_interval.setRange(5, 3600)
        spin_interval.setValue(30)
        spin_interval.setSingleStep(5)

        osc_addr = QLineEdit("127.0.0.1:9000")
        osc_addr.setReadOnly(True)
        osc_addr.setFrame(False)
        osc_addr.setToolTip("OSC 地址固定为 127.0.0.1:9000")

        # 挂到主窗口但不加入任何可见布局
        for wgt in (spin_interval, osc_addr):
            try:
                wgt.setParent(self.main_window)
            except Exception:
                pass
            wgt.hide()

        # 保存引用（状态/倒计时已显示在 Header，由 MainWindow 创建）
        self.main_window.spin_interval = spin_interval
        self.main_window.osc_addr = osc_addr
    
    def create_debug_panel(self) -> QWidget:
        """创建调试信息面板"""
        debug_panel = QWidget()
        debug_layout = QVBoxLayout(debug_panel)
        debug_layout.setContentsMargins(0, 0, 0, 0)
        debug_layout.setSpacing(6)
        
        # 亚克力面板
        debug_acrylic = AcrylicPanel(self.wallpaper, blur_strength=10, white_alpha=0, corner_radius=14)
        debug_layout.addWidget(debug_acrylic)
        
        dbg_box = QVBoxLayout(debug_acrylic)
        dbg_box.setContentsMargins(18, 16, 18, 16)
        dbg_box.setSpacing(12)
        
        # 标题：与输入/工具/历史一致，使用左对齐图标标题行。
        dbg_title_row = QHBoxLayout()
        dbg_title_row.setSpacing(10)
        dbg_title_icon = _icon_badge("debug")
        dbg_title = QLabel("调试信息")
        dbg_title.setObjectName("cardTitle")
        dbg_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        dbg_title_row.addWidget(dbg_title_icon)
        dbg_title_row.addWidget(dbg_title)
        dbg_title_row.addStretch(1)
        self.main_window.dbg_title = dbg_title
        self.main_window.debug_title_icon = dbg_title_icon
        
        # 网格：键左对齐、值右对齐；指标行用可伸长进度条填满中间空隙
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(11)
        grid.setColumnStretch(1, 1)

        # 创建调试标签（状态胶囊）
        self._create_debug_labels(grid)

        self.debug_bars = {}
        self.main_window.debug_bars = self.debug_bars

        try:
            secondary = self.main_window.get_secondary_grey()
        except Exception:
            secondary = "#758095"
        key_style = f"color: {secondary}; font-size: 14px;"
        hr_key_container = self._create_hr_dot_widget(grid, 0, key_style)
        left_labels = self._create_other_debug_labels(grid, 0, key_style, self.debug_labels)
        self.main_window.debug_left_labels = left_labels

        debug_section_headers = []

        def _add_section(title: str, icon_name: str, r: int) -> int:
            hdr = _section_header(title, icon_name, height=36, radius=8)
            hdr.setObjectName("debugSectionHeader")
            debug_section_headers.append(hdr)
            grid.addWidget(hdr, r, 0, 1, 2)
            return r + 1

        def _add_status_row(key_widget: QWidget, value_widget: QWidget, r: int) -> int:
            # R5：固定状态行节奏，避免右侧信息全部挤在卡片上半部。
            grid.setRowMinimumHeight(r, 34)
            grid.addWidget(key_widget, r, 0)
            grid.addWidget(value_widget, r, 1, 1, 1, Qt.AlignRight | Qt.AlignVCenter)
            return r + 1

        row = 0
        row = _add_section("发送状态", "send_status", row)
        row = _add_status_row(left_labels['next'], self.debug_labels['next_send'], row)
        row = _add_status_row(hr_key_container, self.debug_labels['hr_status'], row)
        row = _add_status_row(left_labels['idle'], self.debug_labels['idle_time'], row)

        row = _add_section("环境信息", "environment", row)
        row = _add_status_row(left_labels['window'], self.debug_labels['window'], row)
        row = _add_status_row(left_labels['music'], self.debug_labels['music_title'], row)

        row = _add_section("性能", "performance", row)
        grid.setRowMinimumHeight(row, 34); grid.addWidget(left_labels['cpu'], row, 0); grid.addWidget(self._metric_cell('cpu_usage'), row, 1); row += 1
        grid.setRowMinimumHeight(row, 34); grid.addWidget(left_labels['ram'], row, 0); grid.addWidget(self._metric_cell('ram_usage'), row, 1); row += 1
        grid.setRowMinimumHeight(row, 34); grid.addWidget(left_labels['gpu'], row, 0); grid.addWidget(self._metric_cell('gpu_usage'), row, 1); row += 1
        row = _add_status_row(left_labels['temp'], self.debug_labels['temperatures'], row)

        dbg_box.addLayout(dbg_title_row)
        dbg_box.addLayout(grid)
        dbg_box.addStretch(1)

        self.debug_panel = debug_acrylic
        self.main_window.debug_panel = debug_acrylic
        self.main_window.debug_section_headers = debug_section_headers
        return debug_panel

    def _metric_cell(self, key: str) -> QWidget:
        """仪表盘行：进度条 + 固定宽百分比。"""
        cell = QWidget()
        cell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay = QHBoxLayout(cell)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setFixedHeight(10)
        bar.setMinimumWidth(48)
        bar.setTextVisible(False)
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bar.setStyleSheet(
            f"QProgressBar {{ background: {TRACK}; border: none; border-radius: 5px; }}"
            f"QProgressBar::chunk {{ background-color: {BRAND}; border-radius: 5px; }}"
        )
        self.debug_bars[key.replace('_usage', '')] = bar

        label = self.debug_labels[key]
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setFixedWidth(42)
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

        lay.addWidget(bar, 1)
        lay.addWidget(label, 0)
        return cell

    def _create_debug_labels(self, grid: QGridLayout) -> None:
        """创建调试数值标签（状态胶囊）。"""
        debug_labels = {
            'window': _status_pill(""),
            'music_title': _status_pill(""),
            'idle_time': _status_pill(""),
            'next_send': _status_pill(""),
            'cpu_usage': QLabel(""),
            'ram_usage': QLabel(""),
            'gpu_usage': QLabel(""),
            'temperatures': _status_pill(""),
            'hr_status': _status_pill(""),
        }
        for key in ("cpu_usage", "ram_usage", "gpu_usage"):
            debug_labels[key].setObjectName("metricValue")
            debug_labels[key].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.debug_labels = debug_labels
        self.main_window.debug_labels = debug_labels
    
    def _create_hr_dot_widget(self, grid: QGridLayout, left_col_w: int, key_style: str) -> QWidget:
        """创建心率彩点组件（● + 「心率」，与其它键名左对齐）"""
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        hr_key_container = QWidget()
        hr_key_layout = QHBoxLayout(hr_key_container)
        hr_key_layout.setContentsMargins(0, 0, 0, 0)
        hr_key_layout.setSpacing(6)

        hr_dot = QLabel()
        hr_dot.setFixedSize(8, 8)
        hr_dot.setStyleSheet("border-radius: 4px; background: #888888;")

        hr_dot_fx = QGraphicsOpacityEffect(hr_dot)
        hr_dot.setGraphicsEffect(hr_dot_fx)
        hr_dot_anim = QPropertyAnimation(hr_dot_fx, b"opacity")
        hr_dot_anim.setLoopCount(-1)
        hr_dot_anim.setDuration(1200)
        hr_dot_anim.setStartValue(0.4)
        hr_dot_anim.setEndValue(1.0)

        hr_key_label = QLabel("心率")
        hr_key_label.setStyleSheet(key_style)
        hr_key_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # 彩点与文字靠左，与「下次发送」等键名左边缘对齐
        hr_key_layout.addWidget(hr_dot, 0, Qt.AlignLeft | Qt.AlignVCenter)
        hr_key_layout.addWidget(hr_key_label, 0)
        hr_key_layout.addStretch(1)

        self.main_window.hr_dot = hr_dot
        self.main_window.hr_dot_fx = hr_dot_fx
        self.main_window.hr_dot_anim = hr_dot_anim
        self.main_window.hr_key_label = hr_key_label
        return hr_key_container

    def _create_other_debug_labels(self, grid: QGridLayout, left_col_w: int,
                                  key_style: str, debug_labels: Dict[str, QLabel]) -> Dict[str, QLabel]:
        """创建左列键名（左对齐）并设置右列数值对齐"""
        lefts: Dict[str, QLabel] = {}
        def _mk(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(key_style)
            lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            return lbl
        lefts['next'] = _mk("下次发送")
        lefts['idle'] = _mk("挂机")
        lefts['window'] = _mk("前台窗口")
        lefts['music'] = _mk("音乐")
        lefts['cpu'] = _mk("CPU")
        lefts['ram'] = _mk("RAM")
        lefts['gpu'] = _mk("GPU")
        lefts['temp'] = _mk("温度")

        for key in ['next_send', 'hr_status', 'idle_time', 'window', 'music_title',
                    'cpu_usage', 'ram_usage', 'gpu_usage', 'temperatures']:
            if key in debug_labels:
                lbl = debug_labels[key]
                if lbl.objectName() == "statusPill":
                    continue
                lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                lbl.setMinimumWidth(0)
                lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return lefts

    def setup_body_layout(self) -> None:
        """三栏：左发送区 | 中配置区 | 右状态区，比例约 1.05 : 1 : 1.05"""
        body = QWidget()
        self.body_widget = body
        self.body = QBoxLayout(QBoxLayout.LeftToRight, body)
        self.body.setContentsMargins(18, 14, 18, 18)
        self.body.setSpacing(16)

        left_col = QWidget()
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(14)
        input_panel_widget = self.create_input_panel()
        history_panel_widget = self.create_history_panel()
        left_layout.addWidget(input_panel_widget, 1250)
        left_layout.addWidget(history_panel_widget, 1000)

        tool_panel_widget = self.create_tool_panel()

        debug_panel_widget = self.create_debug_panel()
        right_col = QWidget()
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(debug_panel_widget, 1)

        self.body.addWidget(left_col, 105)
        self.body.addWidget(tool_panel_widget, 100)
        self.body.addWidget(right_col, 105)

        self.main_window.body = self.body
