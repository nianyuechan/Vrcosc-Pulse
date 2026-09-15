# VRCOSC Pulse UI Refined R4

本轮以 R3 Windows 实机截图为视觉验收基准，只做最终视觉收尾，不修改 OSC、自动发送、BLE 心率、硬件监控、壁纸、插件与设置持久化逻辑。

## 本轮修改

- 左栏上下比例从偏重输入区调整为更接近参考图的 1450:1100：输入区略收紧，已发送历史区获得更多垂直空间。
- 常规 / 性能两个工具分组之间新增 1px 极浅分隔线，使层级更清楚，同时避免增加过多留白。
- 禁用状态的 CPU/RAM/GPU/温度复选框不再显示成一块实心灰方块，改为低对比度描边 + 极浅底色，更接近正常 checkbox 的禁用态。
- CPU/RAM/GPU 进度条高度 7px -> 8px，改善小窗口下的可读性和圆角表现。
- 顶部副标题统一为 12px；状态胶囊宽度 142px -> 138px，右侧区域更紧凑。
- 新增分隔线的深色模式样式，保持浅色/深色主题一致。

## 修改文件

- `app/ui/layout.py`
- `app/mixins/theme.py`
- `app/main_window.py`

## 验证

- `python -m compileall -q main.py app plugins utils`
- `python -m unittest discover -s tests -t .`
- 当前容器无 PySide6，因此无法执行 Qt offscreen 实例化；Windows 实机视觉截图仍是最终验收依据。

## 范围说明

R4 是视觉收尾轮，不改变发送消息组成、定时器、OSC、BLE、硬件指标读取、插件和偏好存储行为。
