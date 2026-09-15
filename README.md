# VRCOSC Pulse

把你想说的话**定时自动刷进 VRChat 的聊天框（ChatBox）**，不用摘头显、不用反复打字，就能让身边的人一直看到你当前的状态。

VRCOSC Pulse 是一个 Windows 桌面小工具：它按设定的间隔把「你输入的文本 + 勾选的附加信息」拼成一条消息，通过 **OSC**（`/chatbox/input` → `127.0.0.1:9000`）发给本机运行的 VRChat。

---

## 功能

### 自动发送
- 自定义发送间隔（默认 30 秒），随时开始 / 停止
- 顶部状态胶囊与倒计时实时显示发送状态
- 消息长度自动截断到 VRChat 的 **144 字符**上限

### 可附加的信息
在输入内容后按需勾选拼接：

| 附加项 | 说明 |
|---|---|
| 时间 | `HH:MM:SS` |
| 前台窗口 | 当前活动窗口标题 |
| 正在播放 | 通过 Windows SMTC 读取，显示为 `♪ 歌手 - 歌名` |
| 挂机时长 | 超过阈值自动标注「已挂机 Xh Ym」 |
| CPU / RAM / GPU | 实时占用率 |
| 温度 | CPU / GPU / SSD / 主板 |
| 心率 | 连接 BLE 设备（如小米手环 9），显示 `[HR: 72bpm]` |

### 界面
- 无边框亚克力毛玻璃窗口，浮在桌面壁纸之上
- 品牌粉色配色，自动适配浅色 / 深色壁纸的对比度
- 系统托盘常驻，最小化不退出
- 历史记录面板 + 一键清空
- 右侧调试面板实时显示各指标采集状态，方便判断哪一项没生效
- 设置对话框：外观、性能模式、静态模糊、圆角、投影等

### 插件系统
插件默认**全部不启用**，需在设置中手动开启；启用前会检查依赖（其他插件或 Python 包），缺失时给出可操作的提示。

内置三个插件：

- `hide_console` — 隐藏控制台窗口
- `pause_on_y` — 按下 `Y` 键暂停发送 20 秒后自动恢复
- `hello_plugin` — 插件编写模板

编写自己的插件：在 `plugins/local/` 下新建模块，暴露 `plugin_entry()` 工厂或可无参构造的 `Plugin` 类，并把模块名加入 `VRCOSC_Pulse.spec` 的 `hiddenimports`。

---

## 环境要求

- **Windows 10 / 11**（大量依赖 `ctypes` / `win32gui` / `winsdk` / DWM 等系统 API）
- **Python 3.10+**（源码使用了 PEP 604 的 `X | None` 注解，3.9 无法运行）

### 安装依赖

```bash
pip install -r requirements.txt
```

必需依赖：

```bash
pip install PySide6 python-osc
```

可选依赖（缺失时对应功能优雅降级为「未启用」或 `N/A`，不会崩溃）：

```bash
pip install psutil pynvml pywin32 winsdk bleak
```

---

## 运行

```bash
python main.py
```

无控制台启动（双击友好）：

```bash
python main.pyw
```

### 使用步骤

1. 打开 **VRChat**，在设置中启用 OSC（`Options → OSC`）
2. 运行本程序，在输入框写下要展示的内容
3. 按需勾选要附加的信息
4. 点击「开始发送」

若 1 秒内未收到 VRChat 的 `/chatbox/typing` 回包，程序会提示你检查 OSC 开关。

---

## 开发

```bash
# 语法检查
python -m compileall -q main.py app plugins utils tests

# 单元测试（标准库 unittest）
python -m unittest discover -s tests -t .

# 无显示器冒烟测试（Windows）
set QT_QPA_PLATFORM=offscreen && python main.py
```

打包为单个可执行文件：

```bash
pyinstaller VRCOSC_Pulse.spec
```

---

## 项目结构

```
main.py / main.pyw          入口
app/
  main_window.py            主窗口（组合各 mixin）
  core/                     OSC 客户端、消息合成、系统指标、偏好持久化
  mixins/                   wallpaper / theme / osc / sending / history / debug / tray
  ui/                       布局、面板、控件、背景与动画、设计令牌
  dialogs/settings.py       设置对话框
  hr.py                     BLE 心率
plugins/                    base(Protocol) + manager + local/
utils/                      高斯模糊等工具
resources/icons/            SVG 图标
tests/                      unittest 测试
```

### 消息链路

```
QTimer ──► compose_message()
             └─► app/core/composer.py   （拼接时间 / 窗口 / 音乐 / 挂机 / 硬件 / 心率）
             └─► app/core/system.py     （系统指标，带 TTL 缓存与降级链）
             └─► app/hr.py              （BLE 心率）
          ──► app/core/osc.py:OSCClient.send_message()
          ──► /chatbox/input  →  127.0.0.1:9000
```

### 配置文件

偏好写入用户主目录：

- 当前：`~/.vrcosc_pulse_prefs.json`
- 旧版：`~/.vrc_qt_prefs.json`（首次运行新版时会自动迁移，旧文件保留作为安全网）

---

## 许可

本项目未附带许可证文件。如需开源分发，请先补充 `LICENSE`。
