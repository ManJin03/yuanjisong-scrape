# -*- coding: utf-8 -*-
"""scrape_lightweight —— 猿急送兼职项目异步并发爬虫。

流程：WAF 预热(首页种 Cookie) -> 并发抓取 /job/allcity/page{N} -> 解析 .job_card
     -> 指数退避重试 -> 周期性落盘(output/state.json + projects.json) -> 断点续爬。

用法：
  python scrape_lightweight.py                    # 全量增量抓取
  python scrape_lightweight.py --pages 50         # 只抓 50 页
  python scrape_lightweight.py --fresh            # 清空状态重新抓
  python scrape_lightweight.py --use-proxy        # 启用代理池轮转
  python scrape_lightweight.py --concurrency 8    # 调整并发
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time

from curl_cffi import requests as cffi_requests

import config
from models import Project, load_json, parse_job_cards, save_json
from proxy_pool import ProxyPool


class State:
    """断点续爬状态：已完成的页码集合 + 已见项目 ID。"""

    def __init__(self, path=config.STATE_JSON):
        self.path = path
        self.done_pages: set[int] = set()
        self.seen_ids: set[str] = set()
        self.next_page: int = 1
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                d = json.loads(self.path.read_text(encoding="utf-8"))
                self.done_pages = set(d.get("done_pages", []))
                self.seen_ids = set(d.get("seen_ids", []))
                self.next_page = int(d.get("next_page", 1))
            except Exception:
                pass  # 状态损坏则视为重爬

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "done_pages": sorted(self.done_pages),
            "seen_ids": sorted(self.seen_ids),
            "next_page": self.next_page,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False), encoding="utf-8")


class Scraper:
    def __init__(self, concurrency: int = config.CONCURRENCY, use_proxy: bool = False):
        self.concurrency = max(1, concurrency)
        self.session: cffi_requests.AsyncSession | None = None
        self.pool = ProxyPool() if use_proxy else None
        self.projects: dict[str, Project] = {}
        self.state = State()
        self.stats = {"pages_ok": 0, "pages_fail": 0, "items": 0, "retries": 0}

    # ---------- 会话 ----------
    async def _sess(self) -> cffi_requests.AsyncSession:
        if self.session is None:
            self.session = cffi_requests.AsyncSession(impersonate=config.IMPERSONATE)
        return self.session

    async def warmup(self) -> None:
        """访问首页触发 WAF 挑战并自动保存 Cookie；随后重试直到放行。"""
        s = await self._sess()
        for attempt in range(3):
            r = await s.get(config.BASE_URL + "/", headers=config.REQUEST_HEADERS,
                            timeout=config.PAGE_TIMEOUT)
            if r.status_code == 200:
                return
            await asyncio.sleep(1 + attempt)
        # 即使首页 403，会话 Cookie 已种下，列表页通常放行；继续尝试

    # ---------- 单页 ----------
    async def fetch_page(self, page: int) -> list[Project]:
        url = config.JOB_LIST_URL if page <= 1 else config.JOB_PAGE_URL.format(page=page)
        s = await self._sess()
        proxy = self.pool.acquire() if self.pool else None
        proxies = {"http": proxy, "https": proxy} if proxy else None
        last_err: Exception | None = None
        for attempt in range(config.PAGE_RETRIES):
            try:
                r = await s.get(url, headers=config.REQUEST_HEADERS, proxies=proxies,
                                timeout=config.PAGE_TIMEOUT)
                if r.status_code == 200:
                    if proxy and self.pool:
                        self.pool.report(proxy, True)
                    return parse_job_cards(r.text, page=page)
                last_err = RuntimeError(f"HTTP {r.status_code}")
            except Exception as e:  # 网络超时/代理故障
                last_err = e
                if proxy and self.pool:
                    self.pool.report(proxy, False)
                    proxy = self.pool.acquire()          # 换代理重试
                    proxies = {"http": proxy, "https": proxy} if proxy else None
            self.stats["retries"] += 1
            await asyncio.sleep(config.RETRY_BACKOFF ** attempt + random.random())
        raise RuntimeError(f"page {page} 失败: {last_err}")

    def _merge(self, projects: list[Project]) -> int:
        """合并本页结果，返回新增条数。"""
        new = 0
        for p in projects:
            if p.id not in self.projects:
                new += 1
            self.projects[p.id] = p
        return new

    async def _checkpoint(self, page: int, force: bool = False) -> None:
        self.state.done_pages.add(page)
        self.state.next_page = max(self.state.next_page, page + 1)
        if force or len(self.state.done_pages) % config.CHECKPOINT_EVERY == 0:
            self.state.seen_ids = set(self.projects)
            self.state.save()
            save_json(list(self.projects.values()), config.DATA_JSON)

    # ---------- 主流程 ----------
    async def run(self, max_pages: int | None = None) -> list[Project]:
        # 载入历史数据实现增量续爬
        for p in load_json(config.DATA_JSON):
            self.projects[p.id] = p

        if self.pool:
            alive = await self.pool.refresh()
            print(f"[proxy] 可用代理 {alive} 个 {self.pool.stats()}")
            if alive == 0:
                print("[proxy] 代理池为空，自动降级为直连")

        await self.warmup()
        sem = asyncio.Semaphore(self.concurrency)
        stop = asyncio.Event()
        start_page = self.state.next_page
        page_limit = start_page + max_pages - 1 if max_pages else None  # 绝对页码上限
        fetched = 0
        t0 = time.time()

        async def worker(page: int) -> None:
            nonlocal fetched
            if stop.is_set() or (page_limit and page > page_limit):
                return
            async with sem:
                if stop.is_set() or (page_limit and page > page_limit):
                    return
                try:
                    cards = await self.fetch_page(page)
                    fetched += 1
                    if not cards:                       # 空页 => 全站抓完
                        stop.set()
                        return
                    added = self._merge(cards)
                    self.stats["pages_ok"] += 1
                    self.stats["items"] += added
                    await self._checkpoint(page)
                    print(f"[page {page:>4}] {len(cards)} 条 / 新增 {added}，"
                          f"累计 {len(self.projects)}（{time.time()-t0:.0f}s）")
                except Exception as e:
                    self.stats["pages_fail"] += 1
                    print(f"[page {page:>4}] 失败：{e}", file=sys.stderr)
                    if self.stats["pages_fail"] >= 10:   # 连续性熔断
                        stop.set()

        page = start_page
        batch = self.concurrency * 3
        while not stop.is_set() and (page_limit is None or page <= page_limit):
            end = page + batch
            if page_limit:
                end = min(end, page_limit + 1)
            tasks = [asyncio.create_task(worker(p))
                     for p in range(page, end)
                     if p not in self.state.done_pages]
            if not tasks:
                break
            await asyncio.gather(*tasks)
            page = end

        await self._checkpoint(max(self.state.done_pages, default=start_page), force=True)
        print(f"[done] 成功页 {self.stats['pages_ok']} / 失败页 {self.stats['pages_fail']}"
              f" / 项目 {len(self.projects)} 条，用时 {time.time()-t0:.1f}s")
        return list(self.projects.values())

    async def close(self) -> None:
        if self.session:
            await self.session.close()
        if self.pool:
            await self.pool.close()


async def main() -> None:
    ap = argparse.ArgumentParser(description="猿急送兼职项目异步爬虫")
    ap.add_argument("--pages", type=int, default=None, help="最多抓取页数（默认全量）")
    ap.add_argument("--concurrency", type=int, default=config.CONCURRENCY, help="并发数")
    ap.add_argument("--use-proxy", action="store_true", help="启用代理池轮转")
    ap.add_argument("--fresh", action="store_true", help="清空历史状态重新抓取")
    args = ap.parse_args()

    if args.fresh:
        config.STATE_JSON.unlink(missing_ok=True)
        config.DATA_JSON.unlink(missing_ok=True)
        config.OUTPUT_DIR.mkdir(exist_ok=True)

    scraper = Scraper(concurrency=args.concurrency, use_proxy=args.use_proxy)
    try:
        await scraper.run(max_pages=args.pages)
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
