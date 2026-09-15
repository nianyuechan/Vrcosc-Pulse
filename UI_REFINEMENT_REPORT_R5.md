# VRCOSC Pulse UI Refined R5

本轮以 R4 Windows 实机截图（1158×816）为视觉验收基准，只做最后一轮界面比例/节奏微调，不修改 OSC、自动发送、BLE 心率、硬件监控、壁纸、插件与设置持久化逻辑。

## 本轮修改

- 右侧“调试信息”从过度集中在卡片上半区调整为更接近参考图的仪表盘纵向节奏。
- 调试网格纵向间距 6px → 9px，横向间距 12px → 14px。
- 发送状态 / 环境信息 / 性能分组标题高度 34px → 36px。
- 下次发送、心率、挂机、前台窗口、音乐、温度，以及 CPU/RAM/GPU 指标行统一至少 32px 高，提升扫读性并减少大块无效底部留白。
- 状态胶囊最小高度 27px → 28px。
- CPU/RAM/GPU 进度条高度 8px → 9px，提升 Windows 100% 缩放下的视觉重量。
- CPU/RAM/GPU 百分比字重 500 → 600，和更粗的进度条保持平衡。
- “开始发送”禁用态稍微增强文字与边界对比度，仍保持明显不可用状态。

## 修改文件

- `app/ui/layout.py`
- `app/mixins/theme.py`

## 验证

- `python -m compileall -q main.py app plugins utils`：PASS
- `python -m unittest discover -s tests -t .`：20/20 PASS
- 当前容器未提供 PySide6 图形运行环境，因此最终 Qt 实机视觉效果仍以 Windows 截图验收。

## 范围说明

R5 不改变消息组成、定时器、OSC、BLE、硬件指标读取、插件、偏好存储等业务行为。
