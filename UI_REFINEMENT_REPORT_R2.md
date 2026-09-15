# VRCOSC Pulse UI 精修报告（R2）

基线：R1（`ChatBox_Pulse_UI_Refined_R1.zip`）。
依据：用户实机截图反馈 + 已确认的粉色卡片化参考稿。
目标：不改变 OSC / BLE 心率 / 性能采集核心语义，继续收敛尺寸、间距、状态层级和跨系统图标一致性。

## 本轮完成

1. **顶部栏收紧**
   - Header 由 82px 收到 72px，减少无效留白。
   - 品牌 logo / 标题尺寸微调，副标题增加 `♡`。
   - 状态胶囊固定为紧凑尺寸，长状态自动截断并保留 tooltip。
   - “设置”按钮独立为中性次级按钮，不再与粉色功能按钮混淆。

2. **应用状态与心率状态解耦**
   - 勾选“心率状态”后，顶部不再长期显示“心率监测已开启”。
   - 顶部恢复应用级 `● 就绪 / 一切正常`；心率实时状态继续在右侧发送状态区显示。
   - 蓝牙扫描/连接仍可短暂占用顶部提示，完成后自动恢复“就绪”。

3. **工具区密度优化**
   - 常规项目行高 40→36px，性能子项 36→34px。
   - checkbox 指示器 20→18px，圆角与间距同步缩小。
   - “选择设备”固定为 138×32px，不再横向撑满整栏，并继续作为心率子项缩进显示。
   - 常规/性能分组标题改用本地 SVG 图标，不再依赖 Unicode 符号。

4. **右侧调试面板精修**
   - `发送状态 / 环境信息 / 性能` 分组头全部改用本地 SVG 图标。
   - `未启用 / 0s / 无 / 窗口标题 / 心率状态` 改为右对齐的短胶囊，不再整行拉满。
   - 状态胶囊最大宽度 220px；过长窗口/音乐文本自动省略，完整内容保留 tooltip。
   - CPU/RAM/GPU 保持 `名称 → 进度条 → 百分比`，进度条高度微调为 7px。
   - 移除调试值上的 Consolas 强制字体，统一使用应用 UI 字体。

5. **已发送空状态修正**
   - 删除容易被误认为“加载中”的 `◌` 字符。
   - 新增 `empty_history.svg` 文档/消息空状态图标。
   - 空状态文案与标题继续适配深浅色主题。

6. **卡片边框 / 阴影修正**
   - 浅色模式不再使用深色内描边，解决右侧/底部出现明显黑灰边的问题。
   - 浅色卡片统一为轻边框 + 更弱阴影；深色模式保留适度轮廓。

7. **本地图标优先**
   - `get_icon()` 改为优先使用 `resources/icons/*.svg`，再回退系统主题图标。
   - 重画 `settings.svg`，新增 `send_status.svg`、`empty_history.svg`。
   - 避免 Windows 不同图标主题下出现星号/异形图标。

## R2 变更文件

- `app/main_window.py`
- `app/mixins/debug.py`
- `app/mixins/sending.py`
- `app/mixins/theme.py`
- `app/ui/components/history_panel.py`
- `app/ui/components/input_panel.py`
- `app/ui/components/tool_panel.py`
- `app/ui/layout.py`
- `app/ui/panels.py`
- `resources/icons/settings.svg`
- `resources/icons/send_status.svg`（新增）
- `resources/icons/empty_history.svg`（新增）

## 验证

- `python -m compileall -q app plugins tests main.py`：PASS
- `python -m unittest discover -s tests -v`：20/20 PASS
- 当前执行环境仍未安装 `PySide6`，无法在此环境执行真实 Qt offscreen 启动/截图；需要在用户 Windows + PySide6 环境做最终视觉验收。

## 未改变的核心功能

壁纸/纯色背景、系统深浅色、OSC、自动发送、BLE 心率、硬件性能、温度、系统托盘、设置持久化、插件机制均保留。
