# VRCOSC Pulse UI Refined R3

本轮以 R2 实机截图为视觉验收基准，继续做像素级精修，不改变 OSC、自动发送、BLE 心率、硬件监控、壁纸和设置持久化等业务逻辑。

## 本轮修改

- 工具区父子关系增加轻量点状树形引导线：
  - `心率状态 -> 选择设备`
  - `附加硬件性能信息 -> CPU/RAM/GPU/温度`
- 子项缩进从单纯留白改为明确的结构层级，降低“所有选项同级”的视觉误读。
- 调试区状态胶囊进一步收紧：最小宽度 78 -> 68，高度与内边距下调，减少右侧像输入框的感觉。
- 调试区行间距 7 -> 6，信息密度更接近参考图。
- 四张卡片标题图标底由 28x28 调到 30x30，圆角 8 -> 9，使标题区域比例更协调。
- 浅色模式卡片边框/阴影继续减弱：边框透明度降低、阴影 blur 18 -> 14、offset 2 -> 1、alpha 24 -> 15，减少实机截图中的黑灰重边。
- 运行时更新的状态胶囊与主题静态样式保持一致，避免刷新数据后尺寸跳变。

## 修改文件

- `app/ui/layout.py`
- `app/ui/components/input_panel.py`
- `app/ui/components/history_panel.py`
- `app/ui/components/tool_panel.py`
- `app/mixins/theme.py`
- `app/mixins/debug.py`

## 验证

- `python -m compileall -q main.py app plugins utils`：PASS
- `python -m unittest discover -s tests -t .`：20/20 PASS
- 当前执行环境未安装 PySide6，因此未执行 Qt offscreen 启动截图；请在装有项目依赖的 Windows 环境进行最终视觉验收。

## 范围说明

R3 只做 UI 精修，没有修改消息组装、OSC 发送、BLE 数据解析、插件依赖与偏好存储逻辑。
