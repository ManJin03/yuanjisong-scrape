# -*- coding: utf-8 -*-
"""代理池单元测试：不联网，通过注入代理与模拟 report 验证调度逻辑。"""
import time

import config
from proxy_pool import ProxyEntry, ProxyPool


def test_pool_empty_returns_none():
    pool = ProxyPool()
    assert pool.acquire() is None


def test_weighted_and_report():
    pool = ProxyPool()
    for u in ("http://a:1", "http://b:2", "http://c:3"):
        pool.entries[u] = ProxyEntry(url=u)
    picked = {pool.acquire() for _ in range(200)}
    assert picked <= {"http://a:1", "http://b:2", "http://c:3"}
    assert len(picked) >= 2  # 加权随机覆盖多个代理


def test_blacklist_after_three_fails():
    e = ProxyEntry(url="http://x:1")
    for _ in range(config.PROXY_FAIL_LIMIT):
        e.report(False)
    assert not e.alive
    assert e.blacklisted_at > 0


def test_success_resets_consecutive():
    e = ProxyEntry(url="http://x:1")
    e.report(False)
    e.report(False)
    e.report(True)
    e.report(False)
    e.report(False)
    assert e.alive  # 未连续 3 次失败不拉黑


def test_recovery():
    pool = ProxyPool()
    e = ProxyEntry(url="http://x:1")
    pool.entries[e.url] = e
    for _ in range(config.PROXY_FAIL_LIMIT):
        e.report(False)
    assert not e.alive
    e.blacklisted_at = time.time() - config.PROXY_RECOVER_SECONDS - 1
    assert pool.acquire() == e.url
    assert e.alive and e.score == 0.5


def test_stats():
    pool = ProxyPool()
    pool.entries["a"] = ProxyEntry(url="a", score=2.0)
    e = ProxyEntry(url="b")
    pool.entries["b"] = e
    e.report(False); e.report(False); e.report(False)
    s = pool.stats()
    assert s == {"total": 2, "alive": 1, "blacklisted": 1, "avg_score": 2.0}
