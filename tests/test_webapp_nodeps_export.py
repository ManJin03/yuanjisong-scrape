# -*- coding: utf-8 -*-
"""追加到 webapp 测试：导出接口在 openpyxl 缺失时返回友好错误而非崩溃。"""
import json
import sys
import urllib.request

import pytest


class _Blocker:
    def find_spec(self, name, path=None, target=None):
        if name == "openpyxl" or name.startswith("openpyxl."):
            raise ImportError(f"blocked: {name}")
        return None


def test_export_view_friendly_error_without_openpyxl(server, monkeypatch):
    monkeypatch.delitem(sys.modules, "yuanjisong.exporter", raising=False)
    monkeypatch.delitem(sys.modules, "openpyxl", raising=False)
    blocker = _Blocker()
    sys.meta_path.insert(0, blocker)
    try:
        data = json.dumps({"category": "全部"}).encode()
        req = urllib.request.Request(server + "/api/export/view", data=data,
                                     method="POST",
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        assert e.value.code == 500
        body = e.value.read().decode("utf-8")
        assert "openpyxl" in body and "run_gui.bat" in body
    finally:
        sys.meta_path.remove(blocker)
