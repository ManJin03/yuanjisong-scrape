# -*- coding: utf-8 -*-
"""查询引擎：把搜索 / 筛选 / 排序合并为纯函数，供 GUI 与测试共用。

原始三大筛选能力在此融合：
1. smart_filter 黑名单过滤（exclude_blacklist）
2. classify 技术分类过滤（category）
3. filter_student_projects 学生模式（student_mode: ≤500 元 + 非驻场）
另加：关键词搜索（空格分隔多词 AND）、预算区间、仅远程、多种排序。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from yuanjisong import config
from yuanjisong.filter_student_projects import is_student_friendly
from yuanjisong.models import Project
from yuanjisong.smart_filter import apply_blacklist

CATEGORY_ALL = "全部"

SORT_OPTIONS = (
    "预算升序",
    "预算降序",
    "投递人数升序",
    "工时升序",
    "最新优先",
)


@dataclass
class QueryState:
    """一次查询的全部条件。"""
    keyword: str = ""
    category: str = CATEGORY_ALL
    budget_min: int = 0          # 0 = 不限下限
    budget_max: int = 0          # 0 = 不限上限
    remote_only: bool = False
    exclude_blacklist: bool = True
    student_mode: bool = False   # 预算≤上限 + 非驻场 + 排除黑名单
    sort_by: str = "预算升序"

    def student_budget_cap(self) -> int:
        return config.STUDENT_MAX_BUDGET


def _match_keyword(p: Project, keyword: str) -> bool:
    """空格分隔多关键词 AND 匹配（标题/类型/描述/雇主/分类，忽略大小写）。"""
    terms = [t.lower() for t in keyword.split() if t.strip()]
    if not terms:
        return True
    haystack = f"{p.title} {p.work_type} {p.description} {p.employer_name} {p.category}".lower()
    return all(t in haystack for t in terms)


def apply_query(projects: list[Project], q: QueryState) -> list[Project]:
    """按 QueryState 过滤 + 排序；不修改原始列表。"""
    items = list(projects)

    if q.student_mode:
        # 学生模式 = 严格预设：黑名单强制排除 + 预算上限 + 非驻场
        items, _dropped = apply_blacklist(items)
        items = [p for p in items if is_student_friendly(p)]
    elif q.exclude_blacklist:
        items, _dropped = apply_blacklist(items)
    if q.keyword.strip():
        items = [p for p in items if _match_keyword(p, q.keyword)]
    if q.category != CATEGORY_ALL:
        items = [p for p in items if (p.category or config.CATEGORY_OTHER) == q.category]
    if q.budget_min > 0:
        items = [p for p in items if p.budget >= q.budget_min]
    if q.budget_max > 0:
        cap = min(q.budget_max, q.student_budget_cap()) if q.student_mode else q.budget_max
        items = [p for p in items if 0 < p.budget <= cap]
    if q.remote_only:
        items = [p for p in items if p.is_remote]

    # 排序（稳定；预算/工时无效值排最后）
    if q.sort_by == "预算升序":
        items.sort(key=lambda p: (p.budget <= 0, p.budget, p.delivery_count))
    elif q.sort_by == "预算降序":
        items.sort(key=lambda p: (p.budget <= 0, -p.budget))
    elif q.sort_by == "投递人数升序":
        items.sort(key=lambda p: (p.delivery_count, p.budget))
    elif q.sort_by == "工时升序":
        items.sort(key=lambda p: (p.hours <= 0, p.hours))
    elif q.sort_by == "最新优先":
        items.sort(key=lambda p: -int(p.id) if p.id.isdigit() else 0)
    return items


def summarize(projects: list[Project]) -> str:
    """状态栏摘要：总数 / 远程数 / 学生友好数 / 分类数。"""
    if not projects:
        return "共 0 条"
    remote = sum(1 for p in projects if p.is_remote)
    student = sum(1 for p in projects if is_student_friendly(p) and not p.blacklist_hit)
    cats = {p.category or config.CATEGORY_OTHER for p in projects}
    return (f"共 {len(projects)} 条 | 远程 {remote} | 学生友好 {student} | "
            f"技术方向 {len(cats)} 个")


def available_categories(projects: list[Project]) -> list[str]:
    """数据中实际出现的技术方向（含"全部"置顶，按数量降序）。"""
    from collections import Counter
    c = Counter((p.category or config.CATEGORY_OTHER) for p in projects)
    return [CATEGORY_ALL] + [name for name, _ in c.most_common()]
