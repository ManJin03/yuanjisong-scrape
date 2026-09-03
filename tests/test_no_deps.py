# -*- coding: utf-8 -*-
"""依赖缺失场景测试：GUI 必须能在无第三方依赖时启动浏览（导出/爬取给出友好提示）。"""
import importlib
import sys


class Blocker:
    """meta_path 钩子：屏蔽指定模块，模拟用户系统 Python 未装依赖。"""

    def __init__(self, names):
        self.names = names

    def find_spec(self, name, path=None, target=None):
        if name in self.names or any(name.startswith(n + ".") for n in self.names):
            raise ImportError(f"blocked for test: {name}")
        return None


def _block(monkeypatch, *names):
    for m in list(sys.modules):
        if any(m == n or m.startswith(n + ".") for n in names):
            monkeypatch.delitem(sys.modules, m, raising=False)
    blocker = Blocker(names)
    sys.meta_path.insert(0, blocker)
    return blocker


def test_webapp_imports_without_openpyxl(monkeypatch):
    """复现用户报错场景：无 openpyxl 时 webapp 模块必须可导入（GUI 可启动）。"""
    monkeypatch.delitem(sys.modules, "yuanjisong.webapp", raising=False)
    monkeypatch.delitem(sys.modules, "yuanjisong.exporter", raising=False)
    blocker = _block(monkeypatch, "openpyxl")
    try:
        webapp = importlib.import_module("yuanjisong.webapp")
    finally:
        sys.meta_path.remove(blocker)
    assert callable(webapp.run)
    assert callable(webapp.make_handler)


def test_webapp_imports_without_curl_cffi(monkeypatch):
    monkeypatch.delitem(sys.modules, "yuanjisong.webapp", raising=False)
    monkeypatch.delitem(sys.modules, "yuanjisong.scrape_lightweight", raising=False)
    blocker = _block(monkeypatch, "curl_cffi")
    try:
        webapp = importlib.import_module("yuanjisong.webapp")
    finally:
        sys.meta_path.remove(blocker)
    assert callable(webapp.run)


def test_missing_deps_detector(monkeypatch):
    monkeypatch.delitem(sys.modules, "yuanjisong.webapp", raising=False)
    blocker = _block(monkeypatch, "openpyxl", "curl_cffi")
    try:
        webapp = importlib.import_module("yuanjisong.webapp")
        assert webapp.missing_deps() == ["openpyxl", "curl_cffi"]
    finally:
        sys.meta_path.remove(blocker)
