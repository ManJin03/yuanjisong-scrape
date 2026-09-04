# -*- coding: utf-8 -*-
"""桌面端壳：pywebview 原生窗口 + 后台运行现有 webapp 本地服务。

复用网页端的全部界面与逻辑（webapp.py），桌面端只负责开一个原生窗口，
窗口关闭即进程退出，daemon 服务线程随之结束，资源释放干净。

依赖策略（与项目「按需加载、缺失给出提示」惯例一致）：
- 未安装 pywebview：打印安装指引后退出，不崩溃
- WebView2 运行时缺失（Win10/11 一般自带）：给出官方下载提示
"""
from __future__ import annotations

import os
import sys
import threading
import traceback

WINDOW_TITLE = "猿急送兼职项目智能筛选系统"


def _log_file() -> "str | None":
    """打包运行时把异常写入 exe 同级日志（windowed 模式无控制台可看）。"""
    try:
        import yuanjisong.config as _cfg

        return str(_cfg.ROOT_DIR / "desktop_error.log")
    except Exception:  # noqa: BLE001
        return None


def _log(msg: str) -> None:
    path = _log_file()
    if not path:
        print(msg)
        return
    try:
        from datetime import datetime

        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def run_desktop(host: str = "127.0.0.1", port: int = 8765) -> None:
    """启动桌面窗口：后台线程跑 webapp 服务，主线程进 pywebview 事件循环。"""
    _log("[start] desktop 启动")
    try:
        import webview
    except ImportError:
        hint = (
            "缺少依赖 pywebview，无法启动桌面窗口。\n"
            "请执行：pip install pywebview\n"
            "或重新运行 build_desktop.bat 完整安装构建依赖。"
        )
        _log(hint)
        sys.exit(hint)

    from yuanjisong.webapp import start_server

    try:
        server, url = start_server(host, port)
        # start_server 只负责绑定端口；桌面模式下在后台线程开始受理请求
        # （浏览器模式的 run() 则在主线程 serve_forever，行为不变）
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _log(f"[start] 服务已启动 {url}")
    except Exception as e:  # noqa: BLE001
        _log("[error] 服务启动失败:\n" + traceback.format_exc())
        sys.exit(str(e))

    def _stop_server():
        try:
            server.shutdown()
            server.server_close()
        except Exception:  # noqa: BLE001
            pass

    # headless 模式（环境变量 DESKTOP_HEADLESS=1）：跳过窗口，仅运行本地服务。
    # 供 CI 冒烟测试与无图形环境使用，验证打包产物内服务与依赖可用性。
    if os.environ.get("DESKTOP_HEADLESS") == "1":
        _log("[start] headless 模式：跳过窗口，仅运行本地服务")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            _stop_server()
        return

    try:
        webview.create_window(
            WINDOW_TITLE,
            url,
            width=1280,
            height=840,
            min_size=(1000, 640),
        )
        webview.start()
    except Exception as e:  # noqa: BLE001
        # 窗口未能创建（常见于缺 WebView2）：退回浏览器模式，功能不受影响
        import webbrowser

        _log("[warn] webview 窗口失败，退回浏览器模式:\n" + traceback.format_exc())
        print(
            "WebView2 运行时初始化失败，已退回浏览器模式。\n"
            "Windows 10/11 通常自带该组件；如缺失请安装官方运行时：\n"
            "https://developer.microsoft.com/microsoft-edge/webview2/\n"
            f"错误详情：{e}"
        )
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            _stop_server()
        return

    _stop_server()


if __name__ == "__main__":
    run_desktop()
