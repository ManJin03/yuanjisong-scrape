# -*- coding: utf-8 -*-
"""代理池：抓取免费代理 -> 异步连通性测试 -> 按成功率加权随机 -> 失败拉黑 -> 定期恢复。

设计要点：
- 无代理可用时返回 None，主程序自动降级直连，绝不阻塞任务；
- 评分初始 1.0，成功 +0.2 / 失败 -0.5，截断到 [0.1, 3.0]，加权随机更平滑；
- 连续失败 PROXY_FAIL_LIMIT 次进入黑名单，PROXY_RECOVER_SECONDS 秒后自动放回；
- 代理配置从环境变量读取（KUAIDAILI_ORDER），不引入额外依赖。
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import time
from dataclasses import dataclass

from curl_cffi import requests as cffi_requests

import config


@dataclass
class ProxyEntry:
    url: str
    score: float = 1.0
    success: int = 0
    fail: int = 0
    consec_fail: int = 0
    blacklisted_at: float = 0.0
    last_used: float = 0.0

    @property
    def alive(self) -> bool:
        return self.blacklisted_at == 0.0

    def report(self, ok: bool) -> None:
        if ok:
            self.success += 1
            self.consec_fail = 0
            self.score = min(3.0, self.score + 0.2)
        else:
            self.fail += 1
            self.consec_fail += 1
            self.score = max(0.1, self.score - 0.5)
            if self.consec_fail >= config.PROXY_FAIL_LIMIT:
                self.blacklisted_at = time.time()


class ProxyPool:
    def __init__(self, pool_size: int | None = None):
        self.size = pool_size or config.PROXY_POOL_SIZE
        self.entries: dict[str, ProxyEntry] = {}
        self._session: cffi_requests.AsyncSession | None = None

    async def _sess(self) -> cffi_requests.AsyncSession:
        if self._session is None:
            self._session = cffi_requests.AsyncSession(impersonate=config.IMPERSONATE)
        return self._session

    # ---------- 代理来源 ----------
    async def fetch_free_proxy_list(self) -> list[str]:
        """从 free-proxy-list.net 抓取 HTTP 代理。"""
        try:
            s = await self._sess()
            r = await s.get("https://free-proxy-list.net/", timeout=10)
            pairs = re.findall(r"<td>(\d+\.\d+\.\d+\.\d+)</td><td>(\d+)</td>", r.text)
            return [f"http://{ip}:{port}" for ip, port in pairs]
        except Exception:
            return []

    async def fetch_kuaidaili(self) -> list[str]:
        """快代理订单接口（可选：设置环境变量 KUAIDAILI_ORDER）。"""
        order = os.getenv("KUAIDAILI_ORDER", "").strip()
        if not order:
            return []
        try:
            s = await self._sess()
            r = await s.get(
                f"https://dev.kuaidaili.com/api/getproxy/?orderid={order}"
                f"&num={self.size}&format=text&sep=1",
                timeout=10,
            )
            return [
                f"http://{x}"
                for x in r.text.split()
                if re.fullmatch(r"\d+\.\d+\.\d+\.\d+:\d+", x.strip())
            ]
        except Exception:
            return []

    async def _test(self, proxy_url: str) -> bool:
        try:
            s = await self._sess()
            r = await s.get(
                config.PROXY_TEST_URL,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=config.PROXY_TEST_TIMEOUT,
            )
            return r.status_code == 200
        except Exception:
            return False

    async def refresh(self) -> int:
        """拉取新代理并做连通性测试，返回可用数量。"""
        candidates = list(dict.fromkeys(
            await self.fetch_free_proxy_list() + await self.fetch_kuaidaili()
        ))
        random.shuffle(candidates)
        to_test = candidates[: max(self.size * 3, 30)]
        results = await asyncio.gather(*[self._test(p) for p in to_test])
        for url, ok in zip(to_test, results):
            if ok and url not in self.entries:
                self.entries[url] = ProxyEntry(url)
        return sum(e.alive for e in self.entries.values())

    # ---------- 调度 ----------
    def _recover(self) -> None:
        now = time.time()
        for e in self.entries.values():
            if not e.alive and now - e.blacklisted_at >= config.PROXY_RECOVER_SECONDS:
                e.blacklisted_at = 0.0
                e.consec_fail = 0
                e.score = 0.5  # 恢复后降低权重，进入观察期

    def acquire(self) -> str | None:
        """按成功率加权随机取一个代理；池空返回 None（调用方直连）。"""
        self._recover()
        alive = [e for e in self.entries.values() if e.alive]
        if not alive:
            return None
        picked = random.choices(alive, weights=[e.score for e in alive], k=1)[0]
        picked.last_used = time.time()
        return picked.url

    def report(self, proxy_url: str | None, ok: bool) -> None:
        if proxy_url and proxy_url in self.entries:
            self.entries[proxy_url].report(ok)

    def stats(self) -> dict:
        alive = [e for e in self.entries.values() if e.alive]
        return {
            "total": len(self.entries),
            "alive": len(alive),
            "blacklisted": len(self.entries) - len(alive),
            "avg_score": round(sum(e.score for e in alive) / len(alive), 2) if alive else 0,
        }

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
