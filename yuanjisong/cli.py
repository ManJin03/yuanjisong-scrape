# -*- coding: utf-8 -*-
"""命令行入口：scrape / classify / student / gui / all 子命令。"""
from __future__ import annotations

import argparse
import asyncio
import sys

from yuanjisong import config


def _utf8_console() -> None:
    """Windows 控制台默认 GBK，强制 UTF-8 避免中文日志乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _load_or_exit():
    from yuanjisong.models import load_json

    projects = load_json(config.DATA_JSON)
    if not projects:
        sys.exit(f"未找到数据 {config.DATA_JSON}，请先运行: python main.py scrape")
    return projects


def cmd_scrape(args) -> None:
    from yuanjisong.scrape_lightweight import Scraper

    if args.fresh:
        config.STATE_JSON.unlink(missing_ok=True)
        config.DATA_JSON.unlink(missing_ok=True)
        config.OUTPUT_DIR.mkdir(exist_ok=True)

    async def _run():
        s = Scraper(concurrency=args.concurrency, use_proxy=args.use_proxy)
        try:
            await s.run(max_pages=args.pages)
        finally:
            await s.close()

    asyncio.run(_run())


def cmd_gui(_args) -> None:
    from yuanjisong.webapp import run

    run()


def cmd_classify(args) -> None:
    from yuanjisong.classify import category_summary, classify_all
    from yuanjisong.exporter import export_all_excel

    projects = classify_all(_load_or_exit())
    path = export_all_excel(projects)
    print(f"[classify] 分类分布: {category_summary(projects)}")
    print(f"[classify] 已导出 {path}")


def cmd_student(args) -> None:
    from yuanjisong.exporter import export_student_excel
    from yuanjisong.filter_student_projects import filter_student_projects

    projects = filter_student_projects(_load_or_exit())
    path = export_student_excel(projects)
    print(f"[student] 符合条件 {len(projects)} 条（≤{config.STUDENT_MAX_BUDGET}元且非驻场）")
    print(f"[student] 已导出 {path}")


def cmd_all(args) -> None:
    from yuanjisong.classify import category_summary, classify_all
    from yuanjisong.exporter import export_all_excel

    cmd_scrape(args)
    projects = classify_all(_load_or_exit())
    export_all_excel(projects)
    print(f"[all] 分类分布: {category_summary(projects)}")
    cmd_student(args)


def main() -> None:
    _utf8_console()
    ap = argparse.ArgumentParser(description="猿急送兼职项目智能筛选系统")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_scrape_options(p):
        p.add_argument("--pages", type=int, default=None)
        p.add_argument("--concurrency", type=int, default=config.CONCURRENCY)
        p.add_argument("--use-proxy", action="store_true")
        p.add_argument("--fresh", action="store_true")

    add_scrape_options(sub.add_parser("scrape", help="抓取兼职项目"))
    sub.add_parser("gui", help="启动交互式读取/筛选软件（浏览器 UI）")
    sub.add_parser("classify", help="技术分类并导出多 Sheet Excel")
    sub.add_parser("student", help="生成学生友好项目清单")
    add_scrape_options(sub.add_parser("all", help="抓取+分类+学生筛选全流程"))

    args = ap.parse_args()
    {"scrape": cmd_scrape, "gui": cmd_gui, "classify": cmd_classify,
     "student": cmd_student, "all": cmd_all}[args.cmd](args)


if __name__ == "__main__":
    main()
