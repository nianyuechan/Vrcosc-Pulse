# VRCOSC Pulse UI 精修报告（R1）

基线：用户本轮上传的 `ChatBox Pulse(1).zip`。
目标：在已确认的粉色卡片化参考方案上继续收敛，不改 OSC / 心率 / 性能采集等核心业务语义。

## 本轮继续修改

- 顶部品牌区继续贴近参考稿：补应用 logo 资源、状态胶囊状态色、设置按钮图标化。
- 输入区：清空按钮增加图标；发送按钮支持发送/停止图标切换，并保持空输入禁用。
- 已发送区：清空记录按钮增加图标；保留累计历史和空状态逻辑。
- 工具区：心率“选择设备”明确作为心率子项；硬件性能子项继续由总开关控制。
- 调试区：发送状态 / 环境信息 / 性能三个分组增加一致的图标标题；状态值保持胶囊化。
- 性能条：统一品牌粉；RAM 高占用继续使用强调/警告色。
- 深色模式：补齐状态胶囊、分组标题、次级按钮的深色适配，避免白底硬编码。
- OSC/发送状态：顶部状态胶囊同步“就绪 / 探测 / 发送 / 错误”等状态，不改原通信路径。

## 变更文件

- `app/main_window.py`
- `app/ui/layout.py`
- `app/ui/components/input_panel.py`
- `app/ui/components/history_panel.py`
- `app/mixins/theme.py`
- `app/mixins/sending.py`
- `app/mixins/osc.py`
- `app/mixins/debug.py`
- `resources/icons/logo.svg`（新增）
- `resources/icons/stop.svg`（新增）

## 验证

- `python -m compileall -q app plugins tests main.py`：PASS
- `python -m unittest discover -s tests -v`：20/20 PASS
- 当前执行环境未安装 `PySide6`，因此本轮无法在此环境重新执行 Qt offscreen 启动/截图；这不等同于 UI 运行失败。建议在项目实际 Windows + PySide6 环境再做一次启动确认。

## 功能兼容

保留：壁纸/纯色背景、深浅色主题、OSC、自动发送、BLE 心率、硬件性能、温度、系统托盘、设置持久化、插件机制。
