"""双击启动入口（无控制台窗口）。

Windows 上 .pyw 文件默认由 pythonw.exe 解释执行，不会创建/显示 cmd
控制台窗口。此处复用 main.py 的完整启动逻辑；无控制台时日志由
main._configure_logging() 自动写入用户目录的 ~/.vrc_qt.log。
"""

import os
import sys

# 保证从任意工作目录双击启动时都能导入仓库内的 main 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main.main())
