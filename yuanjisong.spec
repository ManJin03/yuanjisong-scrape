# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：猿急送筛选系统 桌面端（Windows, onedir, windowed）。

要点：
- collect_all(curl_cffi)：libcurl 等二进制 DLL 必须随包，否则运行时报加载失败
- collect_all(webview) + winforms/edgechromium hidden imports：pywebview
  Windows 后端依赖 pythonnet/clr_loader 动态加载，需显式声明
- excludes：排除测试框架等运行时用不到的模块，减小体积
- onedir + console=False：启动快、无控制台黑窗
"""
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
# cffi：curl_cffi 运行时动态依赖（源码中无静态 import，PyInstaller 探测不到，必须显式收集）
for pkg in ("cffi", "curl_cffi", "openpyxl", "webview"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += [
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "clr_loader",
    "pythonnet",
]

a = Analysis(
    ["desktop_app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "_pytest",
        "tkinter",
        "setuptools",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="猿急送筛选系统",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="猿急送筛选系统",
)
