# -*- coding: utf-8 -*-
"""桌面端打包入口（PyInstaller 薄壳）。

仅负责调用桌面壳；窗口标题/尺寸在 yuanjisong/desktop.py 中统一配置。
"""
from yuanjisong.desktop import run_desktop

if __name__ == "__main__":
    run_desktop()
