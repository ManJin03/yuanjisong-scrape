# -*- coding: utf-8 -*-
"""Web 软件 HTTP API 测试：本机回环启动真实服务，无需联网。"""
import json
import threading
import urllib.request
from pathlib import Path

import pytest

from yuanjisong.webapp import DataStore, ScrapeManager, make_handler
from http.server import ThreadingHTTPServer


def get(url: str):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.read()


def post(url: str, body: dict | None = None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read()


def test_index_page(server):
    status, body = get(server + "/")
    assert status == 200
    text = body.decode("utf-8")
    assert "猿急送兼职项目智能筛选系统" in text
    for feature in ("重新爬取", "智能分类", "学生模式", "排除黑名单", "导出当前视图"):
        assert feature in text


def test_api_data_shape(server):
    status, body = get(server + "/api/data")
    assert status == 200
    d = json.loads(body)
    assert "projects" in d and "categories" in d and "summary" in d
    if d["projects"]:
        p = d["projects"][0]
        for key in ("id", "title", "budget", "work_type", "is_remote",
                    "delivery_count", "category", "employer", "desc"):
            assert key in p
        assert d["categories"][0] == "全部"


def test_api_project_detail(server):
    _, body = get(server + "/api/data")
    projects = json.loads(body)["projects"]
    if not projects:
        pytest.skip("本地无数据")
    pid = projects[0]["id"]
    status, body = get(server + f"/api/project/{pid}")
    assert status == 200
    d = json.loads(body)
    assert d["id"] == pid
    assert "description" in d and "url" in d


def test_api_project_not_found(server):
    try:
        get(server + "/api/project/999999999")
        assert False, "should 404"
    except urllib.error.HTTPError as e:
        assert e.code == 404


def test_scrape_status_initial(server):
    status, body = get(server + "/api/scrape/status")
    d = json.loads(body)
    assert d["running"] is False
    assert "messages" in d


def test_export_view_writes_excel(server, tmp_path: Path, monkeypatch):
    from yuanjisong import config
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    body = {"keyword": "", "category": "全部", "budget_min": 0, "budget_max": 500,
            "remote_only": False, "exclude_blacklist": True,
            "student_mode": True, "sort_by": "预算升序"}
    status, resp = post(server + "/api/export/view", body)
    assert status == 200
    d = json.loads(resp)
    assert d["count"] >= 0
    if d["count"] > 0:
        assert Path(d["path"]).exists()


def test_classify_endpoint(server):
    _, body = get(server + "/api/data")
    n = len(json.loads(body)["projects"])
    if not n:
        pytest.skip("本地无数据")
    status, resp = post(server + "/api/classify")
    assert status == 200
    d = json.loads(resp)
    assert d["count"] == n
    assert sum(d["summary"].values()) == n
